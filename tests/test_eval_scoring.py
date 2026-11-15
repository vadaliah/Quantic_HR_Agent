"""Offline tests for evaluation citation-id normalisation. No database, no AWS, no /chat."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.run_eval import _norm_doc, rescore_existing, score


EQUIVALENT = [
    "POL-001 2.1",
    "POL-001 s2.1",
    "POL-001s2.1",
    "pol-001s2.1",
    "pol-0012.1",
    "POL-001:2.1",
    "POL-001 §2.1",
]


@pytest.mark.parametrize("ref", EQUIVALENT)
def test_norm_doc_unifies_gold_and_citation_spellings(ref: str) -> None:
    assert _norm_doc(ref) == "pol-001:2.1"


def test_norm_doc_handles_single_digit_sections_and_annex_ids() -> None:
    assert _norm_doc("POL-002 1") == "pol-002:1"
    assert _norm_doc("pol-002s1") == "pol-002:1"
    assert _norm_doc("POL-005A 5") == "pol-005a:5"
    assert _norm_doc("pol-005a5") == "pol-005a:5"


def test_norm_doc_does_not_equate_distinct_annex_section_ids() -> None:
    # Gold "POL-005A 5" is not the same identifier as a citation "POL-005A sA.5".
    assert _norm_doc("POL-005A 5") != _norm_doc("POL-005A sA.5")
    assert _norm_doc("pol-005asa.5") == "pol-005a:a.5"


def test_score_counts_matching_gold_and_tool_citation() -> None:
    case = {"id": "Q01", "question": "?", "gold_docs": ["POL-001 2.1"], "expected_tools": []}
    payload = {
        "answer": "You have enough PTO [POL-001 2.1].",
        "citations": [{"document_id": "POL-001", "section_id": "2.1"}],
        "tool_trace": [],
        "steps": [],
    }
    row = score(case, payload, latency_ms=1000)
    assert row["citation_accuracy"] == 1.0
    assert row["gold_docs"] == ["pol-001:2.1"]
    assert row["citations"] == ["pol-001:2.1"]


def test_score_stays_zero_when_the_cited_section_is_different() -> None:
    case = {"id": "Q08", "question": "?", "gold_docs": ["POL-003 6"], "expected_tools": []}
    payload = {
        "answer": "See policy.",
        "citations": [{"document_id": "POL-003", "section_id": "3"}],
        "tool_trace": [],
        "steps": [],
    }
    row = score(case, payload, latency_ms=1000)
    assert row["citation_accuracy"] == 0.0


def test_rescore_existing_repairs_legacy_normalised_ids(tmp_path: Path) -> None:
    # A saved results row already compacted by the old helper: gold pol-0012.1,
    # citation pol-001s2.1, accuracy 0.0. Re-scoring must not call /chat and
    # must read original gold from eval_set.jsonl for a real case id.
    source = ROOT / "evaluation" / "results" / "results.jsonl"
    if not source.exists():
        pytest.skip("committed results.jsonl is not present")
    first = json.loads(source.read_text().splitlines()[0])
    first["gold_docs"] = ["pol-0012.1"]
    first["citations"] = ["pol-001s2.1"]
    first["citation_accuracy"] = 0.0
    first["id"] = "Q01"
    dest = tmp_path / "results.jsonl"
    dest.write_text(json.dumps(first) + "\n")
    rows = rescore_existing(dest)
    assert rows[0]["citation_accuracy"] == 1.0
    assert rows[0]["gold_docs"] == ["pol-001:2.1"]
    assert "pol-001:2.1" in rows[0]["citations"]
