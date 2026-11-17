"""Keep the design doc's metrics honest.

Two checks, both cheap and both offline:

1. The marked block in design-and-evaluation.md matches the committed summary.
2. No line in the doc quotes a metric figure that is not the committed one.

These exist because a stale figure is invisible: the doc said citation accuracy
0.409 for a day while the harness wrote 0.318 to evaluation/results/. A number a
human copied and a number a script produced cannot be kept in step by vigilance,
only by a check that fails.

Runs in CI against the committed files, so it needs no database and no network.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "evaluation" / "results" / "summary.md"
DOC = ROOT / "design-and-evaluation.md"
BEGIN = "<!-- BEGIN METRICS -->"
END = "<!-- END METRICS -->"

# summary.md row label -> the doc label that must carry the same figure
LABELS = {
    "citation accuracy": "Citation accuracy",
    "tool selection accuracy": "Tool selection accuracy",
    "route accuracy": "Route accuracy",
    "workflow completion rate": "Workflow completion rate",
    "behaviour accuracy": "Behaviour accuracy",
}

ROW = re.compile(r"^\| ([a-z0-9 ()/.-]+?) \| ([0-9.]+|None) \|\s*$", re.MULTILINE)


def _summary_metrics() -> dict[str, str]:
    if not SUMMARY.exists():
        pytest.skip(f"{SUMMARY} not present")
    found = dict(ROW.findall(SUMMARY.read_text()))
    if not found:
        pytest.skip(f"no metric rows parsed from {SUMMARY}")
    return found


def _doc() -> str:
    if not DOC.exists():
        pytest.skip(f"{DOC} not present")
    return DOC.read_text()


def test_marked_block_matches_summary():
    """The generated block, if the doc has one, carries the committed figures."""
    text = _doc()
    if BEGIN not in text or END not in text:
        pytest.skip("doc has no metrics markers yet; run tools/sync_metrics.py")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    metrics = _summary_metrics()
    for key, label in LABELS.items():
        if key not in metrics:
            continue
        assert re.search(rf"\|\s*{re.escape(label)}\s*\|\s*{re.escape(metrics[key])}\s*\|",
                         block), (
            f"{label} in the doc block is not {metrics[key]} as in {SUMMARY.name}")


def test_doc_quotes_no_stale_figure():
    """Every metric labelled in the doc carries the committed value.

    Catches the hand-written tables outside the generated block too, which is
    where the 0.409 survived.
    """
    text = _doc()
    metrics = _summary_metrics()
    stale = []
    for key, label in LABELS.items():
        if key not in metrics:
            continue
        want = metrics[key]
        # any "| Label | <number> |" row for this metric
        for m in re.finditer(rf"\|\s*{re.escape(label)}\s*\|\s*([0-9.]+|None)\s*\|", text):
            if m.group(1) != want:
                line = text[: m.start()].count("\n") + 1
                stale.append(f"line {line}: {label} = {m.group(1)}, summary says {want}")
    assert not stale, "stale metric figures in the design doc:\n  " + "\n  ".join(stale)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
