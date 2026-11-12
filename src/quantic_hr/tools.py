"""Database tools for the HR agent.

Every function returns a plain dict. Nothing here writes except
create_mock_hr_ticket, and that requires confirm=True.

Conventions that apply to the whole module
------------------------------------------
UNITS ARE DAYS. PTO accrual, carryover, the 3-day manager approval threshold and
the 30/90-day remote-work thresholds all come from the corpus in days. No
function here accepts or returns hours.

MISSING DATA DOES NOT RAISE. A missing record returns
{"found": False, "error": "..."} so the agent can ask a clarifying question
instead of the request failing. The exception is search_policy_documents, where
{"found": False} means the question is out of corpus and the agent should refuse
to answer rather than answer generally.

CITATIONS ARE REAL. Policy references are document and section ids from corpus/
(POL-003 s4.3), where the section id is the numbered heading.

TRANSPORT. Queries go through _sql(), which uses the RDS Data API when
CLUSTER_ARN and SECRET_ARN are set, and psycopg otherwise. The cluster sits in
private subnets, so from a laptop only the Data API works — its DNS name
resolves to a 10.20.x.x address with no route from outside the VPC.

BEDROCK IS A HARD DEPENDENCY for search. If the embedding call fails, or if the
model configured here differs from the model recorded at ingestion, the search
reports the problem instead of falling back to keyword matching.
"""
from __future__ import annotations

import os
from typing import Any

from quantic_hr.db import connection, execute, query_one, using_data_api

DEFAULT_TOP_K = 5
# Below this cosine similarity we treat the question as out of corpus and let
# the agent refuse rather than answer from a weak match.
MIN_SCORE = 0.25
EMBED_DIM = 1024
DEFAULT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"


def _embed_model() -> str:
    return os.environ.get("BEDROCK_EMBEDDING_MODEL", DEFAULT_EMBED_MODEL)


def _aws_region() -> str:
    return os.environ.get("AWS_REGION", "us-east-2")


# ------------------------------------------------------------------ transport
def _sql(sql_text: str, parameters: list[Any] | None = None) -> list[dict[str, Any]]:
    """Run a query on whichever path is configured.

    The Data API binds named parameters (:p1, :p2), psycopg binds positional
    ones (%s). Rather than keeping two copies of every query, %s placeholders
    are rewritten to :pN when the Data API is in use. The SQL text stays
    identical either way, which is what keeps the two paths from drifting.
    """
    params = list(parameters or [])
    if using_data_api():
        parts = sql_text.split("%s")
        if len(parts) - 1 != len(params):
            raise ValueError(
                f"placeholder count {len(parts) - 1} does not match "
                f"parameter count {len(params)}"
            )
        rewritten = parts[0]
        for index, value in enumerate(params, 1):
            rewritten += f":p{index}" + parts[index]
        return execute(rewritten, params)
    with connection() as conn:
        return [dict(r) for r in conn.execute(sql_text, tuple(params)).fetchall()]


def _sql_one(sql_text: str, parameters: list[Any] | None = None) -> dict[str, Any] | None:
    rows = _sql(sql_text, parameters)
    return rows[0] if rows else None


# ------------------------------------------------------------------ retrieval
def _embed_query(text: str) -> list[float]:
    """Embed a question with the same model used at ingestion time."""
    from langchain_aws import BedrockEmbeddings

    embedder = BedrockEmbeddings(model_id=_embed_model(), region_name=_aws_region())
    return embedder.embed_query(text)


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def _model_mismatch() -> list[str]:
    """Models recorded at ingestion that differ from the one configured here.

    An empty list means the two agree, which is the only state in which cosine
    similarity between a stored vector and a query vector is meaningful.
    """
    rows = _sql(
        """
        SELECT DISTINCT embedding_model
        FROM policy_documents
        WHERE embedding_model IS NOT NULL AND embedding_model <> %s
        """,
        [_embed_model()],
    )
    recorded = _sql_one(
        "SELECT count(*) AS n FROM policy_documents WHERE embedding_model IS NOT NULL"
    )
    if not recorded or not recorded.get("n"):
        return ["<no documents recorded an embedding model; re-run ingest_corpus.py>"]
    return [r["embedding_model"] for r in rows]


