#!/usr/bin/env python3
"""Run the evaluation set against the local /chat endpoint and record every run.

For each question it captures the full evidence trail the rubric asks to be
visible: the question, the decision path the agent followed, every MCP tool call
with its arguments and returned result, the retrieved policy citations, the
route, and the latency.

It scores what the rubric names:

  answer quality    citation accuracy against the gold documents
  agent behaviour   tool selection, route match, workflow completion,
                    behaviour (answer / escalate / clarify / refuse)
  system            latency p50 and p95

Outputs, all under evaluation/results/:
  results.jsonl     one record per question, with the full trace
  summary.md        metric tables plus a per-question section
  transcripts/      one markdown file per question, for reading the run

Usage:
    python3 evaluation/run_eval.py                  # all 25
    python3 evaluation/run_eval.py --limit 5        # first five
    python3 evaluation/run_eval.py --id Q09 Q14     # named cases
    python3 evaluation/run_eval.py --fresh-thread   # one thread per question

The API must be running. bash scripts/app.sh status will tell you.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http" + "://" + "127.0.0.1" + ":8000"
ROOT = Path(__file__).resolve().parents[1]
EVAL_SET = ROOT / "evaluation" / "eval_set.jsonl"
RESULTS = ROOT / "evaluation" / "results"
TRANSCRIPTS = RESULTS / "transcripts"

REFUSAL_MARKERS = (
    "not cover", "does not cover", "doesn't cover", "no policy", "out of scope",
    "cannot find", "not in the corpus", "outside the policy", "not addressed",
    "no information", "unable to find",
)


def load_set() -> list[dict]:
    rows = []
    for line in EVAL_SET.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


def ask(question: str, employee_id: str, thread_id: str | None,
        timeout: int = 240) -> tuple[dict, int]:
    body = json.dumps({
        "message": question, "employee_id": employee_id, "thread_id": thread_id,
    }).encode()
    request = urllib.request.Request(
        BASE + "/chat", data=body, headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    return payload, int((time.perf_counter() - started) * 1000)


def _norm_doc(ref: str) -> str:
    """Gold docs use 'POL-001 s2.1'; tool citations use 'POL-001 s2.1'.
    Normalise spacing so the two compare cleanly."""
    return ref.replace(" ", "").replace("§", "s").lower()


def score(case: dict, payload: dict, latency_ms: int) -> dict:
    citations = payload.get("citations", []) or []
    tools = [t.get("name") for t in payload.get("tool_trace", []) or []]
    steps = payload.get("steps", []) or []
    answer = (payload.get("answer") or "")
    answer_lower = answer.lower()

    decision = next((s for s in steps if s.get("kind") == "decision"), None)
    route = (decision or {}).get("detail")
    clarification = next((s for s in steps if s.get("kind") == "clarification"), None)

    got_cites = {_norm_doc(c.get("citation") or
                           f"{c.get('document_id')} s{c.get('section_id')}")
                 for c in citations}
    gold = {_norm_doc(d) for d in (case.get("gold_docs") or [])}

    hit = gold & got_cites
    citation_accuracy = round(len(hit) / len(gold), 3) if gold else None

    expected_tools = case.get("expected_tools") or []
    tool_selection = (round(sum(1 for t in expected_tools if t in tools)
                            / len(expected_tools), 3)
                      if expected_tools else None)
    missing_tools = [t for t in expected_tools if t not in tools]

    # Route: exact match when the case names one, else not scored.
    expected_route = case.get("expected_route")
    route_ok = None
    if expected_route:
        if route:
            route_ok = route.strip().lower() == expected_route.strip().lower()
        elif expected_route in ("insufficient", "manager approval required"):
            # PTO outcomes do not produce a route; infer from the tool result.
            route_ok = expected_route.lower() in answer_lower
        else:
            route_ok = False

    behaviour = case.get("expected_behavior")
    behaviour_ok = None
    if behaviour == "answer_with_escalation":
        behaviour_ok = bool(payload.get("escalation"))
    elif behaviour == "answer_no_escalation":
        behaviour_ok = not payload.get("escalation")
    elif behaviour == "clarify":
        behaviour_ok = bool(payload.get("needs_clarification") or clarification)
    elif behaviour == "refuse":
        behaviour_ok = any(m in answer_lower for m in REFUSAL_MARKERS)

    # Groundedness proxy: every citation shown, and an answer that is not empty.
    grounded = bool(answer.strip()) and (not citations or all(
        _norm_doc(c.get("citation") or
                  f"{c.get('document_id')} s{c.get('section_id')}") in got_cites
        for c in citations))

    return {
        "id": case["id"], "category": case.get("category"),
        "employee_id": case.get("employee_id"), "question": case["question"],
        "gold_answer": case.get("gold_answer"),
        "gold_docs": sorted(gold), "expected_tools": expected_tools,
        "expected_route": expected_route, "expected_behavior": behaviour,
        # observed
        "answer": answer,
        "route": route,
        "escalation": bool(payload.get("escalation")),
        "needs_clarification": bool(payload.get("needs_clarification")),
        "capped": bool(payload.get("capped")),
        "planning_error": payload.get("planning_error"),
        "prompt_id": payload.get("prompt_id"),
        "thread_id": payload.get("thread_id"),
        "tools_called": tools,
        "citations": sorted(got_cites),
        "latency_ms": latency_ms,
        # the evidence trail, preserved verbatim
        "steps": steps,
        "tool_io": [
            {"name": t.get("name"), "arguments": t.get("arguments"),
             "output_summary": t.get("output_summary"),
             "iteration": t.get("iteration")}
            for t in payload.get("tool_trace", []) or []
        ],
        # scores
        "citation_accuracy": citation_accuracy,
        "tool_selection": tool_selection,
        "missing_tools": missing_tools,
        "route_ok": route_ok,
        "behaviour_ok": behaviour_ok,
        "grounded": grounded,
        "completed": bool(answer.strip()) and not payload.get("planning_error"),
    }


def pct(values: list[int], p: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(p / 100 * len(ordered))) - 1))
    return ordered[idx]


def aggregate(rows: list[dict]) -> dict:
    def mean(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(statistics.fmean(vals), 3) if vals else None

    def rate(key):
        vals = [bool(r[key]) for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    lat = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r.get("category") or "uncategorised", []).append(r)

    return {
        "questions": len(rows),
        "citation_accuracy": mean("citation_accuracy"),
        "tool_selection_accuracy": mean("tool_selection"),
        "route_accuracy": rate("route_ok"),
        "workflow_completion_rate": rate("completed"),
        "behaviour_accuracy": rate("behaviour_ok"),
        "groundedness": rate("grounded"),
        "escalations": sum(1 for r in rows if r["escalation"]),
        "capped_runs": sum(1 for r in rows if r["capped"]),
        "planning_errors": sum(1 for r in rows if r["planning_error"]),
        "latency_p50_ms": pct(lat, 50), "latency_p95_ms": pct(lat, 95),
        "latency_min_ms": min(lat) if lat else None,
        "latency_max_ms": max(lat) if lat else None,
        "by_category": {
            cat: {
                "n": len(rs),
                "citation_accuracy": mean.__wrapped__ if False else
                    (round(statistics.fmean([x["citation_accuracy"] for x in rs
                                             if x.get("citation_accuracy") is not None]), 3)
                     if any(x.get("citation_accuracy") is not None for x in rs) else None),
                "route_accuracy": (round(sum(1 for x in rs if x.get("route_ok")) /
                                         len([x for x in rs if x.get("route_ok") is not None]), 3)
                                   if any(x.get("route_ok") is not None for x in rs) else None),
                "behaviour_accuracy": (round(sum(1 for x in rs if x.get("behaviour_ok")) /
                                             len([x for x in rs if x.get("behaviour_ok") is not None]), 3)
                                       if any(x.get("behaviour_ok") is not None for x in rs) else None),
            }
            for cat, rs in sorted(by_cat.items())
        },
    }


def write_transcript(row: dict) -> Path:
    path = TRANSCRIPTS / f"{row['id']}.md"
    lines = [
        f"# {row['id']} — {row['category']}",
        "",
        f"**Employee:** {row['employee_id']}  ",
        f"**Question:** {row['question']}",
        "",
        f"**Expected route:** `{row['expected_route']}` · "
        f"**observed:** `{row['route']}`",
        f"**Expected tools:** {row['expected_tools']}  ",
        f"**Tools called:** {row['tools_called']}",
        f"**Gold docs:** {row['gold_docs']}  ",
        f"**Citations:** {row['citations']}",
        f"**Citation accuracy:** {row['citation_accuracy']} · "
        f"**latency:** {row['latency_ms']} ms · **prompt_id:** {row['prompt_id']}",
        "",
    ]
    if row.get("planning_error"):
        lines += ["**Planning error:**", "", f"```\n{row['planning_error']}\n```", ""]

    lines += ["## Decision path", ""]
    for i, step in enumerate(row.get("steps") or [], 1):
        kind = step.get("kind")
        if kind == "tool_call":
            lines.append(f"{i}. **{step.get('tool')}** "
                         f"`{json.dumps(step.get('arguments'))}`")
            out = str(step.get("output") or "")[:300].replace("\n", " ")
            lines.append(f"   → {out}")
        else:
            lines.append(f"{i}. *{kind}* — {str(step.get('detail'))[:300]}")
    lines.append("")

    lines += ["## MCP tool I/O", ""]
    for t in row.get("tool_io") or []:
        lines += [f"### {t['name']} (iteration {t.get('iteration')})",
                  "", f"arguments: `{json.dumps(t.get('arguments'))}`", "",
                  "```json", str(t.get("output_summary"))[:700], "```", ""]

    lines += ["## Gold answer", "", row.get("gold_answer") or "", "",
              "## Agent answer", "", row.get("answer") or "", ""]
    path.write_text("\n".join(lines))
    return path


def write_summary(rows: list[dict], summary: dict) -> Path:
    path = RESULTS / "summary.md"
    lines = ["# Evaluation Results", "",
             f"Questions run: **{summary['questions']}**", "",
             "## Metric summary", "", "| Metric | Value |", "| --- | --- |"]
    for key in ("citation_accuracy", "tool_selection_accuracy", "route_accuracy",
                "workflow_completion_rate", "behaviour_accuracy", "groundedness"):
        lines.append(f"| {key.replace('_', ' ')} | {summary[key]} |")
    lines.append(f"| escalations | {summary['escalations']} |")
    lines.append(f"| capped runs (step limit) | {summary['capped_runs']} |")
    lines.append(f"| planning errors | {summary['planning_errors']} |")
    lines.append(f"| latency p50 (ms) | {summary['latency_p50_ms']} |")
    lines.append(f"| latency p95 (ms) | {summary['latency_p95_ms']} |")

    lines += ["", "## By category", "",
              "| Category | n | Citation acc. | Route acc. | Behaviour |",
              "| --- | --- | --- | --- | --- |"]
    for cat, m in summary["by_category"].items():
        lines.append(f"| {cat} | {m['n']} | {m['citation_accuracy']} | "
                     f"{m['route_accuracy']} | {m['behaviour_accuracy']} |")

    lines += ["", "## Failures worth fixing", ""]
    for r in rows:
        problems = []
        if r.get("route_ok") is False:
            problems.append(f"route expected `{r['expected_route']}`, got `{r['route']}`")
        if r.get("behaviour_ok") is False:
            problems.append(f"behaviour expected `{r['expected_behavior']}`")
        if r.get("missing_tools"):
            problems.append(f"missing tools {r['missing_tools']}")
        if r.get("citation_accuracy") == 0:
            problems.append("no gold document cited")
        if r.get("planning_error"):
            problems.append("planning error")
        if problems:
            lines.append(f"- **{r['id']}** — " + "; ".join(problems))

    lines += ["", "## Per-question", ""]
    for r in rows:
        lines.append(f"- {r['id']} [{r['category']}] route=`{r['route']}` "
                     f"cite={r['citation_accuracy']} tools={len(r['tools_called'])} "
                     f"{r['latency_ms']}ms")
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--id", nargs="*", dest="ids")
    parser.add_argument("--fresh-thread", action="store_true",
                        help="One thread per question instead of a shared one")
    args = parser.parse_args()

    if not EVAL_SET.exists():
        print(f"missing {EVAL_SET}", file=sys.stderr)
        return 1

    cases = load_set()
    if args.ids:
        wanted = set(args.ids)
        cases = [c for c in cases if c["id"] in wanted]
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 1

    RESULTS.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)

    thread_id: str | None = None
    rows: list[dict] = []

    print(f"running {len(cases)} cases against {BASE}\n")
    for case in cases:
        label = f"{case['id']:5} {case['question'][:58]:60}"
        sys.stdout.write(label)
        sys.stdout.flush()
        try:
            payload, latency = ask(
                case["question"], case.get("employee_id", "E1007"),
                None if args.fresh_thread else thread_id,
            )
            if not args.fresh_thread:
                thread_id = payload.get("thread_id", thread_id)
        except urllib.error.URLError as exc:
            print(f" FAILED: {exc}")
            rows.append({"id": case["id"], "category": case.get("category"),
                         "question": case["question"], "error": str(exc),
                         "latency_ms": None, "completed": False,
                         "steps": [], "tool_io": []})
            continue

        row = score(case, payload, latency)
        rows.append(row)
        write_transcript(row)

        verdict = "ok"
        if not row["behaviour_ok"] and row["behaviour_ok"] is not None:
            verdict = "BEHAVIOUR"
        elif row["route_ok"] is False:
            verdict = "ROUTE"
        elif row["citation_accuracy"] == 0:
            verdict = "CITE"
        elif row["planning_error"]:
            verdict = "ERROR"
        print(f" {verdict:10} route={row['route']} cite={row['citation_accuracy']} "
              f"{latency}ms")

    with (RESULTS / "results.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    scored = [r for r in rows if r.get("latency_ms") is not None]
    summary = aggregate(scored)
    summary_path = write_summary(scored, summary)

    print()
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {RESULTS / 'results.jsonl'}")
    print(f"wrote {summary_path}")
    print(f"wrote {len(scored)} transcripts to {TRANSCRIPTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
