from __future__ import annotations

import os
from typing import Any

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
            result[key] = value.isoformat()
        else:
            result[key] = float(value)
    result["policy_document_id"] = "POL-001"
    result["policy_section_id"] = "2.1"
    return result


def search_policy_documents(query: str, limit: int = 5) -> dict[str, Any]:
    like = f"%{query}%"
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.document_id, c.section_id, c.heading, c.content,
                   d.title, d.source_uri
            FROM policy_chunks c
            JOIN policy_documents d ON d.document_id = c.document_id
            WHERE c.content ILIKE %s OR c.heading ILIKE %s OR d.title ILIKE %s
            ORDER BY c.document_id, c.section_id
            LIMIT %s
            """,
            (like, like, like, limit),
        ).fetchall()
    return {"query": query, "matches": rows}


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


def check_policy_compliance(
    employee_id: str,
    check_type: str,
    requested_hours: float = 0,
    destination_region: str | None = None,
    requested_days: float = 0,
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