def search_policy_documents(
    query: str,
    limit: int = DEFAULT_TOP_K,
    document_id: str | None = None,
    min_score: float = MIN_SCORE,
) -> dict[str, Any]:
    """Vector search over policy chunks, returning cited snippets.

    Reads policy_chunks ordered by cosine distance (embedding <=> query), so
    ASC is highest similarity first. The score is recovered as 1 - distance.
    Chunks below min_score are dropped, which is what turns a weak match into an
    out-of-corpus answer.

    The query vector is interpolated into the SQL rather than bound as a
    parameter, because the Data API does not bind pgvector values. The vector is
    produced by Titan from the user's question, so it contains only digits,
    commas and brackets.
    """
    mismatch = _model_mismatch()
    if mismatch:
        return {
            "query": query,
            "mode": "error",
            "found": False,
            "matches": [],
            "note": ("Embedding model mismatch: ingestion recorded "
                     f"{sorted(set(mismatch))} but the query path is configured for "
                     f"{_embed_model()}. Re-ingest the corpus before trusting retrieval."),
        }

    vector = _vector_literal(_embed_query(query))
    limit = max(1, min(int(limit), 20))

    if document_id:
        rows = _sql(
            f"""
            SELECT c.chunk_id, c.document_id, c.section_id, c.heading,
                   c.content, d.title, d.source_uri,
                   1 - (c.embedding <=> '{vector}'::vector) AS score
            FROM policy_chunks c
            JOIN policy_documents d ON d.document_id = c.document_id
            WHERE c.embedding IS NOT NULL AND c.document_id = %s
            ORDER BY c.embedding <=> '{vector}'::vector
            LIMIT {limit}
            """,
            [document_id],
        )
    else:
        rows = _sql(
            f"""
            SELECT c.chunk_id, c.document_id, c.section_id, c.heading,
                   c.content, d.title, d.source_uri,
                   1 - (c.embedding <=> '{vector}'::vector) AS score
            FROM policy_chunks c
            JOIN policy_documents d ON d.document_id = c.document_id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> '{vector}'::vector
            LIMIT {limit}
            """
        )

    matches = []
    for row in rows:
        score = row.get("score")
        if score is None:
            continue
        score = float(score)
        if score < min_score:
            continue
        row["score"] = round(score, 3)
        row["snippet"] = (row.get("content") or "")[:400]
        row["citation"] = f"{row['document_id']} s{row['section_id']}"
        matches.append(row)

    return {
        "query": query,
        "mode": "vector",
        "embedding_model": _embed_model(),
        "found": bool(matches),
        "matches": matches,
        "note": None if matches else
                "No policy passage met the relevance threshold. Treat as out of corpus "
                "and say the policy does not cover it rather than answering generally.",
    }


def get_policy_section(document_id: str, section_id: str) -> dict[str, Any]:
    """Fetch one policy section. A section may span several chunks.

    Ordered by chunk_index because ingest splits long sections into windows.
    chunk_id is derived from document_id, section_id and index rather than the
    content, so re-ingesting an edited document overwrites its rows instead of
    orphaning them.
    """
    rows = _sql(
        """
        SELECT c.chunk_id, c.document_id, c.section_id, c.heading, c.content,
               d.title, d.source_uri
        FROM policy_chunks c
        JOIN policy_documents d ON d.document_id = c.document_id
        WHERE c.document_id = %s AND c.section_id = %s
        ORDER BY c.chunk_index
        """,
        [document_id, section_id],
    )
    if not rows:
        return {"found": False, "document_id": document_id, "section_id": section_id,
                "error": "SECTION_NOT_FOUND"}
    return {
        "found": True,
        "document_id": document_id,
        "section_id": section_id,
        "title": rows[0]["title"],
        "heading": rows[0]["heading"],
        "content": "\n\n".join(r["content"] for r in rows),
        "citation": f"{document_id} s{section_id}",
    }


# ----------------------------------------------------------------- structured
def lookup_employee_profile(employee_id: str) -> dict[str, Any]:
    """Return one employee with location, manager and service length.

    remote_eligible comes from the employee row, not the location row, because
    POL-003 s3 makes eligibility a property of the role. months_of_service is
    computed here so probation (under 3 months, POL-008 s2.2) is derivable
    without a second query.
    """
    row = _sql_one(
        """
        SELECT e.employee_id, e.display_name, e.email, e.title, e.department,
               e.employment_type, e.scheduled_hours_per_week, e.hire_date,
               e.manager_id, e.home_country, e.home_location, e.work_model,
               e.remote_eligible, e.designated_onsite_role,
               l.location_id, l.name AS location_name, l.region, l.country,
               (EXTRACT(YEAR FROM age(CURRENT_DATE, e.hire_date)) * 12
                + EXTRACT(MONTH FROM age(CURRENT_DATE, e.hire_date)))::int AS months_of_service
        FROM employees e
        LEFT JOIN locations l ON l.location_id = e.location_id
        WHERE e.employee_id = %s
        """,
        [employee_id],
    )
    if not row:
        return {"found": False, "employee_id": employee_id, "error": "EMPLOYEE_NOT_FOUND"}
    if row.get("hire_date"):
        row["hire_date"] = str(row["hire_date"])
    row["remote_eligible"] = bool(row.get("remote_eligible"))
    row["in_probation"] = (row.get("months_of_service") or 0) < 3
    row["found"] = True
    return row


