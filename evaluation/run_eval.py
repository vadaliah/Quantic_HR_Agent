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
    python3 evaluation/run_eval.py                  # all cases in eval_set.jsonl
    python3 evaluation/run_eval.py --limit 5        # first five
    python3 evaluation/run_eval.py --id Q09 Q14     # named cases
    python3 evaluation/run_eval.py --fresh-thread   # one thread per question
    python3 evaluation/run_eval.py --rescore        # re-score saved results; no /chat calls

The API must be running. bash scripts/app.sh status will tell you.
"""
from __future__ import annotations

import argparse
import json
import re as _re
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://" + "quantic-hr-agent-dcw4.onrender.com"
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
    """Reduce a document reference to one canonical form.

    All of these must land on the same string:
        POL-001 2.1   POL-001:2.1   POL-001 s2.1
        POL-001s2.1   pol-001s2.1   POL-001 section 2.1
    Annex ids keep whatever the input carried, so 'POL-005A 5' and
    'POL-005A sA.5' stay distinct -- they are different identifiers.
    """
    s = ref.strip().lower().replace("\u00a7", " ").replace(":", " ")
    s = re.sub(r"\s+", " ", s).replace(" ", "")

    m = re.match(r"^(pol-\d{3})([a-z]?)(.*)$", s)
    if not m:
        return s
    digits, letter, rest = m.group(1), m.group(2), m.group(3)

    # A leading 's' before a section is the shorthand for the section sign, not
    # part of the id. Any other trailing letter (the annex 'a') is part of it.
    if letter == "s" and rest:
        doc = digits
    else:
        doc = digits + letter if letter else digits

    rest = re.sub(r"^s(?=.)", "", rest)
    return f"{doc}:{rest}" if rest else doc

"""Derive a compliance route from saved tool_io, for offline re-scoring."""


import json
from typing import Any


def _payload(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Return the tool's result as a dict, from result or output_summary."""
    raw = entry.get("result")
    if raw is None:
        raw = entry.get("output_summary")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def route_from_tool_io(tool_io: list[dict[str, Any]]) -> str | None:
    """The route the compliance tool returned, or a derivation from its fields.

    Runs offline against saved results, so a re-score needs no /chat call and no
    Bedrock spend. The route is the compliance tool's own output: it is read when
    present, and derived from `compliant` and `manager_approval_required` only
    for rows saved before the tool returned it.
    """
    for entry in tool_io or []:
        if entry.get("name") != "check_policy_compliance":
            continue
        result = _payload(entry)
        if not result:
            continue

        route = result.get("route")
        if route:
            return str(route)

        # Older rows: no route field. Derive from the fields the tool did return.
        checked = result.get("checked")
        if checked is False:
            return "CANNOT_DETERMINE"
        if result.get("compliant") is False:
            if result.get("manager_approval_required"):
                return "MANAGER_APPROVAL"
            if result.get("available_days") is not None:
                return "INSUFFICIENT_BALANCE"
            if result.get("amount_usd") is not None and result.get("limit_usd") is not None:
                return "PARTIAL_UP_TO_LIMIT"
            return "NOT_ELIGIBLE"
        if result.get("compliant") is True:
            if result.get("manager_approval_required"):
                return "MANAGER_APPROVAL"
            if result.get("receipt_required"):
                return "CLAIM_WITH_RECEIPT"
            return "CLAIM"
    return None

