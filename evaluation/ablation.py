"""Ablation: retrieval similarity threshold and k vs gold-document recall.

Calls the real search_policy_documents (the MCP tool's code path) against the
live Aurora corpus via the Data API. The threshold is set per run through
QUANTIC_MIN_SIMILARITY, which tools.py reads on every search. Retrieval only:
embedding calls, no chat-model calls.
"""
from __future__ import annotations

import json
import os
import pathlib
import statistics
import time

from evaluation.run_eval import _norm_doc
from quantic_hr import tools

CASES = pathlib.Path("evaluation/eval_set.jsonl")   # CHECK: your eval set path
OUT = pathlib.Path("evaluation/results/ablation.json")
CONFIGS = [
    {"threshold": 0.20, "k": 5},   # deployed default
    {"threshold": 0.35, "k": 5},   # stricter floor
    {"threshold": 0.20, "k": 3},
    {"threshold": 0.20, "k": 8},
]


def run(cfg: dict, cases: list[dict]) -> dict:
    os.environ["QUANTIC_MIN_SIMILARITY"] = str(cfg["threshold"])
    recalls, abstains, lat = [], 0, []
    for c in cases:
        t0 = time.perf_counter()
        res = tools.search_policy_documents(query=c["question"], limit=cfg["k"])
        lat.append((time.perf_counter() - t0) * 1000)
        matches = res.get("matches") or []
        abstains += not matches
        got = {_norm_doc(m["document_id"]).split(":")[0] for m in matches}
        gold = {_norm_doc(d).split(":")[0] for d in c["gold_docs"]}
        recalls.append(len(gold & got) / len(gold))
    return {**cfg, "cases": len(cases),
            "doc_recall": round(statistics.mean(recalls), 3),
            "abstain_rate": round(abstains / len(cases), 3),
            "p50_ms": round(statistics.median(lat))}


def main() -> None:
    cases = [json.loads(l) for l in CASES.read_text().splitlines() if l.strip()]
    cases = [c for c in cases if c.get("gold_docs")]
    print(f"{len(cases)} cases with gold docs")
    rows = [run(cfg, cases) for cfg in CONFIGS]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2))
    print(f"{'thr':>5} {'k':>3} {'recall':>7} {'abstain':>8} {'p50ms':>6}")
    for r in rows:
        print(f"{r['threshold']:>5} {r['k']:>3} {r['doc_recall']:>7} "
              f"{r['abstain_rate']:>8} {r['p50_ms']:>6}")


if __name__ == "__main__":
    main()
