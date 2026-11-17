"""Keep the design doc's metric table in step with the committed evaluation run.

Reads evaluation/results/summary.md -- the file the harness already writes -- and
splices a generated table into design-and-evaluation.md between markers:

    <!-- BEGIN METRICS -->
    ...
    <!-- END METRICS -->

The markers are inserted automatically if the doc does not have them yet, placed
after the "## 8." heading. Nothing else in the doc is touched.

    python tools/sync_metrics.py            # rewrite the block
    python tools/sync_metrics.py --check    # fail if the block is stale (CI)
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SUMMARY = Path("evaluation/results/summary.md")
DOC = Path("design-and-evaluation.md")
BEGIN = "<!-- BEGIN METRICS -->"
END = "<!-- END METRICS -->"

# summary.md row label -> label as it should read in the design doc
LABELS = {
    "citation accuracy": "Citation accuracy",
    "tool selection accuracy": "Tool selection accuracy",
    "route accuracy": "Route accuracy",
    "workflow completion rate": "Workflow completion rate",
    "behaviour accuracy": "Behaviour accuracy",
    "latency p50 (ms)": "Latency p50",
    "latency p95 (ms)": "Latency p95",
}

ROW = re.compile(r"^\| ([a-z0-9 ()/.-]+?) \| ([0-9.]+|None) \|\s*$", re.MULTILINE)


def read_summary() -> dict[str, str]:
    """Metric label -> value, straight out of the harness's own summary table."""
    if not SUMMARY.exists():
        sys.exit(f"missing {SUMMARY} -- run the evaluation first")
    found = dict(ROW.findall(SUMMARY.read_text()))
    if not found:
        sys.exit(f"no metric rows parsed from {SUMMARY}")
    return found


def build_block(metrics: dict[str, str]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        BEGIN,
        f"_Measured on the deployed service. Source: "
        f"[`evaluation/results/summary.md`](evaluation/results/summary.md), "
        f"generated {stamp}._",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for key, label in LABELS.items():
        if key in metrics:
            value = metrics[key]
            if label.startswith("Latency"):
                value = f"{value} ms"
            lines.append(f"| {label} | {value} |")
    lines += ["", END]
    return "\n".join(lines)


def splice(doc_text: str, block: str) -> tuple[str, bool]:
    """Replace the marked block. Returns (new_text, changed)."""
    pattern = re.compile(
        rf"{re.escape(BEGIN)}.*?{re.escape(END)}", re.DOTALL)
    if pattern.search(doc_text):
        new = pattern.sub(block, doc_text, count=1)
    else:
        # insert after the "## 8." heading, before the next "## " heading
        anchor = re.search(r"^## 8\..*$", doc_text, re.MULTILINE)
        if not anchor:
            sys.exit("could not find the '## 8.' heading to place the block after")
        new = doc_text[:anchor.end()] + "\n\n" + block + doc_text[anchor.end():]
    return new, new != doc_text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the doc block differs from the summary")
    args = ap.parse_args()

    if not DOC.exists():
        sys.exit(f"missing {DOC}")
    metrics = read_summary()
    block = build_block(metrics)
    text = DOC.read_text()
    updated, changed = splice(text, block)

    if args.check:
        if changed:
            print("design-and-evaluation.md metrics are stale -- run tools/sync_metrics.py")
            return 1
        print("metrics in sync")
        return 0

    if not changed:
        print("already in sync, nothing written")
        return 0
    DOC.write_text(updated)
    print(f"updated {DOC} from {SUMMARY}")
    for key, label in LABELS.items():
        if key in metrics:
            print(f"  {label}: {metrics[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
