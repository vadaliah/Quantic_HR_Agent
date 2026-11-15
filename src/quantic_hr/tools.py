from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any

from quantic_hr import bedrock
from quantic_hr.compliance_route import canonicalize_route, derive_route
from quantic_hr.db import connection

HOURS_PER_DAY = 8.0


def _as_date(value: object) -> date:
    """Coerce a date column to a date object.

    The two database paths return different Python types for the same column:
    psycopg returns a `date`, while the Data API returns every scalar as JSON, so
    a date arrives as the string "2026-11-14". Arithmetic on the string raises

        TypeError: unsupported operand type(s) for -: 'str' and 'str'

    which is how a PTO question came to fail with the balance tool erroring and
    the agent reporting that it could not find the employee's records.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def as_of_date() -> str | None:
    """Optional fixed date for PTO balances (evaluation pins one); None means CURRENT_DATE."""
    return os.environ.get("QUANTIC_AS_OF") or None


def lookup_employee_profile(employee_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT e.employee_id, e.display_name, e.email, e.employment_type,
                   e.title, e.department, e.work_model, e.manager_id,
                   l.location_id, l.name AS location_name, l.region, l.country,
                   COALESCE(e.remote_eligible, l.remote_eligible) AS remote_eligible,
                   l.remote_eligible AS location_remote_eligible,
                   e.designated_onsite_role
            FROM employees e
            JOIN locations l ON l.location_id = e.location_id
            WHERE e.employee_id = %s
            """,
            (employee_id,),
        ).fetchone()
    if not row:
        return {"found": False, "employee_id": employee_id}
    return {"found": True, **row}


def check_pto_balance(employee_id: str) -> dict[str, Any]:
    """PTO in DAYS, computed from the policy rule applied to the employee's facts.

    The RULE comes from mock_data/policy_rules.json, each figure carrying the
    section that states it: the accrual rate and the pro-rata method from POL-001
    2.1, the carryover cap from POL-001 4.1. The FACTS come from the database:
    the hire date, days taken this year, pending days, and carryover held.

    The rate is deliberately NOT read from pto_accruals.accrual_days_per_month.
    A rule stored in a table is a rule the policy cannot govern: edit POL-001 and
    the answers would not move. Reading it from the rules file, with a citation,
    means the sentence a reader checks is the sentence the answer used.

    pto_balances (hours, migration 002) is deprecated and the runtime role has no
    grant on it after migration 005.
    """
    # 30.4375 is 365.25 / 12: the average Gregorian month. It converts elapsed
    # calendar days into months, so a per-month policy rate applies continuously
    # rather than only at month end. Named, and derived rather than written as a
    # literal, because a bare divisor in an expression is the kind of number a
    # reader cannot account for six months later. tests/test_policy_rules.py
    # asserts this default and the rules file agree.
    AVERAGE_MONTH_DAYS = 365.25 / 12

    rule = policy_rules()["pto_accrual"]
    pro_rata = rule["pro_rata"]
    rate = float(rule["days_per_completed_month"])
    divisor = float(pro_rata["days_to_months_divisor"])
    if abs(divisor - AVERAGE_MONTH_DAYS) > 0.0001:
        raise ValueError(
            f"pro-rata divisor {divisor} ({pro_rata.get('divisor_name')}) does not "
            f"match AVERAGE_MONTH_DAYS {AVERAGE_MONTH_DAYS:.4f} "
            f"({pro_rata.get('divisor_derivation')}); one of the two has changed"
        )
    cap = float(rule["carryover_max_days"])

    with connection() as conn:
        row = conn.execute(
            """
            SELECT a.employee_id, a.plan, a.carryover_days, a.taken_days_this_year,
                   a.pending_days, a.balance_year, e.hire_date,
                   COALESCE(%s::date, CURRENT_DATE) AS as_of,
                   GREATEST(make_date(extract(year FROM COALESCE(%s::date, CURRENT_DATE))::int, 1, 1),
                            e.hire_date) AS accrual_start
            FROM pto_accruals a
            JOIN employees e USING (employee_id)
            WHERE a.employee_id = %s
            """,
            (as_of_date(), as_of_date(), employee_id),
        ).fetchone()
    if not row:
        return {"found": False, "employee_id": employee_id}

    as_of = _as_date(row["as_of"])
    start = _as_date(row["accrual_start"])
    as_of_iso = as_of.isoformat()
    days_elapsed = max(0, (as_of - start).days)
    months = days_elapsed / divisor
    accrued = round(rate * months, 2)

    carryover_stored = float(row["carryover_days"] or 0)
    carryover = min(carryover_stored, cap)
    taken = float(row["taken_days_this_year"] or 0)
    pending = float(row["pending_days"] or 0)
    available = round(accrued + carryover - taken - pending, 2)

    result: dict[str, Any] = {
        "found": True,
        "employee_id": row["employee_id"],
        "plan": row["plan"],
        "as_of": as_of_iso,
        "balance_year": row["balance_year"],
        # the facts
        "hire_date": _as_date(row["hire_date"]).isoformat(),
        "accrual_start": start.isoformat(),
        "days_elapsed": days_elapsed,
        "months_elapsed": round(months, 4),
        "taken_days_this_year": taken,
        "pending_days": pending,
        "carryover_stored": carryover_stored,
        "carryover_applied": carryover,
        "carryover_cap": cap,
        # the result, and how it was reached
        "accrued_days": accrued,
        "available_days": available,
        "available_formula": (
            f"{accrued:.2f} + {carryover:.2f} - {taken:.2f} - {pending:.2f} = {available:.2f}"
        ),
        "available_note": (
            "available_days is the closing balance: accrued plus carryover, less "
            "taken and pending. It is not the sum of accrued and carryover."
        ),
        "rules": [
            {
                "document_id": rule["accrual_document_id"],
                "section_id": rule["accrual_section_id"],
                "fact": f"accrual {rate} days per month, pro rata from 1 January",
                "source_text": rule["accrual_source_text"],
            },
            {
                "document_id": pro_rata["divisor_document_id"],
                "section_id": pro_rata["divisor_section_id"],
                "fact": (
                    f"pro-rata method: {pro_rata['divisor_name']} = "
                    f"{pro_rata['divisor_derivation']} = {divisor}"
                ),
                "source_text": pro_rata["divisor_note"],
            },
            {
                "document_id": rule["carryover_document_id"],
                "section_id": rule["carryover_section_id"],
                "fact": f"carryover capped at {cap:g} days",
                "source_text": rule["carryover_source_text"],
            },
        ],
        "policy_document_id": rule["accrual_document_id"],
        "policy_section_id": rule["accrual_section_id"],
    }
    if carryover_stored > cap:
        result["carryover_note"] = (
            f"{carryover_stored:g} days were held over, but the policy caps carryover "
            f"at {cap:g} days, so {cap:g} is applied."
        )
    return result


