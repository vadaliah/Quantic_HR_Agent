"""LangGraph agent that calls the real MCP server over stdio.

The planner is a local keyword router so we do not invoke Bedrock. Swap this
node for a Bedrock/Ollama model later without changing the MCP tool surface.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]


class AgentState(TypedDict, total=False):
    message: str
    employee_id: str
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
                    "arguments": {"employee_id": employee_id, "check_type": "pto", "requested_hours": 8},
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


async def _run_mcp(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    python = os.environ.get("PYTHON", sys.executable)
    params = StdioServerParameters(
        command=python,
        args=["-m", "quantic_hr.mcp_server"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        cwd=str(ROOT),
    )
    traces: list[dict[str, Any]] = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for call in calls:
                result = await session.call_tool(call["name"], call["arguments"])
                payload: Any
                if result.structuredContent is not None:
                    payload = result.structuredContent
                else:
                    payload = "\n".join(
                        block.text for block in result.content if getattr(block, "text", None)
                    )
                traces.append(
                    {
                        "name": call["name"],
                        "arguments": call["arguments"],
                        "output_summary": _summarize(payload),
                        "result": payload,
                    }
                )
    return traces


def plan_node(state: AgentState) -> AgentState:
    employee_id = state.get("employee_id") or "E001"
    return {
        **state,
        "employee_id": employee_id,
        "planned_calls": _plan(state["message"], employee_id),
    }


def tools_node(state: AgentState) -> AgentState:
    traces = asyncio.run(_run_mcp(state.get("planned_calls") or []))
    citations: list[dict[str, str]] = []
    snippets: list[str] = []
    for trace in traces:
        extra_cites, extra_snips = _citations_from(trace.get("result"))
        citations.extend(extra_cites)
        snippets.extend(extra_snips)
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
    return {**state, "answer": "\n".join(parts)}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("tools", tools_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "tools")
    graph.add_edge("tools", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


GRAPH = build_graph()


def run_agent(message: str, employee_id: str = "E001") -> dict[str, Any]:
    result = GRAPH.invoke({"message": message, "employee_id": employee_id})
    return {
        "answer": result.get("answer", ""),
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