def check_pto_balance(employee_id: str, days_requested: float = 0.0,
                      start_date: str | None = None) -> dict[str, Any]:
    """Live PTO balance in days, and whether a request fits.

    Reads pto_accruals joined to pto_balance_as_of(CURRENT_DATE). The balance is
    computed from carryover, elapsed accrual, days taken and days pending — it is
    never read from a stored column, so it cannot go stale. POL-001 s2.1 accrual,
    s3.1 notice and approval, s4.1 carryover.
    """
    row = _sql_one(
        """
        SELECT a.employee_id, a.plan, a.accrual_days_per_month, a.carryover_days,
               a.taken_days_this_year, a.pending_days,
               b.accrued_days, b.available_days,
               CURRENT_DATE AS as_of
        FROM pto_accruals a
        JOIN pto_balance_as_of(CURRENT_DATE) b ON b.employee_id = a.employee_id
        WHERE a.employee_id = %s
        """,
        [employee_id],
    )
    if not row:
        return {"found": False, "employee_id": employee_id, "error": "NO_PTO_RECORD"}

    result = dict(row)
    result["as_of"] = str(result.get("as_of"))
    result["policy_refs"] = ["POL-001 s2.1", "POL-001 s3.1", "POL-001 s4.1"]
    for key in ("accrual_days_per_month", "carryover_days", "taken_days_this_year",
                "pending_days", "accrued_days", "available_days"):
        if result.get(key) is not None:
            result[key] = float(result[key])

    result["found"] = True
    if result["plan"] == "NOT_ELIGIBLE":
        result.update({
            "sufficient": False,
            "reason": "Contractors are not eligible for paid time off (POL-001 s1).",
        })
        return result

    if days_requested:
        result["sufficient"] = result["available_days"] >= days_requested
        result["shortfall_days"] = max(0.0, round(days_requested - result["available_days"], 2))
        # POL-001 3.1: 3 days or more needs manager approval, 5 business days notice.
        result["requires_manager_approval"] = days_requested >= 3
        result["notice_business_days_required"] = 5
        if start_date:
            result["start_date"] = start_date
    return result


def lookup_benefits_status(employee_id: str, benefit: str | None = None) -> dict[str, Any]:
    """Return the benefits election for one employee, with the reason for it.

    benefits_class is one of FULL, RETIREMENT_ONLY or NOT_ELIGIBLE. Contractors
    are not eligible and part-time under 30 hrs/week is retirement only
    (POL-007 s1.2), which is what the reason field records.
    """
    record = _sql_one("SELECT * FROM benefits WHERE employee_id = %s", [employee_id])
    if not record:
        return {"found": False, "employee_id": employee_id, "error": "NO_BENEFITS_RECORD"}
    profile = _sql_one(
        "SELECT employment_type, scheduled_hours_per_week, home_country "
        "FROM employees WHERE employee_id = %s",
        [employee_id],
    )
    for key in ("coverage_start", "enrollment_deadline"):
        if record.get(key):
            record[key] = str(record[key])
    record["found"] = True
    record["employment_type"] = profile.get("employment_type") if profile else None
    record["scheduled_hours_per_week"] = (profile.get("scheduled_hours_per_week")
                                          if profile else None)
    record["policy_refs"] = ["POL-007 s1.1", "POL-007 s1.2"]
    if record.get("benefits_class") == "NOT_ELIGIBLE":
        record["escalate"] = "Confirm engagement terms with People Operations (POL-007 s1.2)."
    elif record.get("benefits_class") == "RETIREMENT_ONLY":
        record["escalate"] = ("Retirement contribution only; no medical, dental or vision "
                              "(POL-007 s1.2).")
    return record


