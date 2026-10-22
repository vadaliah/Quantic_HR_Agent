"""Pure Hello World payload. No Bedrock, Aurora, MCP, or HR logic."""

from typing import Any


def handle(payload: Any) -> dict[str, Any]:
    prompt = ""
    if isinstance(payload, dict):
        value = payload.get("prompt", payload.get("input", ""))
        prompt = "" if value is None else str(value)
    return {
        "status": "ok",
        "message": "Hello World",
        "echo": prompt,
    }
