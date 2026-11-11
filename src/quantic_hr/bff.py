"""FastAPI BFF for the HR agent.

/health must not open a Postgres connection: the cluster sits in private subnets
and only the Data API is reachable, so a psycopg attempt would hang until
timeout. It calls db.health() instead, which uses whichever path is configured.

Conversation state is held in memory, keyed by thread_id, and capped per thread.
The last two turns are passed to the agent so a follow-up resolves against them;
the rest is retained for display and for browsing threads within the session.

Thread browsing is session-scoped by design: the deque dies with the process.
The durable record of a single prompt is in agent_runs, keyed by prompt_id.

A warm-up runs at startup because the cluster auto-pauses after 300 seconds of
idle. Without it, the first question after a pause fails while the cluster
resumes, which reads as an application fault rather than a cold start.
"""
from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict, deque
from fastapi import HTTPException, Path
from fastapi.responses import FileResponse, HTMLResponse
from quantic_hr.evaluation import load_results


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from quantic_hr import db
from quantic_hr.agent import DEFAULT_EMPLOYEE, run_agent
from quantic_hr.db import execute, query_one
from quantic_hr.prompt_log import new_prompt_id, persist_prompt
from quantic_hr.guardrails import needs_clarification, is_out_of_corpus, REFUSAL_TEXT


MAX_TURNS = 6          # retained per thread, for display
CONTEXT_TURNS = 2      # passed to the planner, for follow-ups
WARMUP_ATTEMPTS = 3
WARMUP_DELAY = 5




app = FastAPI(title="Quantic HR BFF", version="0.7.0")

from quantic_hr.evaluation import ROOT as REPO_ROOT, load_results
DASHBOARD_HTML = REPO_ROOT / "web" / "evaluation_dashboard.html"



_origins = os.environ.get(
    "ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

THREADS: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_TURNS))


@app.on_event("startup")
def warm_database() -> None:
    """Wake the cluster before the first question is asked."""
    for attempt in range(1, WARMUP_ATTEMPTS + 1):
        result = db.health()
        if result.get("ok"):
            print(f"cluster warm via {result.get('path')} (attempt {attempt})")
            return
        print(f"cluster not ready (attempt {attempt}): {result.get('error')}")
        time.sleep(WARMUP_DELAY)
    print(f"cluster did not wake after {WARMUP_ATTEMPTS} attempts; "
          "the first question may fail and should be retried.")


class ChatRequest(BaseModel):
    message: str
    employee_id: str = Field(default=DEFAULT_EMPLOYEE)
    thread_id: str | None = None


@app.get("/health")
def health() -> dict:
    database = db.health()
    return {
        "status": "ok" if database.get("ok") else "degraded",
        "runtime": "data-api" if db.using_data_api() else "local",
        "mcp": "stdio",
        "database": database,
        "threads_in_session": len(THREADS),
    }

@app.get("/evaluation/results")
def evaluation_results() -> dict:
    """Latest evaluation run, for the dashboard. No caching, always current."""
    return load_results()


@app.get("/evaluation", response_class=HTMLResponse)
def evaluation_dashboard() -> HTMLResponse:
    """The evaluation dashboard, reading from the results endpoint."""
    page = DASHBOARD_HTML
    if not page.exists():
        raise HTTPException(status_code=404, detail="dashboard file not found")
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.get("/employees")
def list_employees() -> dict:
    """Selectable employees, read from the database.

    The frontend renders its dropdown from this rather than from a constant, so
    the list cannot offer an employee that is not in the seeded records.
    """
    rows = execute(
        """
        SELECT employee_id, display_name, employment_type,
               remote_eligible, home_country, home_location,
               designated_onsite_role
        FROM employees
        ORDER BY employee_id
        """
    )
    return {"employees": rows}


@app.get("/threads")
def list_threads() -> dict:
    """Threads held in this server session, most recently used first."""
    out = []
    for tid, turns in THREADS.items():
        if not turns:
            continue
        out.append({
            "thread_id": tid,
            "turns": len(turns),
            "first_question": turns[0].get("question", ""),
            "last_question": turns[-1].get("question", ""),
            "employee_id": turns[-1].get("employee_id"),
        })
    # The deque preserves insertion order, so reverse it for newest-first.
    out.reverse()
    return {"threads": out, "count": len(out)}


@app.get("/thread/{thread_id}")
def get_thread(thread_id: str) -> dict:
    """Full turns for one session thread, oldest first.

    Each turn is the object stored by /chat, so it already carries question,
    answer, steps, tool_trace, citations and escalation. Nothing is remapped.
    """
    turns = list(THREADS.get(thread_id, []))
    return {"thread_id": thread_id, "turns": turns, "count": len(turns)}


@app.get("/prompt/{prompt_id}")
def get_prompt(prompt_id: str) -> dict:
    """Reconstruct a stored transaction: trace, tool calls, citations."""
    row = query_one(
        """SELECT prompt_id, created_at, thread_id, user_message, answer, trace,
                  citations, escalation, route, tool_names, step_count, latency_ms,
                  cold_start, model
           FROM agent_runs WHERE prompt_id = %s""",
        [prompt_id],
    )
    if not row:
        return {"found": False, "prompt_id": prompt_id}
    return {"found": True, **row}


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    thread_id = request.thread_id or uuid.uuid4().hex[:12]
    history = list(THREADS.get(thread_id, []))[-CONTEXT_TURNS:]
    prompt_id = new_prompt_id()
    started = time.perf_counter()

    # --- Guardrail: the request is too vague to apply any policy -------------
    clarify = needs_clarification(request.message)
    if clarify:
        latency_ms = int((time.perf_counter() - started) * 1000)
        turn = {
            "answer": clarify,
            "needs_clarification": True,
            "refused": False,
            "escalation": False,
            "citations": [],
            "tool_trace": [],
            "steps": [{"kind": "clarification", "detail": clarify,
                       "reason": "request under-specified; no policy applied"}],
            "prompt_id": prompt_id,
            "thread_id": thread_id,
            "employee_id": request.employee_id,
            "question": request.message,
            "latency_ms": latency_ms,
        }
        THREADS[thread_id].append(turn)
        persist_prompt(prompt_id, request.employee_id, request.message, turn, latency_ms)
        return turn

    # --- Guardrail: the question is outside the corpus ----------------------
    if is_out_of_corpus(request.message):
        latency_ms = int((time.perf_counter() - started) * 1000)
        turn = {
            "answer": REFUSAL_TEXT,
            "needs_clarification": False,
            "refused": True,
            "escalation": False,
            "citations": [],
            "tool_trace": [],
            "steps": [{"kind": "refusal", "detail": REFUSAL_TEXT,
                       "reason": "question outside the policy corpus"}],
            "prompt_id": prompt_id,
            "thread_id": thread_id,
            "employee_id": request.employee_id,
            "question": request.message,
            "latency_ms": latency_ms,
        }
        THREADS[thread_id].append(turn)
        persist_prompt(prompt_id, request.employee_id, request.message, turn, latency_ms)
        return turn

    # --- Normal path: run the agent -----------------------------------------
    result = run_agent(request.message, request.employee_id,
                       history=history, prompt_id=prompt_id)
    latency_ms = int((time.perf_counter() - started) * 1000)

    turn = {
        **result,
        "prompt_id": prompt_id,
        "thread_id": thread_id,
        "employee_id": request.employee_id,
        "question": request.message,
        "latency_ms": latency_ms,
    }
    THREADS[thread_id].append(turn)
    persist_prompt(prompt_id, request.employee_id, request.message, turn, latency_ms)
    return turn

