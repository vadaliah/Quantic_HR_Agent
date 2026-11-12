"""Serve the latest evaluation run to the dashboard.

Reads evaluation/results/results.jsonl, the file run_eval.py writes on every
run. Nothing is cached, so the dashboard always shows the newest results.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evaluation" / "results" / "results.jsonl"
SUMMARY = ROOT / "evaluation" / "results" / "summary.md"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def load_results() -> dict[str, Any]:
    """Latest results, or an empty payload explaining what is missing."""
    if not RESULTS.exists():
        return {
            "available": False,
            "reason": "no evaluation run found",
            "expected_path": str(RESULTS.relative_to(ROOT)),
            "rows": [],
        }

    rows: list[dict] = []
    for line in RESULTS.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a truncated final line is not worth failing the page for

    stat = RESULTS.stat()
    summary = SUMMARY.read_text(encoding="utf-8") if SUMMARY.exists() else ""
    return {
        "available": bool(rows),
        "rows": rows,
        "count": len(rows),
        "path": str(RESULTS.relative_to(ROOT)),
        "modified": int(stat.st_mtime),
        "modified_iso": _iso(stat.st_mtime),
        "summary_markdown": summary,
    }
