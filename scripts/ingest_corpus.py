#!/usr/bin/env python3
"""Chunk the policy corpus with LangChain and emit SQL for the Data API runner.

Design notes
------------
Chunk identity is DERIVED, not content-hashed. That is the key decision:

    chunk_id = sha256(f"{document_id}|{section_id}|{chunk_index}")[:16]

Consequences, which are the reason for the choice:

  * Editing a section keeps its chunk_id, so ON CONFLICT DO UPDATE overwrites
    the row in place. No orphans, no duplicates, no growing table.
  * Certification is per document, not per corpus. Compare each document's
    source_sha against the current file hash; only mismatches need re-ingesting.
    Editing 3 of 200 documents means validating 3.
  * A deleted section leaves a stale row, because nothing regenerates it. That
    case is handled explicitly by the reconciliation delete below, scoped to the
    document being re-ingested.

The trade accepted: a superseded chunk is replaced, not versioned. The store
always reflects the current corpus revision, and no history is kept.

Pipeline split (the Data API executes SQL but cannot call Bedrock):
    here  -> chunk + embed + emit .sql
    there -> infrastructure/database/scripts/run-sql.sh that .sql

Usage
-----
    export AWS_REGION=us-east-2
    export AWS_PROFILE=AEA-Sandbox-PowerUser-287238357427

    # parse and chunk only; no Bedrock, no output file
    python scripts/ingest_corpus.py --dry-run

    # full corpus
    python scripts/ingest_corpus.py --out infrastructure/database/migrations/008_policy_vectors.sql

    # one document, the amendment loop
    python scripts/ingest_corpus.py --document POL-004 --out /tmp/pol004.sql

    # plan only: which documents differ from what is in the database
    python scripts/ingest_corpus.py --plan

    # offline smoke test with a stub embedder
    python scripts/ingest_corpus.py --offline --out /tmp/preview.sql

Then apply:
    bash infrastructure/database/scripts/run-sql.sh --check <file>.sql
    QUANTIC_ALLOW_SQL_MIGRATIONS=yes bash infrastructure/database/scripts/run-sql.sh <file>.sql
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "corpus"

EMBED_MODEL = os.environ.get("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
EMBED_DIM = 1024

# ~400 tokens per chunk, ~60 tokens of overlap.
CHUNK_CHARS = 1600
CHUNK_OVERLAP = 240

MARKDOWN = {".md"}
HTML = {".html", ".htm"}
PDF = {".pdf"}


# ------------------------------------------------------------------ loading
def html_to_markdownish(raw: str) -> str:
    """Turn corpus HTML into something the markdown splitter understands.

    The corpus HTML is generated from markdown, so h1/h2/h3 map straight back
    to #/##/### and the numbered headings survive into chunk metadata.
    """
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    for level in (1, 2, 3):
        text = re.sub(
            rf"(?i)<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, n=level: "\n" + "#" * n + " "
            + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n",
            text,
            flags=re.S,
        )
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"(?i)</(p|li|tr|div|article|body)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')):
        text = text.replace(entity, char)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def pdf_to_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is required for PDF sources: uv add pypdf")
    return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def load_document(path: Path) -> str:
    if path.suffix.lower() in HTML:
        return html_to_markdownish(path.read_text(encoding="utf-8"))
    if path.suffix.lower() in PDF:
        return pdf_to_text(path)
    return path.read_text(encoding="utf-8")


def doc_id_from(path: Path) -> str:
    """POL-003_remote_and_hybrid_work.md -> POL-003"""
    return path.stem.split("_")[0]


def source_sha(text: str) -> str:
    """Hash of the extracted document text. Certifies which revision is loaded."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------- chunking
def build_splitters():
    from langchain_text_splitters import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
    )

    headers = [("#", "title"), ("##", "section"), ("###", "subsection")]

    def split(text: str):
        heading_docs = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers, strip_headers=False
        ).split_text(text)
        window = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_CHARS,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", "; ", " "],
        )
        return window.split_documents(heading_docs)

    return split


SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$")


def section_of(chunk) -> tuple[str, str]:
    """Section id and heading from the numbered heading, e.g. '4.3', 'Approval paths'."""
    meta = chunk.metadata or {}
    raw = meta.get("subsection") or meta.get("section") or meta.get("title") or ""
    raw = raw.strip().lstrip("#").strip()
    match = SECTION_RE.match(raw)
    if match:
        return match.group(1), match.group(2).strip()
    return "0", raw


def stable_chunk_id(document_id: str, section_id: str, index: int) -> str:
    """Identity from LOCATION, not content. See the module docstring."""
    return hashlib.sha256(f"{document_id}|{section_id}|{index}".encode()).hexdigest()[:16]


def chunks_for(path: Path, split, corpus_root: Path):
    text = load_document(path)
    doc_id = doc_id_from(path)
    title = next((line.lstrip("# ").strip() for line in text.splitlines()
                  if line.startswith("# ")), path.stem)

    # chunk_index is per section, so inserting a section does not renumber
    # chunks in unrelated sections.
    per_section: dict[str, int] = {}
    out = []
    for chunk in split(text):
        section_id, heading = section_of(chunk)
        body = chunk.page_content.strip()
        if not body:
            continue
        index = per_section.get(section_id, 0)
        per_section[section_id] = index + 1
        content = f"{title} - {heading}\n\n{body}" if heading else f"{title}\n\n{body}"
        out.append({
            "chunk_id": stable_chunk_id(doc_id, section_id, index),
            "document_id": doc_id,
            "section_id": section_id,
            "heading": heading or title,
            "content": content,
            "chunk_index": index,
            "token_count": max(1, len(body) // 4),
            "content_sha": hashlib.sha256(body.encode()).hexdigest()[:16],
            "title": title,
            "source_uri": path.relative_to(corpus_root).as_posix(),
            "source_sha": source_sha(text),
        })
    return out


# ------------------------------------------------------------- embeddings
def make_embedder(offline: bool):
    if offline:
        def stub(texts: list[str]) -> list[list[float]]:
            vectors = []
            for text in texts:
                vec = [0.0] * EMBED_DIM
                for token in re.findall(r"[a-z0-9]+", text.lower()):
                    vec[int(hashlib.sha256(token.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
                norm = sum(v * v for v in vec) ** 0.5 or 1.0
                vectors.append([v / norm for v in vec])
            return vectors
        return stub, "stub"

    from langchain_aws import BedrockEmbeddings

    embedder = BedrockEmbeddings(
        model_id=EMBED_MODEL,
        region_name=os.environ.get("AWS_REGION", "us-east-2"),
    )
    return (lambda texts: embedder.embed_documents(texts)), EMBED_MODEL


# ------------------------------------------------------------------- SQL
def q(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def emit_sql(documents: dict, chunks: list, model_label: str, reconcile: bool) -> str:
    lines = [
        "-- Policy corpus vectors for pgvector search.",
        "-- Generated by scripts/ingest_corpus.py; do not hand-edit.",
        f"-- Embedding model: {model_label} ({EMBED_DIM} dims)",
        "-- Chunk ids are derived from document/section/index, so re-ingesting a",
        "-- document overwrites its rows in place rather than orphaning the old ones.",
        "-- No BEGIN/COMMIT: the Data API runner owns the transaction.",
        "",
    ]

    if reconcile:
        # A section that was deleted leaves a stale row, because nothing
        # regenerates its chunk_id. Remove any chunk of these documents that is
        # not in this batch. Scoped per document, so other documents are untouched.
        for doc_id in sorted(documents):
            keep = ", ".join(q(c["chunk_id"]) for c in chunks if c["document_id"] == doc_id)
            lines.append(
                f"DELETE FROM policy_chunks WHERE document_id = {q(doc_id)} "
                f"AND chunk_id NOT IN ({keep});"
            )
        lines.append("")

    for doc in documents.values():
        lines.append(
            "INSERT INTO policy_documents (document_id, title, source_uri, format, "
            "source_sha, ingested_at, embedding_model) VALUES "
            f"({q(doc['document_id'])}, {q(doc['title'])}, {q(doc['source_uri'])}, "
            f"{q(doc['format'])}, {q(doc['source_sha'])}, now(), {q(model_label)}) "
            "ON CONFLICT (document_id) DO UPDATE SET "
            "title = EXCLUDED.title, source_uri = EXCLUDED.source_uri, "
            "format = EXCLUDED.format, source_sha = EXCLUDED.source_sha, "
            "ingested_at = EXCLUDED.ingested_at, "
            "embedding_model = EXCLUDED.embedding_model;"
        )
    for chunk in chunks:
        lines.append(
            "INSERT INTO policy_chunks (chunk_id, document_id, section_id, heading, content, "
            "token_count, content_sha, chunk_index, embedding, ingested_at) VALUES "
            f"({q(chunk['chunk_id'])}, {q(chunk['document_id'])}, {q(chunk['section_id'])}, "
            f"{q(chunk['heading'])}, {q(chunk['content'])}, {chunk['token_count']}, "
            f"{q(chunk['content_sha'])}, {chunk['chunk_index']}, "
            f"'{vector_literal(chunk['embedding'])}'::vector, now()) "
            "ON CONFLICT (chunk_id) DO UPDATE SET "
            "document_id = EXCLUDED.document_id, section_id = EXCLUDED.section_id, "
            "heading = EXCLUDED.heading, content = EXCLUDED.content, "
            "token_count = EXCLUDED.token_count, content_sha = EXCLUDED.content_sha, "
            "chunk_index = EXCLUDED.chunk_index, embedding = EXCLUDED.embedding, "
            "ingested_at = EXCLUDED.ingested_at;"
        )
    lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ plan
CERTIFY_SQL = """SELECT document_id, source_sha FROM policy_documents ORDER BY document_id;"""


def print_plan(documents: dict) -> int:
    """Compare local source_sha against the database, without embedding anything.

    Requires psycopg and DATABASE_URL. Prints which documents differ, which is
    the whole certification question: only mismatches need re-ingesting.
    """
    try:
        import psycopg
    except ImportError:
        print("psycopg is required for --plan: uv add psycopg", file=sys.stderr)
        return 1

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required for --plan", file=sys.stderr)
        return 1

    with psycopg.connect(url) as conn:
        rows = conn.execute(CERTIFY_SQL).fetchall()
    stored = {r[0]: r[1] for r in rows}

    stale, missing, current = [], [], []
    for doc_id, doc in sorted(documents.items()):
        if doc_id not in stored:
            missing.append(doc_id)
        elif stored[doc_id] != doc["source_sha"]:
            stale.append(doc_id)
        else:
            current.append(doc_id)

    print(f"local corpus: {len(documents)} documents")
    print(f"in database : {len(stored)} documents")
    print()
    if current:
        print(f"CURRENT   ({len(current):2}): {' '.join(current)}")
    if stale:
        print(f"STALE     ({len(stale):2}): {' '.join(stale)}")
    if missing:
        print(f"MISSING   ({len(missing):2}): {' '.join(missing)}")
    orphaned = sorted(set(stored) - set(documents))
    if orphaned:
        print(f"ORPHANED  ({len(orphaned):2}): {' '.join(orphaned)}  (in db, not in corpus)")
    print()
    if stale or missing:
        print("to refresh:")
        for doc_id in stale + missing:
            print(f"  python scripts/ingest_corpus.py --document {doc_id} --out /tmp/{doc_id}.sql")
    else:
        print("PASS: every document's vectors match the current corpus revision")
    return 0


# ------------------------------------------------------------------ main
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument("--out", type=Path, help="SQL file to write; omit for no output")
    parser.add_argument("--document", action="append", metavar="DOC_ID",
                        help="Only these documents, e.g. --document POL-004. Repeatable.")
    parser.add_argument("--dry-run", action="store_true", help="Chunk only; no Bedrock, no file")
    parser.add_argument("--plan", action="store_true",
                        help="Compare local source_sha with the database; no embedding")
    parser.add_argument("--offline", action="store_true", help="Stub embeddings; for pipeline testing")
    parser.add_argument("--batch", type=int, default=32, help="Chunks per embedding call")
    parser.add_argument("--no-reconcile", action="store_true",
                        help="Skip the per-document delete of chunks not in this batch")
    args = parser.parse_args()

    corpus_root = args.corpus or _find_corpus_root()
    if not corpus_root.is_dir():
        print(f"corpus directory not found: {corpus_root}", file=sys.stderr)
        return 1

    files = sorted(
        p for p in corpus_root.rglob("*")
        if p.is_file() and p.suffix.lower() in (MARKDOWN | HTML | PDF)
        and p.name != "SOURCES.md"
    )
    if args.document:
        wanted = {d.upper() for d in args.document}
        files = [p for p in files if doc_id_from(p).upper() in wanted]
        if not files:
            print(f"no files matched {sorted(wanted)}", file=sys.stderr)
            return 1

    split = build_splitters()
    documents: dict[str, dict] = {}
    chunks: list[dict] = []
    for path in files:
        doc_chunks = chunks_for(path, split, corpus_root)
        if not doc_chunks:
            continue
        doc_id = doc_chunks[0]["document_id"]
        documents[doc_id] = {
            "document_id": doc_id,
            "title": doc_chunks[0]["title"],
            "source_uri": doc_chunks[0]["source_uri"],
            "format": path.suffix.lower().lstrip("."),
            "source_sha": doc_chunks[0]["source_sha"],
        }
        chunks.extend(doc_chunks)
        print(f"  {doc_id:9} {len(doc_chunks):3} chunks  sha={doc_chunks[0]['source_sha']}  {path.name}")

    print(f"\n{len(documents)} documents, {len(chunks)} chunks, "
          f"~{sum(c['token_count'] for c in chunks)} tokens")

    if args.plan:
        return print_plan(documents)

    if args.dry_run:
        print("dry run: no embeddings, no SQL written")
        return 0

    embed, label = make_embedder(args.offline)
    print(f"\nembedding {len(chunks)} chunks with {label} ...")
    for start in range(0, len(chunks), args.batch):
        batch = chunks[start:start + args.batch]
        vectors = embed([c["content"] for c in batch])
        if len(vectors) != len(batch):
            print(f"error: asked for {len(batch)} vectors, got {len(vectors)}", file=sys.stderr)
            return 1
        for chunk, vector in zip(batch, vectors):
            chunk["embedding"] = vector
        print(f"  {min(start + args.batch, len(chunks))}/{len(chunks)} embedded")

    for chunk in chunks:
        if len(chunk["embedding"]) != EMBED_DIM:
            print(f"error: chunk {chunk['chunk_id']} has {len(chunk['embedding'])} dims, "
                  f"expected {EMBED_DIM}", file=sys.stderr)
            return 1

    sql = emit_sql(documents, chunks, label, reconcile=not args.no_reconcile)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(sql, encoding="utf-8")
        print(f"\nwrote {args.out}  ({args.out.stat().st_size / 1e6:.1f} MB)")
        print("next:")
        print(f"  bash infrastructure/database/scripts/run-sql.sh --check {args.out}")
        print(f"  QUANTIC_ALLOW_SQL_MIGRATIONS=yes bash infrastructure/database/scripts/run-sql.sh {args.out}")
    else:
        print(f"\n{len(sql)} chars of SQL generated; pass --out to write it")
    return 0


def _find_corpus_root() -> Path:
    """Find corpus/ from the working directory or the script's parents."""
    for candidate in [Path.cwd(), *Path(__file__).resolve().parents]:
        if (candidate / "corpus").is_dir():
            return candidate / "corpus"
    return Path.cwd() / "corpus"


if __name__ == "__main__":
    sys.exit(main())