_STOPWORDS = {
    "about", "after", "also", "another", "before", "could", "does", "from", "have", "into",
    "many", "much", "need", "should", "that", "their", "there", "this", "what", "when",
    "where", "which", "while", "will", "with", "would", "your",
}

_SEARCH_COLUMNS = """
    c.chunk_id, c.document_id, c.section_id, c.heading, c.content, d.title, d.source_uri
"""


def retrieval_mode() -> str:
    """QUANTIC_RETRIEVAL: auto (vector when embeddings and AWS credentials exist), vector, keyword."""
    mode = os.environ.get("QUANTIC_RETRIEVAL", "auto").strip().lower()
    return mode if mode in {"auto", "vector", "keyword"} else "auto"


def min_similarity() -> float:
    """Cosine-similarity floor; weaker matches are dropped so the agent can abstain."""
    try:
        return float(os.environ.get("QUANTIC_MIN_SIMILARITY", "0.2"))
    except ValueError:
        return 0.2


def _vector_search(query: str, limit: int) -> dict[str, Any]:
    vector = bedrock.vector_literal(bedrock.embed_text(query))
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_SEARCH_COLUMNS}, 1 - (c.embedding <=> %s::vector) AS score
            FROM policy_chunks c
            JOIN policy_documents d ON d.document_id = c.document_id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, vector, limit),
        ).fetchall()
    floor = min_similarity()
    matches = [{**row, "score": round(float(row["score"]), 4)} for row in rows if float(row["score"]) >= floor]
    return {"query": query, "matches": matches, "retrieval": "vector", "min_similarity": floor}


