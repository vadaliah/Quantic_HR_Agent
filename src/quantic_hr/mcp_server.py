"""Stdio MCP server. Tools reach Postgres; nothing here calls AWS except the
embedding call inside search_policy_documents.

The docstrings below are the tool descriptions the model reads. Each one states
what the tool returns, when to use it, and the policy it maps to — that is what
makes tool selection reliable rather than a guess from the name.
"""
from __future__ import annotations
from quantic_hr.tools import MIN_SCORE

from typing import Any

from mcp.server.fastmcp import FastMCP

from quantic_hr import tools

mcp = FastMCP("quantic-hr")


@mcp.tool()
def search_policy_documents(query: str, limit: int = 5,
                            document_id: str | None = None,
                            min_score: float = MIN_SCORE) -> dict[str, Any]:
    """Search HR policy documents and return cited passages.

    Args:
        query: The user's question in natural language, e.g. 'remote work abroad'.
        limit: Maximum passages to return. 5 is the default.
        document_id: Optional filter, e.g. 'POL-004', to search one document.
        min_score: Relevance floor on cosine similarity. Chunks below it are
            dropped, which is what makes an unrelated question return found=False
            instead of a weak match.

    Returns:
        found: False when nothing met the relevance threshold.
        mode: 'vector' normally; 'error' if the embedding model in use differs
            from the one recorded at ingestion.
        matches: list of dicts with document_id, section_id, heading, snippet,
            score and citation (e.g. 'POL-004 s2.2').

    Use FIRST for any policy question, before answering. If found is False, tell
    the user the policy does not cover the question instead of answering from
    general knowledge.
    """
    kwargs = {} if min_score is None else {"min_score": min_score}
    return tools.search_policy_documents(query, limit, document_id, **kwargs)


@mcp.tool()
def get_policy_section(document_id: str, section_id: str) -> dict[str, Any]:
    """Fetch the full text of one policy section.

    Args:
        document_id: Policy id, e.g. 'POL-003'.
        section_id: Numbered section, e.g. '4.3'.

    Returns:
        found, title, heading, content and citation, or found=False with
        error='SECTION_NOT_FOUND'.

    Use after search_policy_documents when you need the complete wording of a
    section rather than the retrieved snippet.
    """
    return tools.get_policy_section(document_id, section_id)


@mcp.tool()
def lookup_employee_profile(employee_id: str) -> dict[str, Any]:
    """Look up an employee's profile, location, manager and service length.

    Args:
        employee_id: Synthetic id, e.g. 'E1007'.

    Returns:
        display_name, title, department, employment_type, manager_id,
        home_country, remote_eligible, designated_onsite_role, hire_date,
        months_of_service and in_probation (true under 3 months).

    Use when you need to know who is asking, whether their role is
    remote-eligible (POL-003 s3), or whether probation applies (POL-008 s2.2).
    """
    return tools.lookup_employee_profile(employee_id)


@mcp.tool()
def check_pto_balance(employee_id: str, days_requested: float = 0,
                      start_date: str | None = None) -> dict[str, Any]:
    """Check live PTO balance in days and whether a request fits.

    Args:
        employee_id: Synthetic id, e.g. 'E1012'.
        days_requested: Days wanted. 0 returns the balance only.
        start_date: Optional ISO date, e.g. '2026-11-16'.

    Returns:
        plan: 'FULL_TIME_STANDARD', 'PART_TIME_PRORATED' or 'NOT_ELIGIBLE'.
        available_days: Balance as of today, computed from accrual, carryover,
            taken and pending days. Never a stored number.
        sufficient: true when available_days >= days_requested.
        shortfall_days: how many days short, when insufficient.
        requires_manager_approval: true for requests of 3 days or more.

    Use for any time-off question. The answer is not an approval on its own;
    manager approval is separate (POL-001 s3.1).
    """
    return tools.check_pto_balance(employee_id, days_requested, start_date)


