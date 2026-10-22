"""FastAPI BFF. Local only; does not call AgentCore or Bedrock."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from quantic_hr.agent import run_agent
from quantic_hr.db import connection

app = FastAPI(title="Quantic HR BFF", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    employee_id: str = Field(default="E001")


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
        "runtime": "local",
        "mcp": "stdio",
        "database": {"ok": db_ok, "error": db_error},
        "aws_deploy": os.environ.get("QUANTIC_ALLOW_AWS_DEPLOY", "no"),
    }


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    return run_agent(request.message, request.employee_id)
