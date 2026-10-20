from __future__ import annotations

from typing import Any

from quantic_hr.db import connection


def lookup_employee_profile(employee_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT e.employee_id, e.display_name, e.email, e.employment_type,
                   e.manager_id, l.location_id, l.name AS location_name,
                   l.region, l.remote_eligible
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
    with connection() as conn:
        row = conn.execute(
            """
            SELECT employee_id, annual_hours, used_hours, pending_hours,
                   (annual_hours - used_hours - pending_hours) AS remaining_hours
            FROM pto_balances
            WHERE employee_id = %s
            """,
            (employee_id,),
        ).fetchone()
    if not row:
        return {"found": False, "employee_id": employee_id}
    return {"found": True, **{k: float(v) if k != "employee_id" else v for k, v in row.items()}}


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
) -> dict[str, Any]:
    profile = lookup_employee_profile(employee_id)
    if not profile.get("found"):
        return {"compliant": False, "reason": "unknown employee", "employee_id": employee_id}

    if check_type == "remote_work":
        eligible = bool(profile["remote_eligible"])
        same_region = destination_region is None or destination_region == profile["region"]
        compliant = eligible and same_region
        return {
            "compliant": compliant,
            "check_type": check_type,
            "employee_id": employee_id,
            "remote_eligible": eligible,
            "employee_region": profile["region"],
            "destination_region": destination_region,
            "reason": "location is remote-eligible" if compliant else "location or region is not remote-eligible",
            "policy_document_id": "remote-work-policy",
            "policy_section_id": "eligibility",
        }

    if check_type == "pto":
        balance = check_pto_balance(employee_id)
        remaining = float(balance.get("remaining_hours") or 0)
        compliant = remaining >= requested_hours
        return {
            "compliant": compliant,
            "check_type": check_type,
            "employee_id": employee_id,
            "requested_hours": requested_hours,
            "remaining_hours": remaining,
            "reason": "sufficient PTO balance" if compliant else "insufficient PTO balance",
            "policy_document_id": "pto-policy",
            "policy_section_id": "accrual",
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