@mcp.tool()
def lookup_benefits_status(employee_id: str,
                           benefit: str | None = None) -> dict[str, Any]:
    """Return an employee's benefits election and why it applies.

    Args:
        employee_id: Synthetic id, e.g. 'E1015'.
        benefit: Optional single benefit to focus on, e.g. 'medical' or
            'retirement'. Omit to return the whole election.

    Returns:
        benefits_class: 'FULL', 'RETIREMENT_ONLY' or 'NOT_ELIGIBLE'.
        reason: plain-language explanation, e.g. contractors are not eligible.
        medical_plan, dental, vision, retirement_match_pct, coverage_start.
        escalate: present when the case should go to People Operations.

    Use for benefits eligibility questions. Contractors are not eligible and
    part-time under 30 hrs/week is retirement only (POL-007 s1.2) — say so and
    route to People Operations rather than answering as though full benefits
    apply.
    """
    return tools.lookup_benefits_status(employee_id, benefit)


@mcp.tool()
def check_policy_compliance(
    employee_id: str,
    check_type: str,
    days_requested: float = 0,
    destination_country: str | None = None,
    duration_days: int = 0,
    amount_usd: float = 0,
) -> dict[str, Any]:
    """Run a deterministic policy check and return a decision with citations.

    Args:
        employee_id: Synthetic id, e.g. 'E1007'.
        check_type: One of 'pto', 'remote_work', 'expense', 'benefits'.
        days_requested: For check_type='pto'.
        destination_country: For 'remote_work'. ISO code or free text, e.g. 'PT'
            or 'Portugal'. Omit when the employee is staying where they are.
        duration_days: For 'remote_work'. Total consecutive days away.
        amount_usd: For 'expense'. Any single expense amount.

    Returns:
        compliant: True, False, or None when a human decision is needed.
        route: 'MANAGER_APPROVAL', 'PEOPLE_OPS_AND_LEGAL', 'PEOPLE_OPS_REVIEW',
            'DECLINED', 'INELIGIBLE', 'NEEDS_PRE_APPROVAL', 'CLAIM_WITH_RECEIPT'.
        reason and policy_refs: the citation, e.g. ['POL-004 s2.2'].

    Use when the user asks whether something is allowed. Call
    search_policy_documents first so the final answer can quote the passage.
    For remote work: any destination outside the home country counts as
    international (POL-004 s1.2); over 30 consecutive days abroad needs People
    Operations and Legal (s2.2); over 90 days is normally declined (s2.3).
    """
    return tools.check_policy_compliance(
        employee_id,
        check_type,
        days_requested=days_requested,
        destination_country=destination_country,
        duration_days=duration_days,
        amount_usd=amount_usd,
    )


@mcp.tool()
def draft_hr_email(employee_id: str, topic: str,
                   body_points: list[str] | None = None) -> dict[str, Any]:
    """Draft a mock HR email. Does not send mail or change any record.

    Args:
        employee_id: Who the draft is about.
        topic: Subject line.
        body_points: Bullet points to include.

    Returns:
        draft: the message text, marked as a mock.
        sent: always false.

    Use when the user asks for a message to be drafted, e.g. to their manager.
    Show the draft in the reply; never claim it was sent.
    """
    return tools.draft_hr_email(employee_id, topic, body_points)


@mcp.tool()
def create_mock_hr_ticket(employee_id: str, category: str, summary: str,
                          confirm: bool = False) -> dict[str, Any]:
    """Create a MOCK HR ticket. Requires explicit user confirmation first.

    Args:
        employee_id: Synthetic id.
        category: Short label, e.g. 'PTO_REQUEST' or 'POLICY_QUESTION'.
        summary: What the ticket is about.
        confirm: Must be true to write anything. Leave false on the first call.

    Returns:
        With confirm=False: status='awaiting_confirmation' and a preview of the
        ticket, with nothing written.
        With confirm=True: status='created_mock' and a ticket_id.

    Call with confirm=False first, show the preview to the user, and only call
    again with confirm=True once they agree. Never create a ticket without that
    step.
    """
    return tools.create_mock_hr_ticket(employee_id, category, summary, confirm)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
