from __future__ import annotations

import json

import pytest
from fakes import FakeBedrock, final_text, tool_use

from quantic_hr import bedrock


@pytest.fixture(autouse=True)
def _reset_client():
    yield
    bedrock.set_client(None)


def test_defaults_match_single_model_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_CHAT_INFERENCE_PROFILE", raising=False)
    monkeypatch.delenv("BEDROCK_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert bedrock.chat_model_id() == "us.anthropic.claude-sonnet-4-6"
    assert bedrock.embedding_model_id() == "amazon.titan-embed-text-v2:0"
    assert bedrock.region() == "us-east-2"
    monkeypatch.setenv("BEDROCK_CHAT_INFERENCE_PROFILE", "us.amazon.nova-pro-v1:0")
    assert bedrock.chat_model_id() == "us.amazon.nova-pro-v1:0"


def test_embed_requests_1024_normalized_titan_v2() -> None:
    fake = FakeBedrock()
    bedrock.set_client(fake)
    result = bedrock.embed("How many PTO days do I accrue?")
    assert len(result.vector) == 1024
    assert result.input_tokens == 7
    body = json.loads(fake.invoke_calls[0]["body"])
    assert body == {"inputText": "How many PTO days do I accrue?", "dimensions": 1024, "normalize": True}
    assert fake.invoke_calls[0]["modelId"] == "amazon.titan-embed-text-v2:0"


def test_embed_rejects_unsupported_dimensions() -> None:
    with pytest.raises(ValueError):
        bedrock.embed("x", dimensions=1536)


def test_converse_sends_tools_and_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_CHAT_INFERENCE_PROFILE", "us.anthropic.claude-sonnet-4-6")
    fake = FakeBedrock([tool_use("t1", "check_pto_balance", {"employee_id": "E1012"})])
    bedrock.set_client(fake)
    spec = bedrock.tool_spec("check_pto_balance", "PTO", {"type": "object", "properties": {}})
    response = bedrock.converse(
        [{"role": "user", "content": [{"text": "hi"}]}], system="be grounded", tools=[spec]
    )
    request = fake.converse_calls[0]
    assert request["modelId"] == "us.anthropic.claude-sonnet-4-6"
    assert request["system"] == [{"text": "be grounded"}]
    assert request["toolConfig"]["tools"][0]["toolSpec"]["name"] == "check_pto_balance"
    assert bedrock.response_tool_uses(response)[0]["input"] == {"employee_id": "E1012"}
    assert bedrock.response_text(final_text("done")) == "done"


def test_errors_surface_as_bedrock_unavailable() -> None:
    bedrock.set_client(FakeBedrock(fail=True))
    with pytest.raises(bedrock.BedrockUnavailable):
        bedrock.embed("x")
    with pytest.raises(bedrock.BedrockUnavailable):
        bedrock.converse([{"role": "user", "content": [{"text": "x"}]}])


def test_vector_literal_is_pgvector_text() -> None:
    assert bedrock.vector_literal([0.5, -1.0, 0.25]) == "[0.5,-1,0.25]"
