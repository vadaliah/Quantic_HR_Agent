"""Thin Amazon Bedrock client: Converse with tool use, and Titan v2 embeddings.

Configuration comes from the environment so the app, the MCP server and the
ingest script all use the same single model setting:

- ``BEDROCK_CHAT_INFERENCE_PROFILE``: chat inference profile id (default Nova Pro). Must match the
  CDK context ``quanticChatModel`` so the runtime role allows it.
- ``BEDROCK_EMBEDDING_MODEL``: embedding model id (Titan Text Embeddings v2).
- ``AWS_REGION``: Bedrock region, default ``us-east-2``.

Nothing here runs at import time and no AWS call is made until a function is
used. Tests replace the client with a fake; see ``set_client``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

DEFAULT_REGION = "us-east-2"
DEFAULT_CHAT_INFERENCE_PROFILE = "us.amazon.nova-pro-v1:0"
DEFAULT_EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024  # matches policy_chunks.embedding vector(1024)
TITAN_V2_DIMENSIONS = (256, 512, 1024)


class BedrockUnavailable(RuntimeError):
    """Bedrock could not be reached or returned an error. Callers fall back."""


@dataclass(frozen=True)
class Embedding:
    vector: list[float]
    input_tokens: int | None


_client: Any | None = None


def region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or DEFAULT_REGION


def chat_model_id() -> str:
    return os.environ.get("BEDROCK_CHAT_INFERENCE_PROFILE") or DEFAULT_CHAT_INFERENCE_PROFILE


def embedding_model_id() -> str:
    return os.environ.get("BEDROCK_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL


def set_client(client: Any | None) -> None:
    """Inject a client (tests) or reset to lazy creation with ``None``."""
    global _client
    _client = client


def client() -> Any:
    global _client
    if _client is None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - boto3 is a dependency
            raise BedrockUnavailable("boto3 is not installed") from exc
        _client = boto3.client(
            "bedrock-runtime",
            region_name=region(),
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=60,
            ),
        )
    return _client


def credentials_available() -> bool:
    """True when boto3 can resolve AWS credentials locally. Makes no Bedrock call."""
    if _client is not None:
        return True
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


def tool_spec(name: str, description: str, input_schema: dict[str, Any]) -> dict[str, Any]:
    """Converse toolSpec from an MCP tool's name, description and JSON schema."""
    return {
        "toolSpec": {
            "name": name,
            "description": description or name,
            "inputSchema": {"json": input_schema or {"type": "object", "properties": {}}},
        }
    }


def converse(
    messages: list[dict[str, Any]],
    *,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """One Converse call. Returns the raw response (``output``, ``stopReason``, ``usage``)."""
    request: dict[str, Any] = {
        "modelId": chat_model_id(),
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        request["system"] = [{"text": system}]
    if tools:
        request["toolConfig"] = {"tools": tools}
    try:
        return client().converse(**request)
    except BedrockUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - botocore raises many types
        raise BedrockUnavailable(f"Converse failed: {type(exc).__name__}") from exc


def embed(text: str, *, dimensions: int = EMBEDDING_DIMENSIONS, normalize: bool = True) -> Embedding:
    """Titan Text Embeddings v2. Normalized vectors suit pgvector cosine distance."""
    if dimensions not in TITAN_V2_DIMENSIONS:
        raise ValueError(f"Titan v2 supports {TITAN_V2_DIMENSIONS} dimensions, not {dimensions}")
    body = json.dumps({"inputText": text, "dimensions": dimensions, "normalize": normalize})
    try:
        response = client().invoke_model(
            modelId=embedding_model_id(),
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(response["body"].read())
    except BedrockUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BedrockUnavailable(f"Embedding failed: {type(exc).__name__}") from exc
    vector = payload.get("embedding")
    if not isinstance(vector, list) or len(vector) != dimensions:
        raise BedrockUnavailable("Embedding response had an unexpected shape")
    return Embedding(vector=[float(v) for v in vector], input_tokens=payload.get("inputTextTokenCount"))


def embed_text(text: str, *, dimensions: int = EMBEDDING_DIMENSIONS, normalize: bool = True) -> list[float]:
    return embed(text, dimensions=dimensions, normalize=normalize).vector


def vector_literal(vector: list[float]) -> str:
    """pgvector text form, used with a ``::vector`` cast so no extra driver is needed."""
    return "[" + ",".join(f"{v:.7g}" for v in vector) + "]"


def response_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    return "\n".join(block["text"] for block in content if "text" in block).strip()


def response_tool_uses(response: dict[str, Any]) -> list[dict[str, Any]]:
    content = response.get("output", {}).get("message", {}).get("content", [])
    return [block["toolUse"] for block in content if "toolUse" in block]
