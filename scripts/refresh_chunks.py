#!/usr/bin/env python3
"""Full refresh of the RAG index: rebuild policy_chunks from corpus/ from scratch.

Why this exists as well as ingest_corpus.py.

ingest_corpus.py upserts by chunk_id and deletes only the chunks of a document it
just processed. That is right for routine updates, and wrong for a rebuild:

  * A document removed from corpus/ keeps its rows, so the index serves policy
    that no longer exists.
  * The section-id fix renumbers chunks ("POL-001A:0" becomes "POL-001A:A.1"),
    so after re-ingesting, the old rows are still there and the same passage is
    retrievable twice under two ids.
  * An interrupted run leaves a partially populated table with old and new rows
    mixed.

This script is destructive by design and says so. It parses and chunks first,
checks the result, and only then opens a transaction.

Usage:
    python scripts/refresh_chunks.py --dry-run        # parse, chunk, verify: no AWS, no database
    python scripts/refresh_chunks.py --keep-embeddings # re-use vectors for unchanged text
    python scripts/refresh_chunks.py                  # delete policy_chunks and re-embed everything

Run as the ADMIN database user: migration 005 leaves the runtime role read-only.
Expect 1-3 minutes for a corpus this size, most of it Titan embedding.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import ingest_corpus as ingest  # noqa: E402


TRUNCATE = "TRUNCATE policy_chunks"
COUNTS = "SELECT document_id, count(*) FROM policy_chunks GROUP BY document_id ORDER BY document_id"
EMBEDDED = "SELECT count(*) FROM policy_chunks WHERE embedding IS NOT NULL"
ORPHAN_DOCS = """
SELECT c.document_id, count(*)
FROM policy_chunks c
LEFT JOIN policy_documents d ON d.document_id = c.document_id
WHERE d.document_id IS NULL
GROUP BY c.document_id
"""


def summarise(documents: list[ingest.Document]) -> None:
    """Print what will be written, before anything is written."""
    total_chunks = sum(len(d.chunks) for d in documents)
    total_sections = sum(len({c.section_id for c in d.chunks}) for d in documents)
    print(f"{len(documents)} documents, {total_chunks} chunks, {total_sections} distinct sections")
    print()
    print(f"{'DOC':<10}{'CHUNKS':>7}{'SECTIONS':>10}  SOURCE")
    for doc in documents:
        print(
            f"{doc.document_id:<10}{len(doc.chunks):>7}"
            f"{len({c.section_id for c in doc.chunks}):>10}  {doc.source_uri}"
        )


def verify(documents: list[ingest.Document]) -> int:
    """Refuse the write if the parsed corpus has any structural problem."""
    problems: list[str] = []

    for doc in documents:
        for chunk in doc.chunks:
            sid = (chunk.section_id or "").strip()
            if sid in ("", "0"):
                problems.append(f"{doc.document_id}: chunk {chunk.chunk_id} has section_id {sid!r}")
            if len(chunk.content.split()) < 3:
                problems.append(f"{doc.document_id}: chunk {chunk.chunk_id} has almost no text")
        if not doc.chunks:
            problems.append(f"{doc.document_id}: produced no chunks ({doc.source_uri})")

    # Every section the parser found must be openable in the source document.
    for doc in documents:
        source = ROOT / doc.source_uri
        if not source.exists():
            problems.append(f"{doc.document_id}: source file missing at {source}")
            continue
        text = source.read_text(encoding="utf-8")
        for chunk in doc.chunks:
            sid = (chunk.section_id or "").strip()
            if sid and sid != doc.document_id and sid not in text:
                problems.append(
                    f"{doc.document_id}: section id {sid!r} is not present in {source.name}"
                )

    if problems:
        print(f"\n{len(problems)} problem(s) found; nothing was written:", file=sys.stderr)
        for line in problems[:20]:
            print(f"  {line}", file=sys.stderr)
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more", file=sys.stderr)
        return 1

    print("\nverification: every chunk carries an addressable section id and text")
    return 0


def refresh(
    documents: list[ingest.Document],
    *,
    database_url: str,
    keep_embeddings: bool,
    batch: int,
) -> dict[str, int]:
    """Delete policy_chunks and reload it from the parsed corpus."""
    import psycopg

    from quantic_hr import bedrock

    stats = {"documents": 0, "chunks": 0, "embedded": 0, "reused": 0, "tokens": 0, "deleted": 0}

    with psycopg.connect(database_url) as conn:
        # Vectors are keyed by text hash, so an unchanged section keeps its
        # embedding across the truncate. Read them before deleting anything.
        carry: dict[str, str] = {}
        if keep_embeddings:
            rows = conn.execute(
                "SELECT chunk_id, content_sha, embedding::text FROM policy_chunks "
                "WHERE embedding IS NOT NULL"
            ).fetchall()
            carry = {r[1]: r[2] for r in rows}
            print(f"carrying {len(carry)} embeddings across the rebuild")

        stats["deleted"] = conn.execute("SELECT count(*) FROM policy_chunks").fetchone()[0]
        conn.execute(TRUNCATE)
        print(f"truncated policy_chunks ({stats['deleted']} rows removed)")

        for doc in documents:
            conn.execute(
                ingest.UPSERT_DOCUMENT,
                (doc.document_id, doc.title, doc.source_uri, doc.format),
            )
            stats["documents"] += 1

            for chunk in doc.chunks:
                vector_text = carry.get(chunk.content_sha)
                token_count = chunk.estimated_tokens
                if vector_text:
                    stats["reused"] += 1
                else:
                    result = bedrock.embed(chunk.embedding_input)
                    vector_text = bedrock.vector_literal(result.vector)
                    token_count = result.input_tokens or token_count
                    stats["embedded"] += 1
                    stats["tokens"] += token_count

                conn.execute(
                    ingest.UPSERT_CHUNK,
                    (
                        chunk.chunk_id, chunk.document_id, chunk.section_id, chunk.heading,
                        chunk.content, vector_text, chunk.chunk_index, token_count,
                        chunk.content_sha,
                    ),
                )
                stats["chunks"] += 1

            print(f"  {doc.document_id:<10}{len(doc.chunks):>4} chunks", flush=True)

    return stats


def report(database_url: str) -> int:
    """Read back what landed, and flag rows that no document claims."""
    import psycopg

    with psycopg.connect(database_url) as conn:
        rows = conn.execute(COUNTS).fetchall()
        total = sum(r[1] for r in rows)
        embedded = conn.execute(EMBEDDED).fetchone()[0]
        orphans = conn.execute(ORPHAN_DOCS).fetchall()
        zero = conn.execute(
            "SELECT count(*) FROM policy_chunks WHERE section_id IS NULL OR section_id = '0'"
        ).fetchone()[0]

        print(f"\npolicy_chunks: {total} chunks across {len(rows)} documents")
        print(f"  with embeddings: {embedded}")
        print(f"  section_id '0' or null: {zero}")
        print(f"  chunks whose document is not in policy_documents: {sum(o[1] for o in orphans)}")
        for doc_id, count in orphans[:10]:
            print(f"    orphan: {doc_id} ({count} chunks) -- run ingest, or delete these rows")

        if zero or orphans or embedded != total:
            print("\nnot clean: see the lines above", file=sys.stderr)
            return 1
    print("\nclean: every chunk has a document, an embedding, and a real section id")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=ROOT / "corpus")
    parser.add_argument("--dry-run", action="store_true", help="parse and verify only; no AWS, no database")
    parser.add_argument("--keep-embeddings", action="store_true",
                        help="re-use vectors for text whose hash is unchanged")
    parser.add_argument("--max-words", type=int, default=300)
    parser.add_argument("--database-url", default=None, help="defaults to $DATABASE_URL")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    documents = ingest.load_corpus(args.corpus, args.max_words)
    summarise(documents)
    if verify(documents) != 0:
        return 1

    if args.dry_run:
        print("dry run: no AWS call, no database write")
        return 0

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        print("\nDATABASE_URL is not set (use the admin user; see README)", file=sys.stderr)
        return 2

    if not args.yes:
        answer = input("\nThis deletes every row in policy_chunks and re-embeds the corpus. Continue? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("nothing was written")
            return 0

    stats = refresh(
        documents,
        database_url=database_url,
        keep_embeddings=args.keep_embeddings,
        batch=32,
    )
    print(
        "\nrebuilt {documents} documents, {chunks} chunks; embedded {embedded} "
        "({tokens} tokens), reused {reused}".format(**stats)
    )
    return report(database_url)


if __name__ == "__main__":
    raise SystemExit(main())
