"""Persist one row per prompt so a transaction can be reconstructed."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from quantic_hr.db import execute


def new_prompt_id() -> str:
    """Short, URL-safe, quotable in a demo without being unwieldy."""
    return uuid.uuid4().hex[:12]


def persist_prompt(prompt_id: str, employee_id: str, question: str,
                   result: dict[str, Any], latency_ms: int,
                   cold_start: bool = False) -> None:
    """Write one completed prompt. Never raises."""
    try:
        route = None
        for step in result.get("steps", []):
            if step.get("kind") == "decision":
                route = step.get("detail")
                break

        tools = result.get("tool_trace", []) or []

        execute(
            """
            INSERT INTO agent_runs
              (prompt_id, thread_id, user_message, answer, trace, citations,
               escalation, latency_ms, cold_start, route, tool_names, step_count, model)
            VALUES
              (:p1, :p2, :p3, :p4, :p5::jsonb, :p6::jsonb, :p7, :p8, :p9,
               :p10, :p11, :p12, :p13)
            ON CONFLICT (prompt_id) DO NOTHING
            """,
            [
                prompt_id,
                result.get("thread_id"),
                question[:2000],
                (result.get("answer") or "")[:4000],
                json.dumps(result.get("steps", [])),
                json.dumps(result.get("citations", [])),
                bool(result.get("escalation")),
                latency_ms,
                cold_start,
                route,
                ",".join(t.get("name", "") for t in tools),
                len(tools),
                os.environ.get("BEDROCK_CHAT_INFERENCE_PROFILE", "unknown"),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[prompt_log] {prompt_id} persist failed: {type(exc).__name__}: {exc}")