def _keyword_terms(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", query.lower())
    terms = [w for w in words if len(w) >= 4 and w not in _STOPWORDS]
    return list(dict.fromkeys(terms))[:8]


def _keyword_search(query: str, limit: int) -> dict[str, Any]:
    """ILIKE fallback: the whole phrase first, then chunks ranked by matching terms."""
    like = f"%{query}%"
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_SEARCH_COLUMNS}
            FROM policy_chunks c
            JOIN policy_documents d ON d.document_id = c.document_id
            WHERE c.content ILIKE %s OR c.heading ILIKE %s OR d.title ILIKE %s
            ORDER BY c.document_id, c.chunk_index, c.section_id
            LIMIT %s
            """,
            (like, like, like, limit),
        ).fetchall()
        terms = _keyword_terms(query)
        if not rows and terms:
            patterns = [f"%{term}%" for term in terms]
            hits = " + ".join(
                "((c.content || ' ' || coalesce(c.heading, '') || ' ' || d.title) ILIKE %s)::int"
                for _ in patterns
            )
            rows = conn.execute(
                f"""
                SELECT * FROM (
                  SELECT {_SEARCH_COLUMNS}, c.chunk_index, ({hits}) AS hits
                  FROM policy_chunks c
                  JOIN policy_documents d ON d.document_id = c.document_id
                ) ranked
                WHERE hits >= %s
                ORDER BY hits DESC, document_id, chunk_index
                LIMIT %s
                """,
                (*patterns, min(2, len(patterns)), limit),
            ).fetchall()
            rows = [{k: v for k, v in row.items() if k not in {"hits", "chunk_index"}} for row in rows]
    return {"query": query, "matches": rows, "retrieval": "keyword"}


def search_policy_documents(query: str, limit: int = 5) -> dict[str, Any]:
    """Semantic search with pgvector (HNSW, cosine) over Titan v2 embeddings.

    Falls back to ILIKE when no chunk has an embedding yet, when AWS credentials
    are absent, or when Bedrock fails (unless QUANTIC_RETRIEVAL=vector).
    """
    limit = max(1, min(int(limit or 5), 10))
    mode = retrieval_mode()
    reason = "QUANTIC_RETRIEVAL=keyword"
    if mode != "keyword":
        with connection() as conn:
            has_embeddings = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM policy_chunks WHERE embedding IS NOT NULL) AS present"
            ).fetchone()["present"]
        if not has_embeddings:
            reason = "no embeddings in policy_chunks; run scripts/ingest_corpus.py"
        elif mode == "auto" and not bedrock.credentials_available():
            reason = "no AWS credentials for Bedrock"
        else:
            try:
                return _vector_search(query, limit)
            except bedrock.BedrockUnavailable as exc:
                if mode == "vector":
                    raise
                reason = str(exc)
        if mode == "vector":
            raise bedrock.BedrockUnavailable(reason)
    result = _keyword_search(query, limit)
    result["fallback_reason"] = reason
    return result


def get_policy_section(document_id: str, section_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT c.chunk_id, c.document_id, c.section_id, c.heading, c.content,
                   d.title, d.source_uri
            FROM policy_chunks c
            JOIN policy_documents d ON d.document_id = c.document_id
            WHERE c.document_id = %s AND c.section_id = %s
            """,
            (document_id, section_id),
        ).fetchone()
    if not row:
        return {"found": False, "document_id": document_id, "section_id": section_id}
    return {"found": True, **row}


# ------------------------------------------------------------- policy rules
# Design: a rule engine, not a chain of ifs.
#
#   * Limits are DATA (mock_data/policy_rules.json), each keyed to the section
#     that states it, so a verdict always cites the text it came from.
#   * Each check type is one function registered in CHECKS. The MCP schema
#     lists exactly these names, so the model cannot invent a check type.
#   * Every result has the same shape (Verdict). A check that did not run
#     returns checked=False and compliant=None -- never False. Returning
#     False for "I could not check" is what made the model answer that a $400
#     chair broke a $500 limit.
#   * Arithmetic happens here and is shown in the result ("400.00 <= 500.00"),
#     so the model reports a computed comparison instead of reasoning over prose.
import json
from functools import lru_cache
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parents[2] / "mock_data" / "policy_rules.json"


@lru_cache(maxsize=1)
def policy_rules() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text())


def _verdict(
    check_type: str,
    *,
    checked: bool,
    compliant: bool | None,
    route: str,
    reason: str,
    document_id: str | None = None,
    section_id: str | None = None,
    **facts: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "check_type": check_type,
        "checked": checked,
        "compliant": compliant,
        "route": route,
        "reason": reason,
        **facts,
    }
    if document_id:
        out["policy_document_id"] = document_id
        out["policy_section_id"] = section_id
    return out


def _not_checked(check_type: str, reason: str, **facts: Any) -> dict[str, Any]:
    return _verdict(
        check_type, checked=False, compliant=None, route="CANNOT_DETERMINE",
        reason=reason, supported_check_types=sorted(CHECKS), **facts,
    )


