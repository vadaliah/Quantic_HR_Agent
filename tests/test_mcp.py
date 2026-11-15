from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOOLS = {
    "search_policy_documents",
    "get_policy_section",
    "lookup_employee_profile",
    "check_pto_balance",
    "check_policy_compliance",
    "draft_hr_email",
    "lookup_benefits_status",
    "create_mock_hr_ticket"
}


def _payload(result) -> object:
    if result.structuredContent is not None:
        return result.structuredContent
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    return texts[0] if texts else None


@pytest.mark.asyncio
async def test_mcp_lists_eight_tools_without_database() -> None:
    """Start the stdio MCP server and assert list_tools, with no database or AWS.

    The two tests below still need a seeded Postgres and are skipped in CI.
    This test only calls list_tools, so it must run in the offline workflow.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {
            "CLUSTER_ARN",
            "SECRET_ARN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "DATABASE_URL",
        }
    }
    env.update({
        "PYTHONPATH": str(ROOT / "src"),
        "DATABASE_URL": "postgresql://ci-dummy@127.0.0.1:1/ci_dummy",
        "QUANTIC_AGENT_MODE": "keyword",
        "QUANTIC_RETRIEVAL": "keyword",
        "AWS_REGION": "us-east-2",
    })
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "quantic_hr.mcp_server"],
        env=env,
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            assert REQUIRED_TOOLS <= names
            compliance = next(tool for tool in listed.tools if tool.name == "check_policy_compliance")
            properties = (compliance.inputSchema or {}).get("properties") or {}
            assert "days_requested" in properties


@pytest.mark.asyncio
async def test_mcp_discovery_and_calls(database_url: str) -> None:
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
            assert REQUIRED_TOOLS <= names

            profile = _payload(
                await session.call_tool("lookup_employee_profile", {"employee_id": "E1007"})
            )
            assert isinstance(profile, dict)
            inner = profile.get("found", profile)
            if "result" in profile and isinstance(profile["result"], dict):
                inner = profile["result"]
            # FastMCP may wrap as {"found": true, ...} directly or nested.
            blob = str(profile)
            assert "Test User 007" in blob
            assert "true" in blob.lower() or '"found": true' in blob.lower() or profile.get("found") is True

            pto = _payload(await session.call_tool("check_pto_balance", {"employee_id": "E1012"}))
            assert "available_days" in str(pto)


@pytest.mark.asyncio
async def test_mcp_policy_search_returns_corpus_citations(policy_chunks_loaded: str) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "quantic_hr.mcp_server"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "DATABASE_URL": policy_chunks_loaded},
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            search = _payload(
                await session.call_tool("search_policy_documents", {"query": "remote work"})
            )
            assert "POL-003" in str(search)