def check_policy_compliance(
    employee_id: str,
    check_type: str,
    days_requested: float = 0.0,
    destination_country: str | None = None,
    duration_days: int = 0,
    amount_usd: float = 0.0,
) -> dict[str, Any]:
    """Deterministic policy checks. Returns a route and a real citation.

    check_type accepts: 'pto', 'remote_work', 'expense', 'benefits'.

    For remote_work the branches are, in order: role not eligible (POL-003 s3),
    over 90 days (POL-004 s2.3), over 30 days abroad (POL-004 s2.2), over 30 days
    domestic (POL-003 s4.2), otherwise manager approval (POL-003 s4.1 or
    POL-004 s2.1). An unnamed destination means the home country, per POL-004
    s1.2 — absent is not the same as unknown.
    """
    profile = lookup_employee_profile(employee_id)
    if not profile.get("found"):
        return {"compliant": False, "reason": "unknown employee", "employee_id": employee_id}

    if check_type == "pto":
        balance = check_pto_balance(employee_id, days_requested)
        sufficient = bool(balance.get("sufficient", False))
        return {
            "compliant": sufficient,
            "check_type": "pto",
            "employee_id": employee_id,
            "requested_days": days_requested,
            "available_days": balance.get("available_days"),
            "requires_manager_approval": days_requested >= 3,
            "reason": ("Balance covers the request." if sufficient
                       else f"Short by {balance.get('shortfall_days')} days."),
            "policy_document_id": "POL-001",
            "policy_section_id": "3.1" if days_requested >= 3 else "2.1",
            "policy_refs": ["POL-001 s2.1", "POL-001 s3.1", "POL-001 s4.1"],
        }

    if check_type == "remote_work":
        # POL-003 3: role eligibility gates everything else.
        if not profile["remote_eligible"]:
            return {
                "compliant": False, "check_type": "remote_work", "employee_id": employee_id,
                "route": "INELIGIBLE",
                "reason": ("This role is not remote-eligible, or is designated on-site "
                           "(POL-003 s3)."),
                "policy_document_id": "POL-003", "policy_section_id": "3",
                "policy_refs": ["POL-003 s3"],
            }
        home = profile.get("home_country") or "US"
        # An unnamed destination means staying in the home country (POL-004 s1.2).
        destination = destination_country or home
        cross_border = destination != home

        if duration_days > 90:
            return {
                "compliant": False, "check_type": "remote_work", "employee_id": employee_id,
                "destination_country": destination, "duration_days": duration_days,
                "route": "DECLINED",
                "reason": "Over 90 consecutive days is normally declined (POL-004 s2.3).",
                "policy_document_id": "POL-004", "policy_section_id": "2.3",
                "policy_refs": ["POL-004 s2.3"],
            }
        if duration_days > 30 and cross_border:
            return {
                "compliant": None, "check_type": "remote_work", "employee_id": employee_id,
                "destination_country": destination, "duration_days": duration_days,
                "route": "PEOPLE_OPS_AND_LEGAL",
                "reason": ("International work over 30 consecutive days needs People Operations "
                           "and Legal approval before travel is booked (POL-004 s2.2)."),
                "conditions": [
                    "Connect only through the VPN with multi-factor authentication (POL-006 s3.3).",
                    "Do not store company data on local drives or personal cloud accounts (POL-006 s2.2).",
                    "Submit at least 30 days ahead so payroll can assess withholding (POL-004 s3.1).",
                    "Confirm the destination is not on the restricted list (POL-004 s4).",
                ],
                "policy_document_id": "POL-004", "policy_section_id": "2.2",
                "policy_refs": ["POL-004 s2.2", "POL-006 s3.3", "POL-006 s2.2", "POL-003 s4.3"],
            }
        if duration_days > 30:
            return {
                "compliant": None, "check_type": "remote_work", "employee_id": employee_id,
                "destination_country": destination, "duration_days": duration_days,
                "route": "PEOPLE_OPS_REVIEW",
                "reason": ("Over 30 consecutive days in another US state requires People "
                           "Operations review for payroll registration (POL-003 s4.2)."),
                "policy_document_id": "POL-003", "policy_section_id": "4.2",
                "policy_refs": ["POL-003 s4.2", "POL-004 s3.1"],
            }
        return {
            "compliant": True, "check_type": "remote_work", "employee_id": employee_id,
            "destination_country": destination, "duration_days": duration_days,
            "route": "MANAGER_APPROVAL",
            "reason": ("Up to 30 consecutive days is approved by the manager "
                       + ("(POL-004 s2.1)." if cross_border else "(POL-003 s4.1).")),
            "policy_document_id": "POL-004" if cross_border else "POL-003",
            "policy_section_id": "2.1" if cross_border else "4.1",
            "policy_refs": (["POL-004 s2.1"] if cross_border
                            else ["POL-003 s4.1", "POL-003 s5"]),
        }

    if check_type == "expense":
        if amount_usd >= 1000:
            return {
                "compliant": None, "check_type": "expense", "amount_usd": amount_usd,
                "route": "NEEDS_PRE_APPROVAL",
                "reason": ("Any single expense above $1000 needs manager approval in advance "
                           "(POL-005 s1)."),
                "policy_document_id": "POL-005", "policy_section_id": "1",
                "policy_refs": ["POL-005 s1", "POL-005 s2.1"],
            }
        return {
            "compliant": True, "check_type": "expense", "amount_usd": amount_usd,
            "route": "CLAIM_WITH_RECEIPT",
            "reason": "Submit within 30 days with a receipt (POL-005 s5).",
            "policy_document_id": "POL-005", "policy_section_id": "5",
            "policy_refs": ["POL-005 s5", "POL-005 s2.1"],
        }

    if check_type == "benefits":
        record = lookup_benefits_status(employee_id)
        return {
            "compliant": record.get("benefits_class") == "FULL",
            "check_type": "benefits",
            "employee_id": employee_id,
            "benefits_class": record.get("benefits_class"),
            "reason": record.get("reason") or "Standard eligibility applies (POL-007 s1.1).",
            "policy_document_id": "POL-007", "policy_section_id": "1.2",
            "policy_refs": ["POL-007 s1.1", "POL-007 s1.2"],
        }

    return {"compliant": False, "reason": f"unsupported check_type {check_type}",
            "supported": ["pto", "remote_work", "expense", "benefits"]}


