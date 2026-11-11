from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest
from fakes import FakeBedrock

from quantic_hr import bedrock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ingest_corpus  # noqa: E402


def test_corpus_has_twelve_policy_documents_with_unique_chunk_ids() -> None:
    documents = ingest_corpus.load_corpus(ROOT / "corpus", 300)
    assert [d.document_id for d in documents] == [f"POL-{n:03d}" for n in range(1, 13)]
    chunk_ids = [c.chunk_id for d in documents for c in d.chunks]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert all(c.content.strip() for d in documents for c in d.chunks)


def test_markdown_and_html_sections_are_numbered() -> None:
    documents = {d.document_id: d for d in ingest_corpus.load_corpus(ROOT / "corpus", 300)}
    pol001 = {c.section_id: c for c in documents["POL-001"].chunks}
    assert "Full-time employees accrue 15 days" in pol001["2.1"].content
    pol004 = {c.section_id: c for c in documents["POL-004"].chunks}
    assert documents["POL-004"].format == "html"
    assert "People Operations and Legal approval" in pol004["2.2"].content
    assert pol004["2.2"].heading == "2.2 More than 30 consecutive days"


def test_long_sections_are_split() -> None:
    parts = ingest_corpus._split_words("\n\n".join(["word " * 50] * 4), max_words=120)
    assert len(parts) == 2


def test_dry_run_makes_no_aws_or_database_call(capsys: pytest.CaptureFixture[str]) -> None:
    bedrock.set_client(FakeBedrock(fail=True))  # any call would raise
    try:
        assert ingest_corpus.main(["--dry-run"]) == 0
    finally:
        bedrock.set_client(None)
    out = capsys.readouterr().out
    assert "12 documents" in out
    assert "dry run" in out


def test_ingest_upserts_embeddings_and_reuses_unchanged(database_url: str, tmp_path: Path) -> None:
    fake = FakeBedrock()
    bedrock.set_client(fake)
    try:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "POL-901_test.md").write_text(
            "# POL-901 Test Policy\n\n## 1. Scope\n\nApplies to testers.\n\n## 2. Rule\n\nTest rule text.\n",
            encoding="utf-8",
        )
        args = ["--corpus", str(corpus), "--database-url", database_url]
        assert ingest_corpus.main(args) == 0
        assert len(fake.invoke_calls) == 2
        with psycopg.connect(database_url) as conn:
            rows = conn.execute(
                "SELECT chunk_id, vector_dims(embedding), token_count FROM policy_chunks "
                "WHERE document_id = 'POL-901' ORDER BY chunk_index"
            ).fetchall()
        assert [(r[0], r[1]) for r in rows] == [("POL-901:1", 1024), ("POL-901:2", 1024)]

        assert ingest_corpus.main(args) == 0
        assert len(fake.invoke_calls) == 2  # unchanged text is not re-embedded

        (corpus / "POL-901_test.md").write_text(
            "# POL-901 Test Policy\n\n## 1. Scope\n\nApplies to testers.\n", encoding="utf-8"
        )
        assert ingest_corpus.main(args) == 0
        with psycopg.connect(database_url) as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT chunk_id FROM policy_chunks WHERE document_id = 'POL-901'"
            ).fetchall()]
        assert ids == ["POL-901:1"]  # stale section removed
    finally:
        bedrock.set_client(None)
        with psycopg.connect(database_url) as conn:
            conn.execute("DELETE FROM policy_chunks WHERE document_id = 'POL-901'")
            conn.execute("DELETE FROM policy_documents WHERE document_id = 'POL-901'")
