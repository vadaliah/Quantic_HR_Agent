from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from quantic_hr.agent import run_agent
from quantic_hr.bff import app
from quantic_hr.tools import check_policy_compliance, lookup_employee_profile

# These tests read real rows. Skip wherever no database is listening, rather
# than failing on connect: app.sh exports DATABASE_URL for 127.0.0.1:5433, so
# the variable being set is not evidence that a database is there.
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="no DATABASE_URL; database-backed test skipped",
)


def test_remote_eligibility_for_ny_employee() -> None:
    profile = lookup_employee_profile("E1007")
    assert profile["found"] is True
    assert profile["remote_eligible"] is True
    check = check_policy_compliance("E1007", "remote_work")
    assert check["compliant"] is True


def test_pto_insufficient_for_columbus_employee() -> None:
    # E1019 is the insufficient-balance case, as in evaluation case Q15.
    check = check_policy_compliance("E1019", "pto", days_requested=3)
    assert check["compliant"] is False


def test_langgraph_remote_workflow_uses_mcp() -> None:
    result = run_agent("Can I work remote from another state?", "E1007")
    names = [item["name"] for item in result["tool_trace"]]
    assert "search_policy_documents" in names
    assert "check_policy_compliance" in names
    assert result["citations"]


def test_health_and_chat_contracts() -> None:
    client = TestClient(app)
    health = client.get("/health").json()
    assert health["runtime"] in ("local", "data-api")
    assert health["mcp"] == "stdio"
    assert health["database"]["ok"] is True
    chat = client.post(
        "/chat", json={"message": "PTO balance and policy", "employee_id": "E1012"}
    ).json()
    assert "answer" in chat
    assert "tool_trace" in chat
    assert "citations" in chat
