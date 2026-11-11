#!/usr/bin/env python3
"""Chunk the policy corpus, embed it with Titan Text Embeddings v2, and upsert it.

Writes policy_documents and policy_chunks exactly as defined by migrations 002
and 004 (embedding vector(1024), chunk_index, token_count, content_sha, format).
Run as the ADMIN database user: migration 005 leaves the runtime role read-only.

Usage:
    python scripts/ingest_corpus.py --dry-run          # parse + chunk only: no AWS, no database
    python scripts/ingest_corpus.py                    # embed changed chunks and upsert
    python scripts/ingest_corpus.py --force            # re-embed every chunk
    python scripts/ingest_corpus.py --skip-embeddings  # text only (keyword search), no AWS

Chunks are one per numbered policy section (## or ### / <h2> or <h3>), split
further only if a section exceeds --max-words. chunk_id is "<document>:<section>"
so re-running updates rows in place; content_sha skips re-embedding unchanged
text, and chunks that no longer exist in a document are deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DOC_ID_RE = re.compile(r"^(POL-\d{3})")
SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$")


@dataclass
class Section:
    level: int
    heading: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    section_id: str
    heading: str
    content: str
    chunk_index: int
    title: str

    @property
    def content_sha(self) -> str:
        return hashlib.sha256(self.embedding_input.encode("utf-8")).hexdigest()

    @property
    def embedding_input(self) -> str:
        return f"{self.title}\n{self.heading}\n\n{self.content}"

    @property
    def estimated_tokens(self) -> int:
        return max(1, round(len(self.embedding_input) / 4))


@dataclass
class Document:
    document_id: str
    title: str
    source_uri: str
    format: str
    chunks: list[Chunk]


def _clean(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_markdown(text: str) -> list[Section]:
    sections: list[Section] = []
    for raw in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if match:
            sections.append(Section(len(match.group(1)), _clean(match.group(2))))
        elif sections:
            sections[-1].lines.append(re.sub(r"\*\*(.+?)\*\*", r"\1", raw.rstrip()))
    return sections


class _HtmlSections(HTMLParser):
    BLOCKS = {"p", "li", "td", "th", "dd", "dt"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[Section] = []
        self._heading_level: int | None = None
        self._buffer: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self._in_title = True
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self._heading_level = int(tag[1])
        elif tag in self.BLOCKS or tag == "br":
            self._flush()
            if tag == "li":
                self._buffer.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif re.fullmatch(r"h[1-6]", tag) and self._heading_level is not None:
            self.sections.append(Section(self._heading_level, _clean("".join(self._buffer))))
            self._buffer = []
            self._heading_level = None
        elif tag in self.BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._in_title:
            self._buffer.append(data.replace("\n", " "))

    def _flush(self) -> None:
        if self._heading_level is not None:
            return
        text = _clean("".join(self._buffer))
        self._buffer = []
        if text and text != "-" and self.sections:
            self.sections[-1].lines.append(text)


def parse_html(text: str) -> list[Section]:
    parser = _HtmlSections()
    parser.feed(text)
    parser.close()
    parser._flush()
    return parser.sections


def _split_words(text: str, max_words: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    parts, current = [], []
    for paragraph in text.split("\n\n"):
        if current and len(" ".join(current + [paragraph]).split()) > max_words:
            parts.append("\n\n".join(current))
            current = []
        current.append(paragraph)
    if current:
        parts.append("\n\n".join(current))
    return parts


def load_document(path: Path, corpus_root: Path, max_words: int) -> Document:
    match = DOC_ID_RE.match(path.name)
    if not match:
        raise ValueError(f"{path.name}: file name must start with POL-NNN")
    document_id = match.group(1)
    text = path.read_text(encoding="utf-8")
    fmt = "html" if path.suffix.lower() in {".html", ".htm"} else "md"
    sections = parse_html(text) if fmt == "html" else parse_markdown(text)
    h1 = next((s.heading for s in sections if s.level == 1), document_id)
    title = h1

    chunks: list[Chunk] = []
    for section in sections:
        if section.level not in (2, 3):
            continue  # h1 holds only the document metadata block
        body = "\n".join(section.lines).strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        if not body:
            continue  # a parent heading whose text lives in its subsections
        numbered = SECTION_RE.match(section.heading)
        section_id = numbered.group(1) if numbered else re.sub(r"\W+", "-", section.heading.lower()).strip("-")
        parts = _split_words(body, max_words)
        for part_number, part in enumerate(parts, start=1):
            suffix = f":{part_number}" if len(parts) > 1 else ""
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}:{section_id}{suffix}",
                    document_id=document_id,
                    section_id=section_id,
                    heading=section.heading,
                    content=part,
                    chunk_index=len(chunks),
                    title=title,
                )
            )
    return Document(
        document_id=document_id,
        title=title,
        source_uri=path.relative_to(corpus_root.parent).as_posix(),
        format=fmt,
        chunks=chunks,
    )


def discover(corpus: Path) -> list[Path]:
    files = [
        p for p in corpus.rglob("POL-*")
        if p.is_file() and p.suffix.lower() in {".md", ".html", ".htm"}
    ]
    return sorted(files, key=lambda p: p.name)


def load_corpus(corpus: Path, max_words: int) -> list[Document]:
    documents = [load_document(path, corpus, max_words) for path in discover(corpus)]
    seen: dict[str, str] = {}
    for doc in documents:
        if doc.document_id in seen:
            raise ValueError(f"duplicate {doc.document_id}: {seen[doc.document_id]} and {doc.source_uri}")
        seen[doc.document_id] = doc.source_uri
    return documents


UPSERT_DOCUMENT = """
INSERT INTO policy_documents (document_id, title, source_uri, format)
VALUES (%s, %s, %s, %s)
ON CONFLICT (document_id) DO UPDATE
SET title = EXCLUDED.title, source_uri = EXCLUDED.source_uri, format = EXCLUDED.format
"""

# Keep an existing embedding when the text is unchanged and no new one was computed.
UPSERT_CHUNK = """
INSERT INTO policy_chunks
  (chunk_id, document_id, section_id, heading, content, embedding, chunk_index, token_count, content_sha)
VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s)
ON CONFLICT (chunk_id) DO UPDATE SET
  document_id = EXCLUDED.document_id,
  section_id = EXCLUDED.section_id,
  heading = EXCLUDED.heading,
  content = EXCLUDED.content,
  embedding = CASE
    WHEN policy_chunks.content_sha = EXCLUDED.content_sha
      THEN COALESCE(EXCLUDED.embedding, policy_chunks.embedding)
    ELSE EXCLUDED.embedding
  END,
  chunk_index = EXCLUDED.chunk_index,
  token_count = COALESCE(EXCLUDED.token_count, policy_chunks.token_count),
  content_sha = EXCLUDED.content_sha
"""


def write(documents: list[Document], *, database_url: str, embed: bool, force: bool) -> dict[str, int]:
    import psycopg

    from quantic_hr import bedrock

    stats = {"documents": 0, "chunks": 0, "embedded": 0, "reused": 0, "deleted": 0, "tokens": 0}
    with psycopg.connect(database_url) as conn:
        existing = {
            row[0]: (row[1], row[2])
            for row in conn.execute(
                "SELECT chunk_id, content_sha, embedding IS NOT NULL FROM policy_chunks"
            ).fetchall()
        }
        for doc in documents:
            conn.execute(UPSERT_DOCUMENT, (doc.document_id, doc.title, doc.source_uri, doc.format))
            stats["documents"] += 1
            for chunk in doc.chunks:
                vector_text = None
                token_count = None
                previous = existing.get(chunk.chunk_id)
                unchanged = previous is not None and previous[0] == chunk.content_sha and previous[1]
                if embed and (force or not unchanged):
                    result = bedrock.embed(chunk.embedding_input)
                    vector_text = bedrock.vector_literal(result.vector)
                    token_count = result.input_tokens or chunk.estimated_tokens
                    stats["embedded"] += 1
                    stats["tokens"] += token_count
                elif unchanged:
                    stats["reused"] += 1
                conn.execute(
                    UPSERT_CHUNK,
                    (
                        chunk.chunk_id, chunk.document_id, chunk.section_id, chunk.heading,
                        chunk.content, vector_text, chunk.chunk_index,
                        token_count if token_count is not None else chunk.estimated_tokens,
                        chunk.content_sha,
                    ),
                )
                stats["chunks"] += 1
            deleted = conn.execute(
                "DELETE FROM policy_chunks WHERE document_id = %s AND NOT (chunk_id = ANY(%s))",
                (doc.document_id, [c.chunk_id for c in doc.chunks]),
            )
            stats["deleted"] += deleted.rowcount or 0
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=ROOT / "corpus")
    parser.add_argument("--dry-run", action="store_true", help="parse and chunk only; no AWS, no database")
    parser.add_argument("--skip-embeddings", action="store_true", help="write text without embeddings; no AWS")
    parser.add_argument("--force", action="store_true", help="re-embed every chunk")
    parser.add_argument("--max-words", type=int, default=300)
    parser.add_argument("--database-url", default=None, help="defaults to $DATABASE_URL")
    args = parser.parse_args(argv)

    documents = load_corpus(args.corpus, args.max_words)
    total_chunks = sum(len(d.chunks) for d in documents)
    total_tokens = sum(c.estimated_tokens for d in documents for c in d.chunks)
    for doc in documents:
        print(f"{doc.document_id}  {len(doc.chunks):>3} chunks  {doc.source_uri}")
    print(f"{len(documents)} documents, {total_chunks} chunks, ~{total_tokens} tokens to embed (estimate)")

    if args.dry_run:
        print("dry run: no AWS call, no database write")
        return 0

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set (use the admin user; see README)", file=sys.stderr)
        return 2
    stats = write(documents, database_url=database_url, embed=not args.skip_embeddings, force=args.force)
    print(
        "wrote {documents} documents, {chunks} chunks; embedded {embedded} "
        "({tokens} tokens), reused {reused}, deleted {deleted} stale".format(**stats)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
