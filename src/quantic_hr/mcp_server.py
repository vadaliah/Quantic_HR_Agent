"""MCP server: the eight HR tools the agent discovers and calls over stdio.

The docstrings here are the interface the model reads when choosing tools and
arguments, so each one states when to call it, the allowed values, and the
units. Implementations live in tools.py; tests/test_tool_contract.py checks the
two never drift apart.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from quantic_hr import tools

mcp = FastMCP("quantic-hr")


@mcp.tool()
def search_policy_documents(query: str, limit: int = 5) -> dict[str, Any]:
    """Search the Acme Corp HR policy corpus. Call before answering any policy question.

    Args:
        query: Plain-language search, e.g. "home office chair reimbursement".
        limit: Number of passages, 1-8.

    Returns:
        matches: passages with document_id, section_id, heading, content, score.
    """
    return tools.search_policy_documents(query, max(1, min(int(limit), 8)))


@mcp.tool()
def get_policy_section(document_id: str, section_id: str) -> dict[str, Any]:
    """Fetch one policy section by id when a search result needs its full text.

    Args:
        document_id: e.g. "POL-005".
        section_id: e.g. "2.1".
    """
    return tools.get_policy_section(document_id, section_id)


@mcp.tool()
def lookup_employee_profile(employee_id: str) -> dict[str, Any]:
    """Return the signed-in employee's profile: role, employment type, location, work model.

    Args:
        employee_id: The session employee, e.g. "E1007".
    """
    return tools.lookup_employee_profile(employee_id)


@mcp.tool()
def check_pto_balance(employee_id: str) -> dict[str, Any]:
    """Return PTO in DAYS: accrued, carryover, taken, pending, and the balance now.

    `available_days` is the CLOSING balance for today: accrued plus carryover,
    less taken and pending. It is NOT the sum of accrued and carryover, so do not
    present it as a total entitlement. The result carries `available_formula`
    showing the arithmetic; report that formula when you state a balance.

    Args:
        employee_id: The session employee.
    """
    return tools.check_pto_balance(employee_id)


@mcp.tool()
def lookup_benefits_status(employee_id: str) -> dict[str, Any]:
    """Return benefits eligibility and current elections (medical, dental, 401k, FSA/HSA).

    Args:
        employee_id: The session employee.
    """
    return tools.lookup_benefits_status(employee_id)


@mcp.tool()
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
    """Decide whether a request complies with policy. The comparison is computed here.

    Use this for any yes/no or "how much" question about PTO, an expense or remote work.
    Report its `comparison`, `route` and `reason` as given; do not redo the arithmetic.
    If it returns checked=false, say the rule could not be applied; never treat that
    as a "no".

    Args:
        employee_id: The session employee.
        check_type: Exactly one of:
            "pto"         - time off; pass days_requested.
            "expense"     - is a purchase reimbursable; pass amount (USD) and
                            expense_category (e.g. "chair", "desk", "monitor",
                            "internet", "keyboard", "hotel", "meals").
            "remote_work" - working away from home location; pass
                            destination_country (ISO-2, e.g. "PT") or
                            destination_region (US state, e.g. "TX"), and duration_days.
        days_requested: Days of PTO, for "pto".
        amount: Amount in USD, for "expense".
        expense_category: What was bought, for "expense".
        destination_country: ISO-2 country, for "remote_work" abroad.
        destination_region: US state code, for "remote_work" in another state.
        duration_days: Length of the stay in days, for "remote_work". Six weeks = 42.

    Returns:
        checked, compliant (true/false, or null when not checked), route, reason,
        comparison (e.g. "400.00 <= 500.00"), and policy_document_id/policy_section_id.
    """
    return tools.check_policy_compliance(
        employee_id, check_type, days_requested, amount, expense_category,
        destination_country, destination_region, duration_days,
    )


@mcp.tool()
def draft_hr_email(employee_id: str, topic: str, body_points: list[str] | None = None) -> dict[str, Any]:
    """Draft (never send) an email to the employee's manager or HR.

    Args:
        employee_id: The session employee.
        topic: Subject line.
        body_points: Bullet points for the body.
    """
    return tools.draft_hr_email(employee_id, topic, body_points)


@mcp.tool()
def create_mock_hr_ticket(
    employee_id: str, category: str, summary: str, confirm: bool = False
) -> dict[str, Any]:
    """Create a MOCK HR ticket. Requires explicit user confirmation.

    Call first with confirm=false to get a preview and ask the user. Call with
    confirm=true only after the user has said yes in this conversation.

    Args:
        employee_id: The session employee.
        category: One of "pto", "expense", "remote_work", "benefits", "conduct", "other".
        summary: One-paragraph case summary.
        confirm: false returns a preview only; true creates the mock ticket.
    """
    return tools.create_mock_hr_ticket(employee_id, category, summary, confirm)


if __name__ == "__main__":
    mcp.run()
