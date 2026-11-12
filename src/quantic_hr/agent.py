"""LangGraph agent that discovers MCP tools and runs a tool-calling loop.

Design
------
The planner does NOT work from a hand-written description of the tools. On every
run it opens one MCP session, calls list_tools, and binds the published schemas
into the model with bind_tools. The model then emits real tool calls, validated
against those schemas.

The session is held open across the whole loop. Each iteration the model sees the
question, the schemas, and every result so far; it decides whether to call another
tool or to answer. Termination is model-driven — the loop ends when the model
returns a message with no tool calls — and bounded by MAX_STEPS so a confused
model cannot spin forever.

Groundedness boundary
---------------------
The answer, the decision and the citation list are assembled from tool output by
code. The reasoning trace is the model's own narration and is NOT verified, so
policy references are stripped from it before it reaches the UI. References appear
only in the citation list, which is built from actual tool results. That is a
blunt guardrail: it removes a correct quotation too, and is preferred over
publishing a citation the model may not have read.

Session state (the employee id) is injected by code, never inferred, so the model
has no grounds to ask for it.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMPLOYEE = "E1007"
DEFAULT_MODEL = "us.amazon.nova-pro-v1:0"
MAX_STEPS = 6
HISTORY_TURNS = 2

# Tools the agent may call on its own. Write tools are excluded on purpose: they
# require explicit user confirmation and are handled outside the planner.
READ_TOOLS = {
    "search_policy_documents",
    "get_policy_section",
    "lookup_employee_profile",
    "check_pto_balance",
    "lookup_benefits_status",
    "check_policy_compliance",
}

# Tools whose first argument is session state.
EMPLOYEE_SCOPED = {
    "lookup_employee_profile",
    "check_pto_balance",
    "lookup_benefits_status",
    "check_policy_compliance",
}

_CITATION_RE = re.compile(
    r"\((?:POL|pol)-\d{3}[A-Za-z]?[^)]*\)|(?:POL|pol)-\d{3}[A-Za-z]?\s*s?[\d.]+"
)


def _model_id() -> str:
    return os.environ.get("BEDROCK_CHAT_INFERENCE_PROFILE", DEFAULT_MODEL)


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-2")


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=os.environ.get("PYTHON", sys.executable),
        args=["-m", "quantic_hr.mcp_server"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        cwd=str(ROOT),
    )


def _strip_citations(text: str) -> str:
    """Remove policy references from reasoning text.

    The reasoning trace is not verified, so a reference in it may name a rule the
    model never read. Stripping here keeps citations confined to the list built
    from tool output.
    """
    cleaned = _CITATION_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.replace(" ,", ",").replace(" .", ".").strip()


def _text_of(reply: Any) -> str:
    """Reasoning text from a model reply, whether content is str or block list."""
    content = getattr(reply, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return ""


# ------------------------------------------------------------- discovery
async def _discover_tools() -> list[dict[str, Any]]:
    """Open an MCP session and read the published tool schemas."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
        }
        for tool in listed.tools
        if tool.name in READ_TOOLS
    ]


def discover_tools() -> list[dict[str, Any]]:
    return asyncio.run(_discover_tools())


