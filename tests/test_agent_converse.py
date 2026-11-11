"""Converse tool-use loop with a fake Bedrock client and the real stdio MCP server."""

from __future__ import annotations

import pytest
from fakes import FakeBedrock, final_text, tool_use

from quantic_hr import agent, bedrock


@pytest.fixture
def bedrock_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QUANTIC_AGENT_MODE", "bedrock")
    monkeypatch.setenv("BEDROCK_CHAT_INFERENCE_PROFILE", "us.anthropic.claude-sonnet-4-6")
    yield
    bedrock.set_client(None)


def test_mode_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTIC_AGENT_MODE", "keyword")
    assert agent.use_bedrock() is False
    monkeypatch.setenv("QUANTIC_AGENT_MODE", "bedrock")
    assert agent.use_bedrock() is True
    monkeypatch.setenv("QUANTIC_AGENT_MODE", "nonsense")
    assert agent.agent_mode() == "auto"


def test_converse_loop_calls_mcp_tools_and_cites(policy_chunks_loaded: str, bedrock_mode) -> None:
    fake = FakeBedrock(
        [
            tool_use("t1", "search_policy_documents", {"query": "remote work"}),
            tool_use(
                "t2", "check_policy_compliance",
                {"employee_id": "E1025", "check_type": "remote_work"},  # not the session user
            ),
            final_text("Yes, you are remote-eligible [POL-003 3]."),
        ]
    )
    bedrock.set_client(fake)
    result = agent.run_agent("Can I work remotely?", "E1007")

    assert result["mode"] == "bedrock"
    assert result["model"] == "us.anthropic.claude-sonnet-4-6"
    assert result["abstained"] is False
    assert result["answer"] == "Yes, you are remote-eligible [POL-003 3]."
    names = [t["name"] for t in result["tool_trace"]]
    assert names == ["search_policy_documents", "check_policy_compliance"]
    assert result["tool_trace"][1]["arguments"]["employee_id"] == "E1007"
    assert any(c["document_id"] == "POL-003" for c in result["citations"])

    first = fake.converse_calls[0]
    tool_names = {t["toolSpec"]["name"] for t in first["toolConfig"]["tools"]}
    assert {"search_policy_documents", "check_pto_balance", "check_policy_compliance"} <= tool_names
    assert "E1007" in first["messages"][0]["content"][0]["text"]
    tool_result = fake.converse_calls[1]["messages"][-1]["content"][0]["toolResult"]
    assert tool_result["toolUseId"] == "t1"
    assert tool_result["status"] == "success"


def test_abstains_when_nothing_grounds_the_answer(policy_chunks_loaded: str, bedrock_mode) -> None:
    bedrock.set_client(
        FakeBedrock(
            [
                tool_use("t1", "search_policy_documents", {"query": "zzqx yacht allowance"}),
                final_text("Sure, everyone gets a yacht allowance."),
            ]
        )
    )
    result = agent.run_agent("Do I get a yacht allowance?", "E1007")
    assert result["mode"] == "bedrock"
    assert result["abstained"] is True
    assert result["answer"] == agent.ABSTAIN_MESSAGE
    assert result["citations"] == []


def test_falls_back_to_keyword_router_when_bedrock_fails(database_url: str, bedrock_mode) -> None:
    bedrock.set_client(FakeBedrock(fail=True))
    result = agent.run_agent("PTO balance and policy", "E1012")
    assert result["mode"] == "keyword"
    assert "Converse failed" in (result["fallback_reason"] or "")
    assert "check_pto_balance" in [t["name"] for t in result["tool_trace"]]
