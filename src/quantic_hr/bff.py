"""FastAPI app: the web UI, the BFF (/chat, /health) and a cheap /ping.

Deployment: one Render web service (render.yaml, Dockerfile.render) serves the
built React UI from QUANTIC_STATIC_DIR at / and the API on the same origin,
listening on $PORT. Render's health check uses /ping, which touches neither the
database nor Bedrock, so it never wakes the auto-paused Aurora cluster.

POST /invocations is the AgentCore Runtime HTTP contract. It is kept for the
record but the AgentCore path is not used (see docs/DEPLOY_RENDER.md).
"""

from __future__ import annotations

import os
from typing import Any

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from quantic_hr import bedrock
from quantic_hr.agent import DEFAULT_EMPLOYEE_ID, agent_mode, run_agent
from quantic_hr.db import connection, db_mode

LOCAL_UI_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


def allowed_origins() -> list[str]:
    """Vite dev origins plus ALLOWED_ORIGINS (comma-separated). Same-origin UI needs none."""
    extra = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return LOCAL_UI_ORIGINS + extra


app = FastAPI(title="Quantic HR BFF", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    employee_id: str = Field(default=DEFAULT_EMPLOYEE_ID)


@app.get("/health")
def health() -> dict:
    db_ok = False
    db_error = None
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
            db_ok = True
    except Exception as exc:  # noqa: BLE001 — health must not raise
        db_error = str(exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "runtime": os.environ.get("QUANTIC_RUNTIME", "local"),
        "mcp": "stdio",
        "agent_mode": agent_mode(),
        "chat_model": bedrock.chat_model_id(),
        "embedding_model": bedrock.embedding_model_id(),
        "database": {"ok": db_ok, "mode": db_mode(), "error": db_error},
        "aws_deploy": os.environ.get("QUANTIC_ALLOW_AWS_DEPLOY", "no"),
    }


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    return run_agent(request.message, request.employee_id)


class InvocationRequest(BaseModel):
    """AgentCore payload (path kept but not used). ``prompt`` per the HTTP contract; ``message`` also accepted."""

    prompt: str | None = None
    message: str | None = None
    employee_id: str = Field(default=DEFAULT_EMPLOYEE_ID)


@app.get("/ping")
def ping() -> dict:
    """Liveness for Render (and AgentCore). Cheap: no database or Bedrock call."""
    return {"status": "Healthy"}


@app.post("/invocations")
def invocations(
    request: InvocationRequest,
    session_id: str | None = Header(default=None, alias="X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"),
) -> dict[str, Any]:
    text = (request.prompt or request.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="prompt is required")
    result = run_agent(text, request.employee_id)
    return {"response": result["answer"], "status": "success", "session_id": session_id, **result}


def static_dir() -> Path | None:
    """Built UI (frontend/dist) to serve at /, if present. Mounted last so API routes win."""
    configured = os.environ.get("QUANTIC_STATIC_DIR")
    path = Path(configured) if configured else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return path if (path / "index.html").is_file() else None


_ui = static_dir()
if _ui is not None:
    app.mount("/", StaticFiles(directory=_ui, html=True), name="ui")
