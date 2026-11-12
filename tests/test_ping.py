"""The Render health check. This must never touch the database or Bedrock,
so it keeps working while the Aurora cluster is auto-paused."""
from __future__ import annotations

from fastapi.testclient import TestClient

from quantic_hr.bff import app


def test_ping_is_healthy_without_dependencies() -> None:
    response = TestClient(app).get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "Healthy"}
