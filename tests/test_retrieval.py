from __future__ import annotations

import psycopg
import pytest

from fakes import FakeBedrock, fake_vector
from quantic_hr import bedrock, tools

ROWS = [
    ("POL-902:1", "1", "1. Remote work", "Remote work eligibility for hybrid employees."),
    ("POL-902:2", "2", "2. Receipts", "Submit expense receipts within thirty days."),
]


@pytest.fixture
def embedded_rows(database_url: str):
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "INSERT INTO policy_documents (document_id, title, source_uri) VALUES "
            "('POL-902', 'POL-902 Test', 'corpus/test') ON CONFLICT DO NOTHING"
        )
        for index, (chunk_id, section, heading, content) in enumerate(ROWS):
            conn.execute(
                "INSERT INTO policy_chunks (chunk_id, document_id, section_id, heading, content, embedding, chunk_index) "
                "VALUES (%s, 'POL-902', %s, %s, %s, %s::vector, %s)",
                (chunk_id, section, heading, content, bedrock.vector_literal(fake_vector(content)), index),
            )
    yield
    with psycopg.connect(database_url) as conn:
        conn.execute("DELETE FROM policy_chunks WHERE document_id = 'POL-902'")
        conn.execute("DELETE FROM policy_documents WHERE document_id = 'POL-902'")


@pytest.fixture
def fake_bedrock(monkeypatch: pytest.MonkeyPatch):
    fake = FakeBedrock()
    bedrock.set_client(fake)
    monkeypatch.setenv("QUANTIC_RETRIEVAL", "auto")
    yield fake
    bedrock.set_client(None)


def test_vector_search_ranks_by_cosine_and_drops_weak_matches(embedded_rows, fake_bedrock) -> None:
    result = tools.search_policy_documents("remote work eligibility for hybrid employees")
    assert result["retrieval"] == "vector"
    ids = [m["chunk_id"] for m in result["matches"]]
    assert "POL-902:1" in ids
    assert "POL-902:2" not in ids  # below QUANTIC_MIN_SIMILARITY
    assert len(fake_bedrock.invoke_calls) == 1


def test_falls_back_to_keyword_when_bedrock_fails(embedded_rows, monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock.set_client(FakeBedrock(fail=True))
    monkeypatch.setenv("QUANTIC_RETRIEVAL", "auto")
    try:
        result = tools.search_policy_documents("expense receipts")
    finally:
        bedrock.set_client(None)
    assert result["retrieval"] == "keyword"
    assert "Embedding failed" in result["fallback_reason"]
    assert "POL-902:2" in [m["chunk_id"] for m in result["matches"]]


def test_vector_mode_raises_instead_of_falling_back(embedded_rows, monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock.set_client(FakeBedrock(fail=True))
    monkeypatch.setenv("QUANTIC_RETRIEVAL", "vector")
    try:
        with pytest.raises(bedrock.BedrockUnavailable):
            tools.search_policy_documents("expense receipts")
    finally:
        bedrock.set_client(None)


def test_keyword_fallback_matches_terms_of_a_question(policy_chunks_loaded: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTIC_RETRIEVAL", "keyword")
    result = tools.search_policy_documents("Can I work remote from another state?")
    assert result["retrieval"] == "keyword"
    assert any(m["document_id"] == "POL-003" for m in result["matches"])
