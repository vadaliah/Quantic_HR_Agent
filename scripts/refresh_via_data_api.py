#!/usr/bin/env python3
"""Refresh the RAG index over the RDS Data API.

Why this exists as well as refresh_chunks.py.

The Aurora cluster sits in private subnets. Its DNS name resolves to an address
with no route from a laptop: `nc -vz <endpoint> 5432` hangs rather than
refusing. So psycopg cannot reach it, the master password is irrelevant, and a
DATABASE_URL will never connect. That is also why the deployed app reads through
the Data API from Render.

This script writes through the same channel. Every statement - the truncate, the
document upserts, the chunk inserts - goes out as one signed HTTPS call, so it
works from any machine that has AWS credentials and needs no tunnel, no bastion,
no open port and no password.

Usage:
    python scripts/refresh_via_data_api.py --dry-run     # parse and verify: no AWS, no database
    python scripts/refresh_via_data_api.py               # truncate and rebuild
    python scripts/refresh_via_data_api.py --keep-embeddings

Environment (the same values the deployed service uses):
    CLUSTER_ARN        arn:aws:rds:us-east-2:...:cluster:...
    SECRET_ARN         the secret the Data API authenticates with
    DB_NAME            default quantic_hr_agent
    AWS_REGION         default us-east-2
    AWS_PROFILE        your SSO profile, exported in the shell

The secret must be the one that can log into the cluster. If MasterUserSecret is
empty, it is a secret created separately for the application role; list them with
    aws secretsmanager list-secrets --region us-east-2

Notes that matter:

  * The Data API needs `HttpEndpointEnabled: true` on the cluster.
  * `ExecuteStatement` accepts parameters, so the SQL here reuses the same %s
    placeholders as ingest_corpus.py and is rewritten by db.to_named_sql().
  * A vector column cannot be bound as a parameter, so the embedding is
    interpolated into the statement text as a literal. The value comes from
    Titan, not from user input.
  * Statements run in batches through BatchExecuteStatement where the row count
    is large, which is faster and cheaper than one call per chunk.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import ingest_corpus as ingest  # noqa: E402
from quantic_hr import db  # noqa: E402


def cluster_arn() -> str:
    value = os.environ.get("CLUSTER_ARN") or os.environ.get("DB_CLUSTER_ARN") or ""
    if not value:
        sys.exit("CLUSTER_ARN is not set")
    return value


def secret_arn() -> str:
    value = os.environ.get("SECRET_ARN") or os.environ.get("DB_SECRET_ARN") or ""
    if not value:
        sys.exit("SECRET_ARN is not set")
    return value


def client():
    import boto3

    return boto3.client("rds-data", region_name=db.region())


def statement(sql: str, parameters: list | None = None) -> dict:
    """One ExecuteStatement call. Returns the raw response."""
    kwargs = {
        "resourceArn": cluster_arn(),
        "secretArn": secret_arn(),
        "database": db.database_name(),
        "sql": db.to_named_sql(sql),
        "includeResultMetadata": True,
    }
    if parameters:
        kwargs["parameters"] = [
            {"name": f"p{i}", "value": db._field(v)} for i, v in enumerate(parameters, 1)
        ]
    # db.execute() is not usable here: it returns parsed rows and applies the
    # read-only SQL guard, which rejects TRUNCATE and the inserts. This calls the
    # Data API directly, and does not depend on db._execute_with_resume, which
    # exists in some copies of db.py and not others.
    return client().execute_statement(**kwargs)


def rows(response: dict) -> list[dict]:
    columns = [
        c.get("name", f"c{i}") for i, c in enumerate(response.get("columnMetadata", []), 1)
    ]
    return [db._row(fields, columns) for fields in response.get("records", [])]


def batch(statements: list[dict]) -> dict:
    """BatchExecuteStatement, split so one call never carries too much."""
    import boto3

    rds = boto3.client("rds-data", region_name=db.region())
    total = 0
    size = 25
    for start in range(0, len(statements), size):
        window = statements[start:start + size]
        response = rds.batch_execute_statement(
            resourceArn=cluster_arn(),
            secretArn=secret_arn(),
            database=db.database_name(),
            parameterSets=[s["parameters"] for s in window],
            sql=window[0]["sql"],
        )
        total += len(response.get("updateResults", []))
        print(f"    batch {start // size + 1}: {len(window)} statements", flush=True)
    return {"statements": total}


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def chunk_statements(doc: ingest.Document, embedder, carry: dict[str, str]) -> tuple[list[dict], dict]:
    """Build one parameter set per chunk, embedding where needed."""
    stats = {"embedded": 0, "reused": 0, "tokens": 0}
    out: list[dict] = []
    for chunk in doc.chunks:
        literal = carry.get(chunk.content_sha)
        token_count = chunk.estimated_tokens
        if literal:
            stats["reused"] += 1
        else:
            result = embedder(chunk.embedding_input)
            literal = result[0]
            token_count = result[1] or token_count
            stats["embedded"] += 1
            stats["tokens"] += token_count

        # The vector is a literal, not a bound parameter: the Data API cannot
        # bind a pgvector value. Everything else is bound.
        sql = ingest.UPSERT_CHUNK.replace("%s::vector", ":v::vector")
        parameters = [
            {"name": "p1", "value": db._field(chunk.chunk_id)},
            {"name": "p2", "value": db._field(chunk.document_id)},
            {"name": "p3", "value": db._field(chunk.section_id)},
            {"name": "p4", "value": db._field(chunk.heading)},
            {"name": "p5", "value": db._field(chunk.content)},
            {"name": "v", "value": {"stringValue": literal}},
            {"name": "p6", "value": db._field(chunk.chunk_index)},
            {"name": "p7", "value": db._field(token_count)},
            {"name": "p8", "value": db._field(chunk.content_sha)},
        ]
        out.append({
            "sql": db.to_named_sql(sql).replace(":v::vector", ":v::vector"),
            "parameters": parameters,
        })
    return out, stats


def existing_vectors() -> dict[str, str]:
    response = statement(
        "SELECT content_sha, embedding::text FROM policy_chunks WHERE embedding IS NOT NULL"
    )
    return {row["content_sha"]: row["embedding"] for row in rows(response)}


def refresh(documents: list[ingest.Document], *, keep_embeddings: bool) -> dict[str, int]:
    from quantic_hr import bedrock

    stats = {"documents": 0, "chunks": 0, "embedded": 0, "reused": 0, "tokens": 0, "deleted": 0}

    carry: dict[str, str] = {}
    if keep_embeddings:
        carry = existing_vectors()
        print(f"carrying {len(carry)} embeddings across the rebuild")

    counted = rows(statement("SELECT count(*) AS n FROM policy_chunks"))
    stats["deleted"] = counted[0]["n"] if counted else 0
    print(f"truncating policy_chunks ({stats['deleted']} rows)")
    statement("TRUNCATE policy_chunks")

    def embedder(text: str) -> tuple[str, int]:
        result = bedrock.embed(text)
        return vector_literal(result.vector), result.input_tokens or 0

    for doc in documents:
        statement(
            ingest.UPSERT_DOCUMENT,
            [doc.document_id, doc.title, doc.source_uri, doc.format],
        )
        stats["documents"] += 1
        statements, chunk_stats = chunk_statements(doc, embedder, carry)
        stats["embedded"] += chunk_stats["embedded"]
        stats["reused"] += chunk_stats["reused"]
        stats["tokens"] += chunk_stats["tokens"]
        stats["chunks"] += len(statements)
        print(f"  {doc.document_id:<10}{len(statements):>4} chunks", flush=True)
        batch(statements)

    return stats


def report() -> int:
    total = rows(statement("SELECT count(*) AS n FROM policy_chunks"))[0]["n"]
    embedded = rows(
        statement("SELECT count(*) AS n FROM policy_chunks WHERE embedding IS NOT NULL")
    )[0]["n"]
    zero = rows(
        statement("SELECT count(*) AS n FROM policy_chunks WHERE section_id IS NULL OR section_id = '0'")
    )[0]["n"]
    documents = rows(
        statement("SELECT count(DISTINCT document_id) AS n FROM policy_chunks")
    )[0]["n"]

    print(f"\npolicy_chunks: {total} chunks across {documents} documents")
    print(f"  with embeddings: {embedded}")
    print(f"  section_id '0' or null: {zero}")

    if zero or embedded != total:
        print("\nnot clean: see the lines above", file=sys.stderr)
        return 1
    print("\nclean: every chunk has an embedding and a real section id")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=ROOT / "corpus")
    parser.add_argument("--dry-run", action="store_true", help="parse and verify only")
    parser.add_argument("--keep-embeddings", action="store_true")
    parser.add_argument("--max-words", type=int, default=300)
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    documents = ingest.load_corpus(args.corpus, args.max_words)
    total_chunks = sum(len(d.chunks) for d in documents)

    print(f"{'DOC':<10}{'CHUNKS':>7}{'SECTIONS':>10}  SOURCE")
    problems: list[str] = []
    for doc in documents:
        print(
            f"{doc.document_id:<10}{len(doc.chunks):>7}"
            f"{len({c.section_id for c in doc.chunks}):>10}  {doc.source_uri}"
        )
        for chunk in doc.chunks:
            sid = (chunk.section_id or "").strip()
            if sid in ("", "0"):
                problems.append(f"{doc.document_id}: {chunk.chunk_id} section_id={sid!r}")
            if len(chunk.content.split()) < 3:
                problems.append(f"{doc.document_id}: {chunk.chunk_id} has almost no text")
        if not doc.chunks:
            problems.append(f"{doc.document_id}: produced no chunks")

    print(f"\n{len(documents)} documents, {total_chunks} chunks")

    if problems:
        print(f"\n{len(problems)} problem(s); nothing was written:", file=sys.stderr)
        for line in problems[:20]:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("verification: every chunk carries an addressable section id and text")

    if args.dry_run:
        print("dry run: no AWS call, no database write")
        return 0

    if not args.yes:
        answer = input("\nThis truncates policy_chunks and re-embeds the corpus. Continue? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("nothing was written")
            return 0

    started = time.monotonic()
    stats = refresh(documents, keep_embeddings=args.keep_embeddings)
    print(
        "\nrebuilt {documents} documents, {chunks} chunks; embedded {embedded} "
        "({tokens} tokens), reused {reused} in {seconds:.0f}s".format(
            seconds=time.monotonic() - started, **stats
        )
    )
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
