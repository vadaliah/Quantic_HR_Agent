"""Fake Bedrock runtime client for offline tests. No AWS call is made."""

from __future__ import annotations

import io
import json
import math
import zlib
from typing import Any


def fake_vector(text: str, dimensions: int = 1024) -> list[float]:
    """Deterministic bag-of-words vector, normalized, so similar text scores higher."""
    vec = [0.0] * dimensions
    for word in text.lower().split():
        word = "".join(ch for ch in word if ch.isalnum())
        if word:
            vec[zlib.crc32(word.encode()) % dimensions] += 1.0  # stable across processes
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeBedrock:
    def __init__(self, converse_responses: list[dict[str, Any]] | None = None, fail: bool = False):
        self.converse_responses = list(converse_responses or [])
        self.converse_calls: list[dict[str, Any]] = []
        self.invoke_calls: list[dict[str, Any]] = []
        self.fail = fail

    def converse(self, **request: Any) -> dict[str, Any]:
        if self.fail:
            raise ConnectionError("simulated Bedrock outage")
        self.converse_calls.append(request)
        return self.converse_responses.pop(0)

    def invoke_model(self, **request: Any) -> dict[str, Any]:
        if self.fail:
            raise ConnectionError("simulated Bedrock outage")
        self.invoke_calls.append(request)
        body = json.loads(request["body"])
        payload = {
            "embedding": fake_vector(body["inputText"], body["dimensions"]),
            "inputTextTokenCount": len(body["inputText"].split()),
        }
        return {"body": io.BytesIO(json.dumps(payload).encode())}


def tool_use(tool_use_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": tool_use_id, "name": name, "input": arguments}}
        ]}},
        "stopReason": "tool_use",
    }


def final_text(text: str) -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
    }
