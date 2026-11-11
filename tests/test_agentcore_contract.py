"""AgentCore Runtime HTTP contract adapters and IAM database auth. No AWS or DB call."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from quantic_hr import bff, db


def test_ping_is_healthy_without_dependencies() -> None:
    response = TestClient(bff.app).get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "Healthy"}


def test_invocations_wraps_the_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run_agent(message: str, employee_id: str) -> dict:
        calls.append((message, employee_id))
        return {"answer": "grounded answer", "citations": [], "tool_trace": [], "mode": "keyword"}

    monkeypatch.setattr(bff, "run_agent", fake_run_agent)
    response = TestClient(bff.app).post(
        "/invocations",
        json={"prompt": "How much PTO do I have?", "employee_id": "E1012"},
        headers={"X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": "s-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "grounded answer"
    assert body["status"] == "success"
    assert body["session_id"] == "s-123"
    assert calls == [("How much PTO do I have?", "E1012")]


def test_invocations_requires_a_prompt() -> None:
    assert TestClient(bff.app).post("/invocations", json={}).status_code == 400


def test_database_url_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://x@h/d")
    monkeypatch.setenv("DB_HOST", "ignored")
    assert db.connection_kwargs() == {"conninfo": "postgresql://x@h/d"}


def test_iam_auth_connection_uses_token_and_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "cluster.example.internal")
    monkeypatch.setenv("DB_IAM_AUTH", "true")
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    seen = {}

    def fake_token(host: str, port: int, user: str) -> str:
        seen.update(host=host, port=port, user=user)
        return "signed-token"

    monkeypatch.setattr(db, "iam_auth_token", fake_token)
    kwargs = db.connection_kwargs()
    assert kwargs["password"] == "signed-token"
    assert kwargs["dbname"] == "quantic_hr_agent"
    assert kwargs["user"] == "quantic_hr_agent"
    assert kwargs["sslmode"] == "require"
    assert seen == {"host": "cluster.example.internal", "port": 5432, "user": "quantic_hr_agent"}