def score(case: dict, payload: dict, latency_ms: int,) -> dict:
    citations = payload.get("citations", []) or []
    tools = [t.get("name") for t in payload.get("tool_trace", []) or []]
    steps = payload.get("steps", []) or []
    answer = payload.get("answer") or ""
    answer_lower = answer.lower()

    # ---- route ----------------------------------------------------------
    # The route is the compliance tool's own output. The saved rows carry it
    # under tool_io[].output_summary as a JSON string; a live response carries
    # the same payload under tool_trace. Reading only tool_trace[].result left
    # the route None on every saved case, so route accuracy read 0.0 however
    # the tool behaved.
    route = None

    def _compliance_results():
        for source in ("tool_io", "tool_trace"):
            for entry in payload.get(source) or []:
                if entry.get("name") != "check_policy_compliance":
                    continue
                if entry.get("is_error"):
                    continue
                raw = entry.get("result")
                if raw is None:
                    raw = entry.get("output_summary")
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except ValueError:
                        raw = None
                if isinstance(raw, dict):
                    yield raw

    for result in _compliance_results():
        if result.get("route"):
            route = result["route"]
            break

    # Rows saved before the tool returned a route: derive it from the fields
    # the tool did return, so a re-score needs no /chat call and no Bedrock.
    if route is None:
        for result in _compliance_results():
            if result.get("checked") is False:
                route = "CANNOT_DETERMINE"
            elif result.get("compliant") is False:
                if result.get("manager_approval_required"):
                    route = "MANAGER_APPROVAL"
                elif result.get("available_days") is not None:
                    route = "INSUFFICIENT_BALANCE"
                elif result.get("amount_usd") is not None:
                    route = "PARTIAL_UP_TO_LIMIT"
                else:
                    route = "NOT_ELIGIBLE"
            elif result.get("compliant") is True:
                if result.get("manager_approval_required"):
                    route = "MANAGER_APPROVAL"
                elif result.get("receipt_required"):
                    route = "CLAIM_WITH_RECEIPT"
                else:
                    route = "CLAIM"
            if route:
                break

    if route is None:
        decision = next((s for s in steps if s.get("kind") == "decision"), None)
        route = (decision or {}).get("detail")

    clarification = next((s for s in steps if s.get("kind") == "clarification"), None)

    # ---- citations ------------------------------------------------------
    got_cites = {_norm_doc(c.get("citation") or
                           f"{c.get('document_id')}:{c.get('section_id')}")
                 for c in citations}
    gold = {_norm_doc(d) for d in (case.get("gold_docs") or [])}

    hit = gold & got_cites
    citation_accuracy = round(len(hit) / len(gold), 3) if gold else None

    # ---- tools ----------------------------------------------------------
    expected_tools = case.get("expected_tools") or []
    tool_selection = (round(sum(1 for t in expected_tools if t in tools)
                            / len(expected_tools), 3)
                      if expected_tools else None)
    missing_tools = [t for t in expected_tools if t not in tools]

    # ---- route score ----------------------------------------------------
    expected_route = case.get("expected_route")
    route_ok = None
    if expected_route:
        route_ok = bool(route) and route.strip().lower() == expected_route.strip().lower()

    # ---- behaviour ------------------------------------------------------
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

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "question": case.get("question"),
        "employee_id": case.get("employee_id"),
        "gold_docs": sorted(gold),
        "citations": sorted(got_cites),
        "citation_accuracy": citation_accuracy,
        "expected_tools": expected_tools,
        "tools_called": tools,
        "tool_selection": tool_selection,
        "missing_tools": missing_tools,
        "expected_route": expected_route,
        "route": route,
        "route_ok": route_ok,
        "expected_behavior": behaviour,
        "behaviour_ok": behaviour_ok,
        "escalation": bool(payload.get("escalation")),
        "needs_clarification": bool(payload.get("needs_clarification") or clarification),
        "planning_error": payload.get("planning_error"),
        "steps": steps,
        "completed": not bool(payload.get("capped")),
        "capped": bool(payload.get("capped")),
        "latency_ms": latency_ms,
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

    lat = [r.get("latency_ms") for r in rows if r.get("latency_ms") is not None]
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
        "escalations": sum(1 for r in rows if r.get("escalation")),
        "capped_runs": sum(1 for r in rows if r.get("capped")),
        "planning_errors": sum(1 for r in rows if r.get("planning_error")),
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
    g = lambda k, d="—": row.get(k, d)  # noqa: E731
    lines = [
        f"# {row['id']} — {g('category')}",
        "",
        f"**Employee:** {g('employee_id')}  ",
        f"**Question:** {g('question')}",
        "",
        f"**Expected route:** `{g('expected_route')}` · "
        f"**observed:** `{g('route')}`",
        f"**Expected tools:** {g('expected_tools')}  ",
        f"**Tools called:** {g('tools_called')}",
        f"**Gold docs:** {g('gold_docs')}  ",
        f"**Citations:** {g('citations')}",
        f"**Citation accuracy:** {g('citation_accuracy')} · ",
    ]
    if row.get("planning_error"):
        lines += ["**Planning error:**", "", f"```\n{row.get('planning_error')}\n```", ""]

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
            problems.append(f"route expected `{r.get("expected_route")}`, got `{r.get("route")}`")
        if r.get("behaviour_ok") is False:
            problems.append(f"behaviour expected `{r.get("expected_behavior")}`")
        if r.get("missing_tools"):
            problems.append(f"missing tools {r.get("missing_tools")}")
        if r.get("citation_accuracy") == 0:
            problems.append("no gold document cited")
        if r.get("planning_error"):
            problems.append("planning error")
        if problems:
            lines.append(f"- **{r['id']}** — " + "; ".join(problems))

    lines += ["", "## Per-question", ""]
    for r in rows:
        lines.append(f"- {r['id']} [{r.get("category")}] route=`{r.get("route")}` "
                     f"cite={r.get("citation_accuracy")} tools={len(r.get("tools_called"))} "
                     f"{r.get("latency_ms")}ms")
    path.write_text("\n".join(lines) + "\n")
    return path