def resolve_expense_category(name: str | None) -> str | None:
    """Map what the user bought ("chair", "hotel") to a rule category."""
    if not name:
        return None
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    categories = policy_rules()["expense_categories"]
    if key in categories:
        return key
    for category, rule in categories.items():
        if key in rule["aliases"] or any(alias in key for alias in rule["aliases"]):
            return category
    return None


def _check_expense(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    category = resolve_expense_category(args.get("expense_category"))
    if category is None:
        return _not_checked(
            "expense",
            f"no expense rule for category {args.get('expense_category')!r}",
            known_categories=sorted(policy_rules()["expense_categories"]),
        )
    amount = args.get("amount")
    if amount is None or float(amount) <= 0:
        return _not_checked("expense", "amount (USD) is required to compare against the limit")
    amount = float(amount)
    rule = policy_rules()["expense_categories"][category]
    glob = policy_rules()["expense_global"]
    limit = float(rule["limit_usd"])

    needed_model = rule.get("requires_work_model")
    if needed_model and profile.get("work_model") != needed_model:
        return _verdict(
            "expense", checked=True, compliant=False, route="NOT_ELIGIBLE",
            reason=f"{rule['description']} applies only to {needed_model} employees",
            document_id=rule["document_id"], section_id=rule["section_id"],
            category=category, amount_usd=amount, limit_usd=limit,
        )

    within = amount <= limit
    comparison = f"{amount:.2f} {'<=' if within else '>'} {limit:.2f}"
    receipt = amount >= glob["receipt_required_from_usd"]
    if within:
        route, reason = "CLAIM_WITH_RECEIPT" if receipt else "CLAIM", (
            f"${amount:,.2f} is within the ${limit:,.0f} {rule['limit_kind'].replace('_', ' ')} "
            f"limit for {rule['description'].lower()}, so it is reimbursable"
        )
    elif amount > glob["pre_approval_above_usd"]:
        route, reason = "NEEDS_PRE_APPROVAL", (
            f"${amount:,.2f} exceeds the ${limit:,.0f} limit and the "
            f"${glob['pre_approval_above_usd']:,} pre-approval threshold; only up to "
            f"${limit:,.0f} is reimbursable without manager pre-approval"
        )
    else:
        route, reason = "PARTIAL_UP_TO_LIMIT", (
            f"${amount:,.2f} exceeds the ${limit:,.0f} limit; at most ${limit:,.0f} "
            f"is reimbursable and the remaining ${amount - limit:,.2f} is not"
        )
    return _verdict(
        "expense", checked=True, compliant=within, route=route, reason=reason,
        document_id=rule["document_id"], section_id=rule["section_id"],
        category=category, amount_usd=amount, limit_usd=limit,
        comparison=comparison,
        reimbursable_usd=min(amount, limit),
        receipt_required=receipt,
        source_text=rule["source_text"],
    )


def _check_pto(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    days = float(args.get("days_requested") or 0)
    if days <= 0:
        return _not_checked("pto", "days_requested is required")
    rule = policy_rules()["pto"]
    balance = check_pto_balance(profile["employee_id"])
    if balance.get("plan") == "NOT_ELIGIBLE":
        return _verdict(
            "pto", checked=True, compliant=False, route="NOT_ELIGIBLE",
            reason="this employment type does not accrue paid time off",
            document_id="POL-001", section_id="1", days_requested=days,
        )
    available = float(balance.get("available_days") or 0)
    enough = days <= available
    approval = days >= rule["manager_approval_from_days"]
    if not enough:
        route = "INSUFFICIENT_BALANCE"
    elif approval:
        route = "MANAGER_APPROVAL"
    else:
        route = "SELF_SERVICE"
    return _verdict(
        "pto", checked=True, compliant=enough, route=route,
        reason=(
            f"{days:g} day(s) requested, {available:g} available"
            + ("; manager approval required" if enough and approval else "")
        ),
        document_id=rule["document_id"], section_id=rule["section_id"],
        days_requested=days, available_days=available,
        comparison=f"{days:g} {'<=' if enough else '>'} {available:g}",
        manager_approval_required=approval, as_of=balance.get("as_of"),
    )


def _check_remote(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    rule = policy_rules()["remote_work"]
    eligible = bool(profile.get("remote_eligible")) and not profile.get("designated_onsite_role")
    if not eligible:
        return _verdict(
            "remote_work", checked=True, compliant=False, route="NOT_ELIGIBLE",
            reason="the role is designated onsite or not remote-eligible",
            document_id="POL-003", section_id="3", remote_eligible=False,
        )
    country = (args.get("destination_country") or "").upper() or None
    state = (args.get("destination_region") or "").upper() or None
    days = float(args.get("duration_days") or 0)
    home_country = (profile.get("country") or "US").upper()
    if country and country != home_country:
        limit = rule["international_approval_after_days"]
        needs = days == 0 or days > limit
        return _verdict(
            "remote_work", checked=True, compliant=not needs,
            route="PEOPLE_OPS_AND_LEGAL_APPROVAL" if needs else "MANAGER_APPROVAL",
            reason=(
                f"working from {country} for {days:g} days"
                + (f" exceeds {limit} days and needs People Operations and Legal approval"
                   if needs else f" is within {limit} days")
            ),
            document_id=rule["document_id"], section_id=rule["section_id"],
            destination_country=country, duration_days=days, limit_days=limit,
            comparison=f"{days:g} {'>' if needs else '<='} {limit}",
        )
    if state and state != (profile.get("region") or "").upper():
        return _verdict(
            "remote_work", checked=True, compliant=False, route="MANAGER_APPROVAL",
            reason=f"working from {state} (another state) needs approval",
            document_id="POL-003", section_id="4.2", destination_region=state,
        )
    return _verdict(
        "remote_work", checked=True, compliant=True, route="SELF_SERVICE",
        reason="employee is remote-eligible in their home location",
        document_id="POL-003", section_id="3",
    )


CHECKS = {"expense": _check_expense, "pto": _check_pto, "remote_work": _check_remote}


def check_policy_compliance(
    employee_id: str,
    check_type: str,
    days_requested: float = 0,
    amount: float | None = None,
    expense_category: str | None = None,
    destination_country: str | None = None,
    destination_region: str | None = None,
    duration_days: float = 0,
) -> dict[str, Any]:
    check = CHECKS.get((check_type or "").strip().lower())
    if check is None:
        return _not_checked(str(check_type), f"unknown check_type {check_type!r}")
    profile = lookup_employee_profile(employee_id)
    if not profile.get("found"):
        return _not_checked(check_type, f"unknown employee {employee_id}")
    result = check(profile, {
        "days_requested": days_requested,
        "amount": amount,
        "expense_category": expense_category,
        "destination_country": destination_country,
        "destination_region": destination_region,
        "duration_days": duration_days,
    })
    # Additive: current check functions already set a vocabulary `route`.
    # Fill it in only when missing or not in the gold vocabulary, so older
    # call shapes still expose the field to the agent and the scorer.
    if not canonicalize_route(result.get("route")):
        derived = derive_route({key: value for key, value in result.items() if key != "route"})
        if derived:
            result["route"] = derived
    return result


BENEFITS_PATH = RULES_PATH.parent / "benefits.json"


def lookup_benefits_status(employee_id: str) -> dict[str, Any]:
    """Synthetic benefits elections from mock_data/benefits.json."""
    rows = {r["employee_id"]: r for r in json.loads(BENEFITS_PATH.read_text())}
    row = rows.get(employee_id)
    if not row:
        return {"found": False, "employee_id": employee_id}
    return {"found": True, **row,
            "reason": "eligible for benefits" if row["eligible"]
            else f"{row['employment_type'].lower()} employees are not benefits-eligible",
            "policy_document_id": "POL-007", "policy_section_id": "1"}


TICKETS: list[dict[str, Any]] = []


def create_mock_hr_ticket(
    employee_id: str, category: str, summary: str, confirm: bool = False
) -> dict[str, Any]:
    """Mock write held in memory. Without confirm=True only a preview returns."""
    ticket = {"employee_id": employee_id, "category": category, "summary": summary}
    if not confirm:
        return {"status": "awaiting_confirmation", "created": False, "preview": ticket}
    ticket["ticket_id"] = f"MOCK-{len(TICKETS) + 1:04d}"
    TICKETS.append(ticket)
    return {"status": "created_mock", "created": True, **ticket,
            "note": "Mock ticket only; no HR system was changed."}


def draft_hr_email(employee_id: str, topic: str, body_points: list[str] | None = None) -> dict[str, Any]:
    profile = lookup_employee_profile(employee_id)
    name = profile.get("display_name", employee_id)
    points = body_points or []
    draft = (
        f"Subject: {topic}\n\nHi {name},\n\n"
        + "\n".join(f"- {point}" for point in points)
        + "\n\nThis is a mock draft only. No email was sent.\n"
    )
    return {"draft": draft, "sent": False, "employee_id": employee_id}