def _to_langchain_tools(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert MCP schemas to the shape ChatBedrockConverse.bind_tools expects."""
    return [
        {
            "name": s["name"],
            "description": s["description"],
            "parameters": s["input_schema"],
        }
        for s in schemas
    ]


# ------------------------------------------------------------- established
def resolve_context(employee_id: str, history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Facts the system already holds. Code decides; the model only uses them."""
    known: dict[str, Any] = {}
    if employee_id:
        known["employee_id"] = employee_id
    for turn in reversed(history or []):
        for step in turn.get("steps", []):
            if step.get("kind") != "tool_call":
                continue
            if step.get("tool") != "check_policy_compliance":
                continue
            for key in ("check_type", "destination_country", "duration_days", "amount_usd"):
                value = step.get("arguments", {}).get(key)
                if value is not None and key not in known:
                    known[key] = value
        for key in ("check_type", "destination_country", "duration_days", "amount_usd"):
            if key in known:
                break
    return known


def _conversation_block(history: list[dict[str, Any]] | None) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history[-HISTORY_TURNS:]:
        question = (turn.get("question") or "").strip()
        if question:
            lines.append(f"User: {question}")
        decision = next((s for s in (turn.get("steps") or [])
                         if s.get("kind") == "decision"), None)
        if decision:
            lines.append(f"Assistant: {decision.get('detail','')} — "
                         f"{(decision.get('reason') or '')[:180]}")
    return ("Recent conversation:\n" + "\n".join(lines) + "\n\n") if lines else ""


PLANNER_SYSTEM = """You are an HR policy assistant with access to tools.

You are given the tools with their input schemas. Use them, then answer.

Rules:
1. A question asking whether something is allowed — 'can I', 'am I allowed',
   'is it ok', 'do I qualify' — is a DECISION question. A retrieved passage is
   not a decision: you must call check_policy_compliance before answering it.
2. Call search_policy_documents first for any policy question, so the answer can
   cite the passage.
3. Call lookup_employee_profile before check_policy_compliance.
4. The established values are authoritative and already known. Pass them through;
   never ask the user for them.
5. Resolve follow-ups against Recent conversation. Carry forward the employee, the
   check_type and the subject under discussion, changing only what the new
   question changes.
6. Convert durations to days: 'six weeks' is 42, 'a month' is 30, 'two weeks' is 14.
7. Name the destination for any country. Omit it only if the person is staying put.
8. Never call the ticket or email tools.
9. Your reasoning describes what you are doing and what a tool result told you.
   Do not state policy rules unless you retrieved that passage in this
   conversation. Before retrieval, say what you are looking for, not what the
   policy says.
10. Emit tool calls. Producing none is a failure unless the question cannot be
    related to any tool at all.
"""


# ------------------------------------------------------------- execution
class AgentState(TypedDict, total=False):
    message: str
    employee_id: str
    history: list[dict[str, Any]]
    reasoning: str
    thoughts: list[str]
    final_text: str
    known: dict[str, Any]
    tool_trace: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    snippets: list[str]
    answer: str
    needs_clarification: bool
    clarification_question: str | None
    escalation: bool
    capped: bool
    planning_error: str | None


def _summarize(result: Any) -> str:
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    return text[:500]


def _citations_from(result: Any) -> tuple[list[dict[str, Any]], list[str]]:
    citations: list[dict[str, Any]] = []
    snippets: list[str] = []
    if isinstance(result, dict):
        for match in result.get("matches") or []:
            if not isinstance(match, dict):
                continue
            snippet = str(match.get("snippet") or match.get("content", ""))
            citations.append({
                "document_id": str(match.get("document_id", "")),
                "section_id": str(match.get("section_id", "")),
                "title": str(match.get("title", "")),
                "citation": str(match.get("citation", "")),
                "snippet": snippet[:400],
                "score": match.get("score"),
            })
            snippets.append(snippet[:240])
        if result.get("policy_document_id"):
            citations.append({
                "document_id": str(result["policy_document_id"]),
                "section_id": str(result.get("policy_section_id", "")),
                "title": str(result.get("check_type") or "policy"),
                "citation": f"{result['policy_document_id']} s{result.get('policy_section_id','')}",
                "snippet": str(result.get("reason", "")),
                "score": None,
            })
    return citations, snippets


async def _loop(message: str, employee_id: str,
                known: dict[str, Any],
                history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """One MCP session, one open loop.

    The model decides when the goal is met: it returns a message with no tool
    calls. MAX_STEPS bounds it. The session stays open, so discovery at the top
    and every call below share one server process.
    """
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            schemas = [
                {"name": t.name, "description": t.description or "",
                 "input_schema": t.inputSchema or {"type": "object", "properties": {}}}
                for t in listed.tools if t.name in READ_TOOLS
            ]

            llm = ChatBedrockConverse(model=_model_id(), region_name=_region(),
                                      temperature=0)
            bound = llm.bind_tools(_to_langchain_tools(schemas))

            established = "\n".join(f"  {k}: {v}" for k, v in known.items()) or "  (none)"
            messages: list[Any] = [
                SystemMessage(content=PLANNER_SYSTEM),
                HumanMessage(content=(
                    f"Established (already known, use these):\n{established}\n\n"
                    f"{_conversation_block(history)}"
                    f"Question: {message}"
                )),
            ]

            traces: list[dict[str, Any]] = []
            thoughts: list[str] = []
            final_text = ""
            capped = False

            for step in range(1, MAX_STEPS + 1):
                try:
                    reply: AIMessage = bound.invoke(messages)
                except Exception as exc:  # noqa: BLE001
                    return {"tool_trace": traces, "thoughts": thoughts,
                            "reasoning": "\n\n".join(thoughts),
                            "final_text": "", "capped": False,
                            "planning_error": f"{type(exc).__name__}: {exc}"}

                thought = _text_of(reply)
                if thought:
                    thoughts.append(thought)

                calls = getattr(reply, "tool_calls", None) or []
                if not calls:
                    final_text = thought
                    break

                messages.append(reply)

                for call in calls:
                    arguments = dict(call.get("args") or {})
                    # Session state, not model output.
                    if call["name"] in EMPLOYEE_SCOPED:
                        arguments.setdefault("employee_id", employee_id)
                    if call["name"] == "search_policy_documents" and not arguments.get("query"):
                        arguments["query"] = message

                    try:
                        result = await session.call_tool(call["name"], arguments)
                        if result.structuredContent is not None:
                            payload: Any = result.structuredContent
                        else:
                            payload = "\n".join(b.text for b in result.content
                                                if getattr(b, "text", None))
                    except Exception as exc:  # noqa: BLE001
                        payload = {"error": "TOOL_UNAVAILABLE", "detail": str(exc)}

                    traces.append({
                        "name": call["name"], "arguments": arguments,
                        "output_summary": _summarize(payload),
                        "result": payload, "iteration": step,
                    })
                    messages.append(ToolMessage(
                        content=_summarize(payload),
                        tool_call_id=call.get("id") or f"call_{step}",
                    ))
            else:
                capped = True

    return {"tool_trace": traces, "thoughts": thoughts,
            "reasoning": "\n\n".join(thoughts),
            "final_text": final_text, "capped": capped}


def agent_node(state: AgentState) -> AgentState:
    employee_id = state.get("employee_id") or DEFAULT_EMPLOYEE
    known = resolve_context(employee_id, state.get("history") or [])
    outcome = asyncio.run(_loop(state["message"], employee_id, known,
                                state.get("history") or []))

    traces = outcome["tool_trace"]
    citations: list[dict[str, Any]] = []
    snippets: list[str] = []
    for trace in traces:
        c, s = _citations_from(trace.get("result"))
        citations.extend(c)
        snippets.extend(s)

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for c in citations:
        key = (c.get("document_id", ""), c.get("section_id", ""))
        if key in seen or not key[0]:
            continue
        seen.add(key)
        unique.append(c)

    escalation = any(
        isinstance(t.get("result"), dict)
        and t["result"].get("route") in {"PEOPLE_OPS_AND_LEGAL", "PEOPLE_OPS_REVIEW", "DECLINED"}
        for t in traces
    )

    return {
        **state,
        "employee_id": employee_id,
        "known": known,
        "tool_trace": traces,
        "thoughts": outcome["thoughts"],
        "reasoning": outcome["reasoning"],
        "final_text": outcome["final_text"],
        "citations": unique,
        "snippets": snippets,
        "escalation": escalation,
        "capped": outcome["capped"],
        "planning_error": outcome.get("planning_error"),
    }


def synthesize_node(state: AgentState) -> AgentState:
    """The model's closing text when it produced one, else a deterministic summary."""
    if state.get("final_text"):
        return {**state, "answer": state["final_text"]}

    traces = state.get("tool_trace") or []
    parts = [f"Used {len(traces)} MCP tool call(s)."]
    for trace in traces:
        parts.append(f"{trace['name']}: {trace['output_summary'][:180]}")
    for trace in traces:
        result = trace.get("result")
        if isinstance(result, dict) and result.get("check_type"):
            line = "Decision: " + str(result.get("route") or result.get("compliant"))
            if result.get("reason"):
                line += f" — {result['reason']}"
            parts.append(line)
    cites = state.get("citations") or []
    if cites:
        parts.append("Citations: " + ", ".join(
            c.get("citation") or f"{c.get('document_id')}s{c.get('section_id')}" for c in cites))
    return {**state, "answer": "\n".join(parts)}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


GRAPH = build_graph()


def _steps_from(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the run into the ordered decision path the UI renders.

    Each thought is emitted once, attached to the first tool call of its
    iteration, so a repeated iteration does not duplicate the plan text. Policy
    references are stripped from reasoning, since that text is not verified.
    """
    trace = result.get("tool_trace", []) or []
    thoughts = result.get("thoughts") or []
    steps: list[dict[str, Any]] = []
    emitted: set[int] = set()

    for index, item in enumerate(trace, 1):
        iteration = item.get("iteration") or 1
        slot = iteration - 1
        if 0 <= slot < len(thoughts) and slot not in emitted:
            emitted.add(slot)
            steps.append({"kind": "plan", "detail": _strip_citations(thoughts[slot])})
        steps.append({
            "kind": "tool_call", "step": index, "tool": item["name"],
            "arguments": item["arguments"], "output": item["output_summary"],
            "iteration": iteration,
        })
        payload = item.get("result")
        if isinstance(payload, dict):
            if payload.get("route"):
                steps.append({"kind": "decision", "detail": payload["route"],
                              "reason": payload.get("reason", ""),
                              "policy_refs": payload.get("policy_refs", [])})
            elif payload.get("check_type") == "pto":
                steps.append({"kind": "decision",
                              "detail": "SUFFICIENT" if payload.get("sufficient") else "INSUFFICIENT",
                              "reason": payload.get("reason", ""),
                              "policy_refs": payload.get("policy_refs", [])})
            elif payload.get("benefits_class"):
                steps.append({"kind": "decision", "detail": payload["benefits_class"],
                              "reason": payload.get("reason") or "",
                              "policy_refs": payload.get("policy_refs", [])})

    final_text = result.get("final_text")
    if final_text:
        slot = len(thoughts) - 1
        if slot not in emitted:
            emitted.add(slot)
            steps.append({"kind": "plan", "detail": _strip_citations(final_text)})

    if result.get("capped"):
        steps.append({"kind": "escalation",
                      "detail": "Step limit reached before the agent finished."})
    if result.get("escalation"):
        steps.append({"kind": "escalation",
                      "detail": "Requires People Operations and Legal review."})
    return steps


def run_agent(message: str, employee_id: str = DEFAULT_EMPLOYEE,
              history: list[dict[str, Any]] | None = None,
              prompt_id: str | None = None) -> dict[str, Any]:
    prompt_id = prompt_id or uuid.uuid4().hex[:12]
    """Run the agent. Tools are discovered over MCP; the model drives the loop."""
    result = GRAPH.invoke({
        "message": message,
        "employee_id": employee_id,
        "history": history or [],
    })

    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "snippets": result.get("snippets", []),
        "tool_trace": [
            {"name": t["name"], "arguments": t["arguments"],
             "output_summary": t["output_summary"], "iteration": t.get("iteration")}
            for t in result.get("tool_trace", [])
        ],
        "reasoning": result.get("reasoning", ""),
        "thoughts": result.get("thoughts", []),
        "steps": _steps_from(result),
        "needs_clarification": bool(result.get("needs_clarification")),
        "clarification_question": result.get("clarification_question"),
        "escalation": bool(result.get("escalation")),
        "capped": bool(result.get("capped")),
        "planning_error": result.get("planning_error"),
    }
