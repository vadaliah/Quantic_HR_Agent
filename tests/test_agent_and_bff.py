from __future__ import annotations

import os

from fastapi.testclient import TestClient

from quantic_hr.agent import run_agent
from quantic_hr.bff import app
from quantic_hr.tools import check_policy_compliance, lookup_employee_profile


def test_remote_eligibility_for_ny_employee() -> None:
    profile = lookup_employee_profile("E001")
    assert profile["found"] is True
    assert profile["remote_eligible"] is True
    check = check_policy_compliance("E001", "remote_work")
    assert check["compliant"] is True


def test_pto_insufficient_for_columbus_employee() -> None:
    check = check_policy_compliance("E002", "pto", requested_hours=16)
    assert check["compliant"] is False


def test_langgraph_remote_workflow_uses_mcp() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql://quantic@127.0.0.1:5433/quantic_hr")
    result = run_agent("Can I work remote from another state?", "E001")
    names = [item["name"] for item in result["tool_trace"]]
    assert "lookup_employee_profile" in names
    assert "search_policy_documents" in names
    assert "check_policy_compliance" in names
    assert result["citations"]
    assert "MCP tool" in result["answer"]


def test_health_and_chat_contracts() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql://quantic@127.0.0.1:5433/quantic_hr")
    client = TestClient(app)
    health = client.get("/health").json()
    assert health["runtime"] == "local"
    assert health["mcp"] == "stdio"
    assert health["database"]["ok"] is True
    chat = client.post("/chat", json={"message": "PTO balance and policy", "employee_id": "E002"}).json()
    assert "answer" in chat
    assert "tool_trace" in chat
    assert "citations" in chat
    names = [item["name"] for item in chat["tool_trace"]]
    assert "check_pto_balance" in names
