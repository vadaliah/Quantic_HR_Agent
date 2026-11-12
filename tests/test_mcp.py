"""MCP server discovery and tool calls.

Runs the real stdio server and calls tools over the protocol, so it needs a
seeded database. Opt in with QUANTIC_TEST_DB=1:

    QUANTIC_TEST_DB=1 DATABASE_URL=postgresql://quantic:quantic@127.0.0.1:5433/quantic_hr \
      PYTHONPATH=src uv run pytest -q tests/test_mcp.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.skipif(
    os.getenv("QUANTIC_TEST_DB") != "1",
    reason="set QUANTIC_TEST_DB=1 with a seeded Postgres to run these",
)

ROOT = Path(__file__).resolve().parents[1]

# The eight-tool surface the brief requires. The agent must reach all of these
# through the MCP layer, so discovery is part of the contract.
REQUIRED_TOOLS = {
    "search_policy_documents",
    "get_policy_section",
    "lookup_employee_profile",
    "check_pto_balance",
    "lookup_benefits_status",
    "check_policy_compliance",
    "draft_hr_email",
    "create_mock_hr_ticket",
}


def _payload(result) -> object:
    """Prefer structured content; fall back to the first text block."""
    if result.structuredContent is not None:
        return result.structuredContent
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    return texts[0] if texts else None


@pytest.fixture
def database_url() -> str:
    """The URL this run was configured with.

    Deliberately no default: falling back to 127.0.0.1:5433 would let the test
    run against a database that is not there and fail on connect.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.mark.asyncio
async def test_mcp_discovery_lists_all_eight_tools(database_url: str) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "quantic_hr.mcp_server"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "DATABASE_URL": database_url},
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            assert REQUIRED_TOOLS <= names, f"missing tools: {REQUIRED_TOOLS - names}"

            schema = next(t for t in listed.tools if t.name == "check_policy_compliance")
            assert "days_requested" in schema.inputSchema["properties"]
            assert "requested_hours" not in schema.inputSchema["properties"]


@pytest.mark.asyncio
async def test_profile_lookup_returns_a_real_employee(database_url: str) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "quantic_hr.mcp_server"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "DATABASE_URL": database_url},
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "lookup_employee_profile", {"employee_id": "E1007"}
            )
            blob = str(_payload(result))
            assert "E1007" in blob
            assert "EMPLOYEE_NOT_FOUND" not in blob


@pytest.mark.asyncio
async def test_policy_search_returns_real_pol_ids(database_url: str) -> None:
    """Citations must point at corpus documents, not placeholder labels."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "quantic_hr.mcp_server"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "DATABASE_URL": database_url},
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_policy_documents", {"query": "remote work"}
            )
            blob = str(_payload(result))
            assert "POL-" in blob
            # 'remote-work-policy' was a placeholder id from an earlier dataset.
            assert "remote-work-policy" not in blob
