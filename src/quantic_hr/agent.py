"""LangGraph agent that calls the real MCP server over stdio.

Primary path: a Bedrock Converse tool-use loop. The model sees the MCP tools
(name, description, JSON schema), calls them through the stdio MCP session, and
answers only from tool results with citations. When nothing grounds the answer,
the agent abstains instead of guessing.

Fallback path: the original local keyword router, used when
QUANTIC_AGENT_MODE=keyword, when no AWS credentials exist (auto), or when
Bedrock fails. Both paths use the same MCP tool surface.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from quantic_hr import bedrock

ROOT = Path(__file__).resolve().parents[2]
# Seed data (mock_data/employees.json) uses E1001-E1025; E1007 is the remote-work demo.
DEFAULT_EMPLOYEE_ID = "E1007"
MAX_TOOL_ROUNDS = 6
ABSTAIN_MESSAGE = (
    "I could not find this in the Acme Corp HR policies or your HR records, so I will not guess. "
    "Please contact People Operations."
)
SYSTEM_PROMPT = f"""You are the Acme Corp HR assistant for one signed-in employee.
Rules:
- Use the tools. Answer only from tool results; never from general knowledge.
- Search the policy corpus before answering any policy question.
- The employee_id is fixed by the session; do not ask for or use another one.
- Cite every policy statement as [document_id section_id], for example [POL-001 2.1].
- draft_hr_email only drafts; never say an email was sent or a record was changed.
- If the tools return nothing relevant, reply exactly: {ABSTAIN_MESSAGE}
- Do not include reasoning, planning or thinking tags in your answer. Reply
  with the answer only, Be brief: a short answer, then the key conditions or next step."""


class AgentState(TypedDict, total=False):
    message: str
    employee_id: str
    history: list[dict[str, Any]]
    prompt_id: str | None
    mode: str
    model: str | None
    abstained: bool
    fallback_reason: str | None
    planned_calls: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    citations: list[dict[str, str]]
    snippets: list[str]
    answer: str


def _plan(message: str, employee_id: str) -> list[dict[str, Any]]:
    text = message.lower()
    calls: list[dict[str, Any]] = []
    if employee_id:
        calls.append({"name": "lookup_employee_profile", "arguments": {"employee_id": employee_id}})
    if "pto" in text or "leave" in text or "vacation" in text:
        if employee_id:
            calls.append({"name": "check_pto_balance", "arguments": {"employee_id": employee_id}})
        calls.append({"name": "search_policy_documents", "arguments": {"query": "paid time off"}})
        if employee_id:
            calls.append(
                {
                    "name": "check_policy_compliance",
                    "arguments": {"employee_id": employee_id, "check_type": "pto", "requested_days": 1},
                }
            )
        return calls
    if "remote" in text or "work from" in text:
        calls.append({"name": "search_policy_documents", "arguments": {"query": "remote work"}})
        if employee_id:
            calls.append(
                {
                    "name": "check_policy_compliance",
                    "arguments": {"employee_id": employee_id, "check_type": "remote_work"},
                }
            )
        return calls
    calls.append({"name": "search_policy_documents", "arguments": {"query": message}})
    return calls


def _summarize(result: Any) -> str:
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    return text[:500]


def _citations_from(result: Any) -> tuple[list[dict[str, str]], list[str]]:
    citations: list[dict[str, str]] = []
    snippets: list[str] = []
    if isinstance(result, dict):
        matches = result.get("matches")
        if isinstance(matches, list):
            for match in matches:
                citations.append(
                    {
                        "document_id": str(match.get("document_id", "")),
                        "section_id": str(match.get("section_id", "")),
                        "title": str(match.get("title", "")),
                    }
                )
                snippets.append(str(match.get("content", ""))[:240])
        if result.get("policy_document_id"):
            citations.append(
                {
                    "document_id": str(result["policy_document_id"]),
                    "section_id": str(result.get("policy_section_id", "")),
                    "title": str(result.get("check_type", "policy")),
                }
            )
    return citations, snippets


@asynccontextmanager
async def _mcp_session():
    python = os.environ.get("PYTHON", sys.executable)
    params = StdioServerParameters(
        command=python,
        args=["-m", "quantic_hr.mcp_server"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    payload: Any
    if result.structuredContent is not None:
        payload = result.structuredContent
    else:
        payload = "\n".join(block.text for block in result.content if getattr(block, "text", None))
    return {
        "name": name,
        "arguments": arguments,
        "output_summary": _summarize(payload),
        "result": payload,
        "is_error": bool(getattr(result, "isError", False)),
    }


async def _run_mcp(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    async with _mcp_session() as session:
        for call in calls:
            traces.append(await _call_tool(session, call["name"], call["arguments"]))
    return traces


def agent_mode() -> str:
    """QUANTIC_AGENT_MODE: auto (Bedrock when AWS credentials exist), bedrock, keyword."""
    mode = os.environ.get("QUANTIC_AGENT_MODE", "auto").strip().lower()
    return mode if mode in {"auto", "bedrock", "keyword"} else "auto"


def use_bedrock() -> bool:
    mode = agent_mode()
    return mode == "bedrock" or (mode == "auto" and bedrock.credentials_available())


def _json_safe(payload: Any) -> dict[str, Any]:
    data = json.loads(json.dumps(payload, default=str))
    return data if isinstance(data, dict) else {"result": data}


async def _converse_loop(message: str, employee_id: str) -> tuple[str, list[dict[str, Any]]]:
    """Bedrock Converse tool-use loop over the MCP tools. Raises BedrockUnavailable."""
    traces: list[dict[str, Any]] = []
    failure: bedrock.BedrockUnavailable | None = None
    text = ""
    # Raise Bedrock errors only after the MCP session closes; raised inside it,
    # anyio would wrap them in an ExceptionGroup.
    async with _mcp_session() as session:
        listed = await session.list_tools()
        specs = [bedrock.tool_spec(t.name, t.description or t.name, t.inputSchema) for t in listed.tools]
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"text": f"Signed-in employee_id: {employee_id}\n\n{message}"}]}
        ]
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = await asyncio.to_thread(
                    bedrock.converse, messages, system=SYSTEM_PROMPT, tools=specs
                )
            except bedrock.BedrockUnavailable as exc:
                failure = exc
                break
            messages.append(response["output"]["message"])
            uses = bedrock.response_tool_uses(response)
            if response.get("stopReason") != "tool_use" or not uses:
                text = bedrock.response_text(response)
                break
            results = []
            for use in uses:
                arguments = dict(use.get("input") or {})
                if "employee_id" in arguments:
                    arguments["employee_id"] = employee_id  # the session decides whose data is read
                trace = await _call_tool(session, use["name"], arguments)
                traces.append(trace)
                results.append(
                    {
                        "toolResult": {
                            "toolUseId": use["toolUseId"],
                            "content": [{"json": _json_safe(trace["result"])}],
                            "status": "error" if trace["is_error"] else "success",
                        }
                    }
                )
            messages.append({"role": "user", "content": results})
    if failure is not None:
        raise failure
    return text, traces  # text is empty if the tool-round budget ran out


def _collect(traces: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
    citations: list[dict[str, str]] = []
    snippets: list[str] = []
    seen: set[tuple[str, str]] = set()
    for trace in traces:
        if trace.get("is_error"):
            continue
        extra_cites, extra_snips = _citations_from(trace.get("result"))
        for cite in extra_cites:
            key = (cite["document_id"], cite["section_id"])
            if cite["document_id"] and key not in seen:
                seen.add(key)
                citations.append(cite)
        snippets.extend(extra_snips)
    return citations, snippets


import re

_THINK = re.compile(r"<thinking>.*?</thinking>", re.S | re.I)


def _clean(text: str) -> str:
    """Drop the model's reasoning tags. The trace carries the operational
    steps; the answer carries only the answer."""
    return _THINK.sub("", text or "").strip()


def converse_node(state: AgentState) -> AgentState:
    try:
        text, traces = asyncio.run(_converse_loop(state["message"], state["employee_id"]))
    except bedrock.BedrockUnavailable as exc:
        return {**state, "fallback_reason": str(exc)}
    citations, snippets = _collect(traces)
    abstained = not citations or not text or ABSTAIN_MESSAGE in text
    return {
        **state,
        "mode": "bedrock",
        "model": bedrock.chat_model_id(),
        "tool_trace": traces,
        "citations": [] if abstained else citations,
        "snippets": [] if abstained else snippets,
        "answer": ABSTAIN_MESSAGE if abstained else _clean(text),
        "abstained": abstained,
    }


def start_node(state: AgentState) -> AgentState:
    return {**state, "employee_id": state.get("employee_id") or DEFAULT_EMPLOYEE_ID}


def route_start(state: AgentState) -> str:
    return "converse" if use_bedrock() else "plan"


def route_after_converse(state: AgentState) -> str:
    return END if state.get("mode") == "bedrock" else "plan"


def plan_node(state: AgentState) -> AgentState:
    employee_id = state.get("employee_id") or DEFAULT_EMPLOYEE_ID
    return {
        **state,
        "employee_id": employee_id,
        "planned_calls": _plan(state["message"], employee_id),
    }


def tools_node(state: AgentState) -> AgentState:
    traces = asyncio.run(_run_mcp(state.get("planned_calls") or []))
    citations, snippets = _collect(traces)
    return {**state, "tool_trace": traces, "citations": citations, "snippets": snippets}


def synthesize_node(state: AgentState) -> AgentState:
    traces = state.get("tool_trace") or []
    parts = [f"Used {len(traces)} MCP tool call(s)."]
    for trace in traces:
        parts.append(f"{trace['name']}: {trace['output_summary'][:180]}")
    cites = state.get("citations") or []
    if cites:
        parts.append(
            "Citations: "
            + ", ".join(f"{c.get('document_id')}#{c.get('section_id')}" for c in cites if c.get("document_id"))
        )
    else:
        parts.append(ABSTAIN_MESSAGE)
    return {
        **state,
        "mode": "keyword",
        "model": None,
        "abstained": not cites,
        "answer": "\n".join(parts),
    }


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("start", start_node)
    graph.add_node("converse", converse_node)
    graph.add_node("plan", plan_node)
    graph.add_node("tools", tools_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "start")
    graph.add_conditional_edges("start", route_start, ["converse", "plan"])
    graph.add_conditional_edges("converse", route_after_converse, [END, "plan"])
    graph.add_edge("plan", "tools")
    graph.add_edge("tools", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


GRAPH = build_graph()


def run_agent(
    message: str,
    employee_id: str = DEFAULT_EMPLOYEE_ID,
    history: list[dict[str, Any]] | None = None,
    prompt_id: str | None = None,
) -> dict[str, Any]:
    result = GRAPH.invoke({
        "message": message,
        "employee_id": employee_id,
        "history": history or [],
        "prompt_id": prompt_id,
    })
    return {
        "answer": result.get("answer", ""),
        "mode": result.get("mode", "keyword"),
        "model": result.get("model"),
        "abstained": bool(result.get("abstained")),
        "fallback_reason": result.get("fallback_reason"),
        "citations": result.get("citations", []),
        "snippets": result.get("snippets", []),
        "tool_trace": [
            {
                "name": item["name"],
                "arguments": item["arguments"],
                "output_summary": item["output_summary"],
            }
            for item in result.get("tool_trace", [])
        ],
    }
