"""Stdio MCP server. Tools talk to local Postgres, not AWS."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from quantic_hr import tools

mcp = FastMCP("quantic-hr")


@mcp.tool()
def search_policy_documents(query: str, limit: int = 5) -> dict[str, Any]:
    """Search synthetic HR policy chunks by keyword and return cited snippets."""
    return tools.search_policy_documents(query, limit)


@mcp.tool()
def get_policy_section(document_id: str, section_id: str) -> dict[str, Any]:
    """Fetch one policy section by document_id and section_id."""
    return tools.get_policy_section(document_id, section_id)


@mcp.tool()
def lookup_employee_profile(employee_id: str) -> dict[str, Any]:
    """Look up a synthetic employee profile, location, and manager id."""
    return tools.lookup_employee_profile(employee_id)


@mcp.tool()
def check_pto_balance(employee_id: str) -> dict[str, Any]:
    """Return synthetic PTO accrual, used, pending, and remaining hours."""
    return tools.check_pto_balance(employee_id)


@mcp.tool()
def check_policy_compliance(
    employee_id: str,
    check_type: str,
    requested_hours: float = 0,
    destination_region: str | None = None,
) -> dict[str, Any]:
    """Deterministic remote-work or PTO compliance check against synthetic data."""
    return tools.check_policy_compliance(
        employee_id,
        check_type,
        requested_hours=requested_hours,
        destination_region=destination_region,
    )


@mcp.tool()
def draft_hr_email(employee_id: str, topic: str, body_points: list[str] | None = None) -> dict[str, Any]:
    """Draft a mock HR email. Does not send mail or change records."""
    return tools.draft_hr_email(employee_id, topic, body_points)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
