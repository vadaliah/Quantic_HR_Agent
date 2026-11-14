"""Heading parser for corpus ingestion.

Extracted because of a real defect: every top-level section was stored with
section_id '0', so citations rendered as "POL-002 s0" and scored as retrieval
misses.

Two causes, both fixed here:

  1. The pattern required a space directly after the number, so a heading
     written "## 1. Observed Holidays" (number, dot, space) did not match.
  2. Annex documents number their sections "A.1", "A.2" and also use bare
     capitals, which a digits-only pattern cannot match at all.

Assigning a section_id of '0' must never happen: a citation that reads
"section 0" points at nothing a reader can open.
"""
from __future__ import annotations

import re

# Matches, in order of specificity:
#   3.2.1  subsection
#   3.2    subsection
#   3      top-level, with or without a trailing dot
#   A.1    annex subsection
#   A      annex section
#   IV     roman-numeral annex
SECTION_RE = re.compile(
    r"""^\s*
    (?:
        (?P<num>\d+(?:\.\d+)*)           # 3, 3.2, 3.2.1
      | (?P<annex>[A-Z]\.\d+(?:\.\d+)*)  # A.1, A.2.3
      | (?P<letter>[A-Z])                # A, B
      | (?P<roman>[IVX]{2,4})            # II, IV, XIV
    )
    \.?\s+                               # optional dot, then a space
    (?P<title>\S.*)$                     # the heading text
    """,
    re.VERBOSE,
)

# A heading line in markdown.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# Bold-only lines used as headings in some documents: "**3.2 Lodging**".
BOLD_HEADING_RE = re.compile(r"^\s*(?:\*\*|__)(?P<text>[^*_]{3,80})(?:\*\*|__)\s*$")


def parse_heading(raw: str) -> tuple[str | None, str | None, str]:
    """Return (section_id, title, body_text) for a heading line.

    section_id is None when the line is a heading with no number at all -- a
    document title, or a heading like "Purpose". The caller must treat None as
    "inherits the parent section", never as '0'.

    Accepts markdown ("## 1. Title"), HTML that still carries its tags
    ("<h2>1. Title</h2>"), and bold-only lines ("**1. Title**").
    """
    original = raw
    text = raw.strip()

    match = HEADING_RE.match(text)
    if match:
        text = match.group(2).strip()
    else:
        match = BOLD_HEADING_RE.match(text)
        if not match:
            # Not a heading line, or an HTML heading still carrying its tags.
            text = re.sub(r"^<h[1-6][^>]*>", "", text)
            text = re.sub(r"</h[1-6]>$", "", text).strip()
        else:
            text = match.group("text").strip()

    section = SECTION_RE.match(text)
    if not section:
        # No number: inherits the enclosing section.
        return None, text, original

    section_id = (
        section.group("num")
        or section.group("annex")
        or section.group("letter")
        or section.group("roman")
    )
    title = section.group("title").strip().rstrip(".")
    return section_id, title, original


def inheriting_section_id(section_id: str | None, parent: str | None) -> str | None:
    """Resolve a heading's effective section id.

    A numbered heading starts a new section. An unnumbered heading belongs to
    whatever section encloses it. When neither exists -- text before the first
    heading -- return None, and the caller falls back to the document id.
    """
    if section_id:
        return section_id
    return parent


def assert_no_zero_sections(rows: list[dict]) -> None:
    """Fail the ingest if any chunk carries section_id '0' or an empty value.

    Run this after chunking and before embedding, so the run stops rather than
    loading unaddressable citations into the vector store.
    """
    bad = [r for r in rows if str(r.get("section_id") or "").strip() in ("", "0")]
    if bad:
        sample = ", ".join(
            f"{r.get('document_id')}:{str(r.get('heading', ''))[:40]}" for r in bad[:5]
        )
        raise ValueError(
            f"{len(bad)} chunk(s) have no section id ({sample}). "
            "Every citation must resolve to a section a reader can open."
        )
