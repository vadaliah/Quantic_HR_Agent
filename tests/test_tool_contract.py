"""MCP tool discovery and schema contract, with no database and no model.

Referenced by design-and-evaluation.md section 10. Runs in CI.
"""
import asyncio

EXPECTED = {
    "search_policy_documents",
    "get_policy_section",
    "lookup_employee_profile",
    "check_pto_balance",
    "lookup_benefits_status",
    "check_policy_compliance",
    "draft_hr_email",
    "create_mock_hr_ticket",
}


def test_mcp_server_exposes_eight_tools(monkeypatch):
    """Discovery: the server publishes all eight tools, each with a schema."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CLUSTER_ARN", raising=False)
    monkeypatch.delenv("SECRET_ARN", raising=False)
    from quantic_hr import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == EXPECTED, f"missing={EXPECTED - names} extra={names - EXPECTED}"
    for t in tools:
        assert t.description, f"{t.name} has no description"
        assert t.inputSchema.get("type") == "object"


def test_tool_names_are_stable(monkeypatch):
    """The vocabulary the prompts and the evaluation set both rely on."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from quantic_hr import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    for required in ("search_policy_documents", "check_policy_compliance",
                     "create_mock_hr_ticket"):
        assert required in names
