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
}


def _payload(result) -> object:
    if result.structuredContent is not None:
        return result.structuredContent
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    return texts[0] if texts else None


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://quantic@127.0.0.1:5433/quantic_hr")
    os.environ["DATABASE_URL"] = url
    return url


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
                await session.call_tool("lookup_employee_profile", {"employee_id": "E001"})
            )
            assert isinstance(profile, dict)
            inner = profile.get("found", profile)
            if "result" in profile and isinstance(profile["result"], dict):
                inner = profile["result"]
            # FastMCP may wrap as {"found": true, ...} directly or nested.
            blob = str(profile)
            assert "Amina Cole" in blob
            assert "true" in blob.lower() or '"found": true' in blob.lower() or profile.get("found") is True

            search = _payload(
                await session.call_tool("search_policy_documents", {"query": "remote work"})
            )
            assert "remote-work-policy" in str(search)