# --------------------------------------------------------------- mock action
def draft_hr_email(employee_id: str, topic: str,
                   body_points: list[str] | None = None) -> dict[str, Any]:
    """Compose a MOCK email draft. Nothing is sent.

    Returns the draft text with the manager on record named, and sent always
    false. The agent must show the draft rather than claim it was delivered.
    """
    profile = lookup_employee_profile(employee_id)
    name = profile.get("display_name", employee_id)
    manager = profile.get("manager_id")
    points = body_points or []
    draft = (
        f"Subject: {topic}\n\n"
        f"Hi {name},\n\n"
        + ("\n".join(f"- {point}" for point in points) if points else "")
        + f"\n\nManager on record: {manager or 'n/a'}\n"
        + "\nThis is a mock draft only. No email was sent.\n"
    )
    return {"draft": draft, "sent": False, "employee_id": employee_id, "to_role": "manager"}


def create_mock_hr_ticket(employee_id: str, category: str, summary: str,
                          confirm: bool = False) -> dict[str, Any]:
    """MOCK HR ticket. Requires confirm=True before anything is written.

    With confirm=False this returns a preview and writes nothing, which is the
    step that lets the agent ask the user first. Only a confirmed call inserts,
    and the row is stamped is_mock and confirmed_by_user. ticket_id is assigned
    by the database (identity column, migration 006).
    """
    preview = {"employee_id": employee_id, "category": category,
               "summary": summary, "is_mock": True}
    if not confirm:
        return {
            "status": "awaiting_confirmation",
            "preview": preview,
            "message": ("No ticket was created. Ask the user to confirm, then call again "
                        "with confirm=true."),
        }
    profile = lookup_employee_profile(employee_id)
    if not profile.get("found"):
        return {"status": "rejected", "error": "EMPLOYEE_NOT_FOUND", "employee_id": employee_id}

    if using_data_api():
        row = _sql_one(
            """
            INSERT INTO tickets (employee_id, subject, status, category,
                                 summary, is_mock, confirmed_by_user)
            VALUES (%s, %s, 'MOCK_OPEN', %s, %s, TRUE, TRUE)
            RETURNING ticket_id
            """,
            [employee_id, summary[:120], category, summary],
        )
    else:
        with connection() as conn:
            row = dict(conn.execute(
                """
                INSERT INTO tickets (employee_id, subject, status, category,
                                     summary, is_mock, confirmed_by_user)
                VALUES (%s, %s, 'MOCK_OPEN', %s, %s, TRUE, TRUE)
                RETURNING ticket_id
                """,
                (employee_id, summary[:120], category, summary),
            ).fetchone())

    ticket_id = (row or {}).get("ticket_id")
    return {"status": "created_mock",
            "ticket_id": f"MOCK-{int(ticket_id):04d}" if ticket_id else "MOCK-????",
            **preview,
            "note": "Mock record only; no real HR system was touched."}
