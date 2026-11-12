from __future__ import annotations

import os
import re
from typing import Any

from quantic_hr import bedrock
from quantic_hr.db import connection

HOURS_PER_DAY = 8.0


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
    """PTO in days from pto_accruals via pto_balance_as_of() (migration 004).

    pto_balances (hours, migration 002) is deprecated and the runtime role has no
    grant on it after migration 005.
    """
    with connection() as conn:
        row = conn.execute(
            """
            SELECT b.employee_id, b.plan, b.accrued_days, b.available_days,
                   a.carryover_days, a.taken_days_this_year, a.pending_days,
                   a.balance_year, COALESCE(%s::date, CURRENT_DATE) AS as_of
            FROM pto_balance_as_of(COALESCE(%s::date, CURRENT_DATE)) b
            JOIN pto_accruals a USING (employee_id)
            WHERE b.employee_id = %s
            """,
            (as_of_date(), as_of_date(), employee_id),
        ).fetchone()
    if not row:
        return {"found": False, "employee_id": employee_id}
    result: dict[str, Any] = {"found": True}
    for key, value in row.items():
        if key in {"employee_id", "plan", "balance_year"}:
            result[key] = value
        elif key == "as_of":
            result[key] = value.isoformat() if hasattr(value, "isoformat") else value
        else:
            result[key] = float(value)
    result["policy_document_id"] = "POL-001"
    result["policy_section_id"] = "2.1"
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


# ------------------------------------------------------------- policy limits
def _limit_from_corpus(document_id: str, section_id: str) -> float | None:
    """Read a dollar limit out of the policy text rather than asserting it.

    Hardcoding the home office stipend would silently disagree with POL-005 the
    moment the corpus is edited, and nothing would catch it. Reading the figure
    keeps one source of truth: the citation the answer gives is the same text
    the comparison came from.

    Returns None when no figure can be read, so the caller reports that rather
    than inventing a threshold.
    """
    section = get_policy_section(document_id, section_id)
    if not section.get("found"):
        return None
    text = str(section.get("content") or "")
    # POL-005 2.1 words the rule as a "one-time ... stipend of $500". Anchoring
    # on the phrase avoids picking up an unrelated figure elsewhere in the
    # section, which a bare "$" match would.
    match = re.search(r"one-time[^$]{0,60}\$\s?([\d,]+(?:\.\d{2})?)", text, re.I)
    if not match:
        match = re.search(r"\$\s?([\d,]+(?:\.\d{2})?)", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


# The model names an expense check in several ways, and an unrecognised name
# used to produce "unsupported check_type", which left the comparison to be
# reasoned from prose. Amount questions now get the deterministic branch
# whatever label arrives.
EXPENSE_CHECK_TYPES = {
    "expense", "expenses", "reimbursement", "reimbursable", "office_furniture",
    "furniture", "equipment", "home_office", "stipend", "purchase",
}


def check_policy_compliance(
    employee_id: str,
    check_type: str,
    requested_hours: float = 0,
    destination_region: str | None = None,
    requested_days: float = 0,
    amount: float = 0,
) -> dict[str, Any]:
    profile = lookup_employee_profile(employee_id)
    if not profile.get("found"):
        return {"compliant": False, "reason": "unknown employee", "employee_id": employee_id}

    if check_type == "remote_work":
        eligible = bool(profile["remote_eligible"]) and not profile.get("designated_onsite_role")
        same_region = destination_region is None or destination_region == profile["region"]
        compliant = eligible and same_region
        if not eligible:
            reason = "employee is not remote-eligible (onsite role or work model)"
        elif not same_region:
            reason = "work from another state or country needs approval (POL-003 4.2/4.3, POL-004)"
        else:
            reason = "employee is remote-eligible"
        return {
            "compliant": compliant,
            "check_type": check_type,
            "employee_id": employee_id,
            "remote_eligible": eligible,
            "work_model": profile.get("work_model"),
            "employee_region": profile["region"],
            "destination_region": destination_region,
            "reason": reason,
            "policy_document_id": "POL-003",
            "policy_section_id": "3" if compliant or not eligible else "4.2",
        }

    if check_type == "pto":
        days = float(requested_days or 0) or float(requested_hours or 0) / HOURS_PER_DAY
        balance = check_pto_balance(employee_id)
        if balance.get("plan") == "NOT_ELIGIBLE":
            return {
                "compliant": False,
                "check_type": check_type,
                "employee_id": employee_id,
                "requested_days": days,
                "reason": "not eligible for paid time off",
                "policy_document_id": "POL-001",
                "policy_section_id": "1",
            }
        available = float(balance.get("available_days") or 0)
        compliant = available >= days
        return {
            "compliant": compliant,
            "check_type": check_type,
            "employee_id": employee_id,
            "requested_days": days,
            "available_days": available,
            "as_of": balance.get("as_of"),
            "manager_approval_required": days >= 3,
            "reason": "sufficient PTO balance" if compliant else "insufficient PTO balance",
            "policy_document_id": "POL-001",
            "policy_section_id": "2.1" if compliant else "3.1",
        }

    if check_type in EXPENSE_CHECK_TYPES:
        # The comparison is made here, not by the model reading prose. A section
        # titled "What is not reimbursed" describes exclusions; applying it to a
        # figure UNDER the limit inverts the rule, which is how a $400 chair was
        # once answered as not reimbursable.
        amount = float(amount or 0)
        stipend = _limit_from_corpus("POL-005", "2.1")
        if stipend is None:
            # No number invented. If the corpus does not state the limit, the
            # honest answer is that the comparison cannot be made.
            return {
                "compliant": False,
                "check_type": check_type,
                "employee_id": employee_id,
                "amount": amount,
                "reason": "could not read the home office stipend from POL-005 2.1",
                "policy_document_id": "POL-005",
                "policy_section_id": "2.1",
            }
        if amount <= stipend:
            return {
                "compliant": True,
                "check_type": check_type,
                "employee_id": employee_id,
                "amount": amount,
                "stipend": stipend,
                "route": "CLAIM_WITH_RECEIPT",
                "reason": (
                    f"${amount:.0f} is within the ${stipend:.0f} one-time home office "
                    "stipend, so it is reimbursable. Submit the receipt within 30 days."
                ),
                "policy_document_id": "POL-005",
                "policy_section_id": "2.1",
            }
        return {
            "compliant": False,
            "check_type": check_type,
            "employee_id": employee_id,
            "amount": amount,
            "stipend": stipend,
            "route": "NEEDS_PRE_APPROVAL",
            "reason": (
                f"${amount:.0f} exceeds the ${stipend:.0f} one-time home office "
                "stipend, so it needs manager pre-approval."
            ),
            "policy_document_id": "POL-005",
            "policy_section_id": "2.1",
        }

    return {"compliant": False, "reason": f"unsupported check_type {check_type}"}


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
