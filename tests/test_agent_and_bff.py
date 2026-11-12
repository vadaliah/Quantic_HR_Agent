"""Agent, orchestrator and BFF behaviour.

These read real rows, so they are opt-in. Set QUANTIC_TEST_DB=1 with a seeded
Postgres to run them:

    docker run -d --name quantic-pg -p 5433:5432 \
      -e POSTGRES_USER=quantic -e POSTGRES_PASSWORD=quantic \
      -e POSTGRES_DB=quantic_hr pgvector/pgvector:pg16
    QUANTIC_TEST_DB=1 DATABASE_URL=postgresql://quantic:quantic@127.0.0.1:5433/quantic_hr \
      PYTHONPATH=src uv run pytest -q

Why an explicit opt-in rather than a check on DATABASE_URL: app.sh exports a
URL pointing at 127.0.0.1:5433, so the variable being set says nothing about
whether a database is listening. Keying off it made these fail on connect
instead of skipping.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from quantic_hr.agent import run_agent
from quantic_hr.bff import app
from quantic_hr.tools import check_policy_compliance, lookup_employee_profile

pytestmark = pytest.mark.skipif(
    os.getenv("QUANTIC_TEST_DB") != "1",
    reason="set QUANTIC_TEST_DB=1 with a seeded Postgres to run these",
)


def test_remote_eligibility_is_answered_with_citations() -> None:
    """E1007 is remote-eligible; the policy check should say so and cite POL-003."""
    profile = lookup_employee_profile("E1007")
    assert profile["found"] is True
    assert profile["remote_eligible"] is True

    check = check_policy_compliance("E1007", "remote_work")
    assert check["compliant"] is True
    assert check["policy_document_id"].startswith("POL-")


def test_pto_insufficient_balance_is_reported() -> None:
    """E1019 carries an insufficient balance, as in evaluation case Q15."""
    check = check_policy_compliance("E1019", "pto", days_requested=3)
    assert check["compliant"] is False
    assert check["route"] == "INSUFFICIENT"


def test_sufficient_balance_routes_to_manager_approval() -> None:
    """E1012 has enough balance, as in evaluation case Q14. Three days or more
    still needs manager approval."""
    check = check_policy_compliance("E1012", "pto", days_requested=3)
    assert check["compliant"] is True
    assert check["route"] == "MANAGER_APPROVAL"


def test_agent_calls_mcp_tools_and_returns_citations() -> None:
    """The agent must go through the MCP layer, not call tools directly."""
    result = run_agent("Can I work remote from another state?", "E1007")
    names = [item["name"] for item in result["tool_trace"]]

    assert "search_policy_documents" in names
    assert result["citations"], "an answer with no citations is not grounded"
    for citation in result["citations"]:
        assert citation["document_id"].startswith("POL-")


def test_health_reports_components() -> None:
    client = TestClient(app)
    health = client.get("/health").json()

    assert health["runtime"] in ("local", "data-api")
    assert health["mcp"] == "stdio"
    assert health["database"]["ok"] is True


def test_chat_returns_answer_trace_and_citations() -> None:
    client = TestClient(app)
    chat = client.post(
        "/chat",
        json={"message": "Can I take 3 days of PTO next week?", "employee_id": "E1012"},
    ).json()

    assert chat["answer"]
    assert "tool_trace" in chat
    assert "citations" in chat
    assert "thread_id" in chat
    assert "prompt_id" in chat

    names = [item["name"] for item in chat["tool_trace"]]
    assert "check_pto_balance" in names
