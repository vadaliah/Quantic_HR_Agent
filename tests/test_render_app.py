"""Render entry point: UI served at / on the same origin, cheap /ping, env aliases."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from quantic_hr import bedrock


@pytest.fixture
def app_with_ui(tmp_path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "index.html").write_text("<!doctype html><title>Quantic HR</title>")
    monkeypatch.setenv("QUANTIC_STATIC_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://example.onrender.com")
    from quantic_hr import bff

    module = importlib.reload(bff)
    yield module
    monkeypatch.delenv("QUANTIC_STATIC_DIR")
    monkeypatch.delenv("ALLOWED_ORIGINS")
    importlib.reload(bff)


def test_ui_served_at_root_and_api_routes_win(app_with_ui) -> None:
    client = TestClient(app_with_ui.app)
    assert "Quantic HR" in client.get("/").text
    assert client.get("/ping").json() == {"status": "Healthy"}
    assert "https://example.onrender.com" in app_with_ui.allowed_origins()


def test_no_ui_when_static_dir_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTIC_STATIC_DIR", str(tmp_path / "missing"))
    from quantic_hr import bff

    assert bff.static_dir() is None


def test_chat_model_env_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_CHAT_INFERENCE_PROFILE", raising=False)
    monkeypatch.setenv("CHAT_MODEL", "us.anthropic.claude-sonnet-4-6")
    assert bedrock.chat_model_id() == "us.anthropic.claude-sonnet-4-6"
    monkeypatch.delenv("CHAT_MODEL")
    assert bedrock.chat_model_id() == "us.amazon.nova-pro-v1:0"