def rescore_existing(results_path: Path) -> list[dict]:
    """Re-apply citation scoring to a saved results.jsonl without calling /chat."""
    cases = {case["id"]: case for case in load_set()}
    rows = [json.loads(line) for line in results_path.read_text().splitlines() if line.strip()]
    for row in rows:
        case = cases.get(row.get("id"))
        if not case:
            continue
        gold = {_norm_doc(doc) for doc in (case.get("gold_docs") or [])}
        got = {_norm_doc(cite) for cite in (row.get("citations") or [])}
        row["gold_docs"] = sorted(gold)
        row["citations"] = sorted(got)
        row["citation_accuracy"] = (
            round(len(gold & got) / len(gold), 3) if gold else None
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--id", nargs="*", dest="ids")
    parser.add_argument("--fresh-thread", action="store_true",
                        help="One thread per question instead of a shared one")
    parser.add_argument(
        "--rescore",
        nargs="?",
        const=str(RESULTS / "results.jsonl"),
        help="Re-score citation accuracy from a saved results.jsonl; does not call /chat",
    )
    args = parser.parse_args()

    if args.rescore:
        results_path = Path(args.rescore)
        if not results_path.exists():
            print(f"missing {results_path}", file=sys.stderr)
            return 1
        rows = rescore_existing(results_path)
        RESULTS.mkdir(parents=True, exist_ok=True)
        with results_path.open("w") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        scored = [row for row in rows if row.get("latency_ms") is not None]
        summary = aggregate(scored)
        summary_path = write_summary(scored, summary)
        note = (
            "Citation identifiers were re-scored on 15 Nov 2026 (Europe/Berlin) "
            "with the corrected `_norm_doc` helper. The underlying traces were "
            "not re-run against `/chat`.\n\n"
        )
        body = summary_path.read_text()
        if not body.startswith("Citation identifiers were re-scored"):
            # Insert the note after the title line.
            parts = body.split("\n", 1)
            summary_path.write_text(parts[0] + "\n\n" + note + (parts[1].lstrip("\n") if len(parts) > 1 else ""))
        print(json.dumps({k: summary[k] for k in (
            "questions", "citation_accuracy", "tool_selection_accuracy",
            "route_accuracy", "workflow_completion_rate", "behaviour_accuracy",
            "groundedness", "latency_p50_ms", "latency_p95_ms",
        )}, indent=2))
        print(f"rewrote {results_path}")
        print(f"rewrote {summary_path}")
        return 0

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
        row.setdefault("employee_id", case.get("employee_id"))
        row.setdefault("category", case.get("category"))
        row.setdefault("question", case.get("question"))
        rows.append(row)
        write_transcript(row)

        verdict = "ok"
        if not row.get("behaviour_ok") and row.get("behaviour_ok") is not None:
            verdict = "BEHAVIOUR"
        elif row.get("route_ok") is False:
            verdict = "ROUTE"
        elif row["citation_accuracy"] == 0:
            verdict = "CITE"
        elif row.get("planning_error"):
            verdict = "ERROR"
        print(f" {verdict:10} route={row.get("route")} cite={row.get("citation_accuracy")} "
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
