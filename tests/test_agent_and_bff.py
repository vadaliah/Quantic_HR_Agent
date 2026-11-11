from __future__ import annotations

from fastapi.testclient import TestClient

from quantic_hr.agent import run_agent
from quantic_hr.bff import app
from quantic_hr.tools import check_policy_compliance, check_pto_balance, lookup_employee_profile

# Seed IDs from mock_data/: E1007 remote-eligible (NY), E1001 onsite (NY),
# E1012 PTO covers three days, E1019 insufficient PTO, E1004 contractor.


def test_remote_eligibility_for_ny_remote_employee(database_url: str) -> None:
    profile = lookup_employee_profile("E1007")
    assert profile["found"] is True
    assert profile["display_name"] == "Test User 007"
    assert profile["remote_eligible"] is True
    check = check_policy_compliance("E1007", "remote_work")
    assert check["compliant"] is True
    assert check["policy_document_id"] == "POL-003"


def test_onsite_employee_is_not_remote_eligible(database_url: str) -> None:
    check = check_policy_compliance("E1001", "remote_work")
    assert check["compliant"] is False
    assert check["remote_eligible"] is False


def test_remote_from_another_state_needs_approval(database_url: str) -> None:
    check = check_policy_compliance("E1007", "remote_work", destination_region="CA")
    assert check["compliant"] is False
    assert check["policy_section_id"] == "4.2"


def test_pto_balance_reads_accruals_in_days(database_url: str) -> None:
    balance = check_pto_balance("E1012")
    assert balance["found"] is True
    assert balance["plan"] == "FULL_TIME_STANDARD"
    assert balance["as_of"] == "2026-11-03"
    assert balance["available_days"] > 3


def test_pto_sufficient_and_insufficient_paths(database_url: str) -> None:
    ok = check_policy_compliance("E1012", "pto", requested_days=3)
    assert ok["compliant"] is True
    assert ok["manager_approval_required"] is True
    short = check_policy_compliance("E1019", "pto", requested_days=3)
    assert short["compliant"] is False
    contractor = check_policy_compliance("E1004", "pto", requested_days=1)
    assert contractor["compliant"] is False
    assert contractor["reason"] == "not eligible for paid time off"


def test_langgraph_remote_workflow_uses_mcp(database_url: str) -> None:
    result = run_agent("Can I work remote from another state?", "E1007")
    names = [item["name"] for item in result["tool_trace"]]
    assert "lookup_employee_profile" in names
    assert "search_policy_documents" in names
    assert "check_policy_compliance" in names
    assert result["citations"]
    assert "MCP tool" in result["answer"]


def test_health_and_chat_contracts(database_url: str) -> None:
    client = TestClient(app)
    health = client.get("/health").json()
    assert health["runtime"] == "local"
    assert health["mcp"] == "stdio"
    assert health["database"]["ok"] is True
    chat = client.post("/chat", json={"message": "PTO balance and policy", "employee_id": "E1012"}).json()
    assert "answer" in chat
    assert "tool_trace" in chat
    assert "citations" in chat
    names = [item["name"] for item in chat["tool_trace"]]
    assert "check_pto_balance" in names
