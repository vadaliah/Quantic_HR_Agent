# Design and Evaluation

Quantic HR Agent — an agentic RAG system over Acme Corp HR policy, deployed on
Render and answered through Amazon Bedrock.

- Deployed URL: https://quantic-hr-agent-dcw4.onrender.com
- Branch: `fix/bedrock-wiring-2026-11-11`
- Region: AWS `us-east-2`; Render free tier, Ohio

---

## 1. Architecture

One Render web service serves the API and the built UI on the same origin, so no
CORS boundary exists in production and no second host is needed on the free tier.

```
Browser (React UI, served by the same service)
   │  POST /chat            GET /employees, /threads, /evaluation, /health, /ping
   ▼
FastAPI BFF  (src/quantic_hr/bff.py)
   ├─ guardrail: needs_clarification?  → clarification turn, no model call
   ├─ guardrail: is_out_of_corpus?     → refusal turn, no model call
   └─ run_agent(message, employee_id, history, prompt_id)
          │
          ▼  LangGraph  (src/quantic_hr/agent.py)
          ├─ start_node        employee_id fixed to the session value
          ├─ route_start       QUANTIC_AGENT_MODE decides the path
          ├─ converse_node     Bedrock Converse tool-use loop, ≤ 6 rounds
          │     ├─ session.initialize()          MCP handshake
          │     ├─ session.list_tools()          live discovery
          │     ├─ bedrock.converse(...)         model chooses tool + arguments
          │     ├─ session.call_tool(name, args) executed over MCP
          │     └─ toolResult appended → loop
          └─ _collect          citations from successful traces only
   │
   ▼  MCP server (src/quantic_hr/mcp_server.py, FastMCP over stdio)
   │     eight tools; read-only SQL guard
   ▼
db.py  ── Aurora PostgreSQL 17.4 Serverless v2, pgvector(1024) HNSW
   │       via the RDS Data API over HTTPS (no VPC route, no bastion)
   ▼
Bedrock us-east-2:  amazon.nova-pro-v1:0 (Converse), titan-embed-text-v2:0
```

The layers the brief asks to be distinguishable — web app, agent orchestration,
MCP client/server, RAG index, mock data, LLM provider — are separated by module,
not by convention: `bff.py` (web), `agent.py` (orchestration + MCP client),
`mcp_server.py` (MCP server + tool schemas), `tools.py` (RAG and data access),
`db.py` (storage), `bedrock.py` (provider). A component diagram is in `docs/`
(Archify export).

### Why the Data API rather than psycopg

The Aurora cluster sits in private subnets and its DNS name resolves to an
unroutable `10.20.x.x` address. A laptop — and a Render container — cannot reach
it over TCP. The Data API is HTTPS with SigV4, so the same database is reachable
from anywhere without a VPN, a bastion or an open port. `db.py` prefers the Data
API when `CLUSTER_ARN` and `SECRET_ARN` are set and falls back to psycopg only
where a route exists.

Both paths expose the same surface — `with connection() as conn:` then
`conn.execute(sql, params).fetchone()` — so the tools are written once. Two
differences are absorbed inside `db.py`:

- **Placeholders.** psycopg binds `%s`; the Data API binds by name. Aurora
  rejects `%s` with `SQLState 42601`, so `to_named_sql()` rewrites `%s` to
  `:p1, :p2` and leaves literal percent signs inside `ILIKE '%…%'` alone.
- **Types.** The Data API returns every scalar as JSON, so a `date` column
  arrives as `"2026-11-12"`. `_row()` coerces ISO date strings so both paths
  return the same Python types.

---

## 2. RAG design

### Corpus

Sixteen policy documents in three formats (Markdown, HTML, PDF-derived text), so
the ingester is exercised on more than one parser.

- Documents: 16 (`POL-001` … `POL-012`, plus annexes `001A`, `002A`, `005A`, `006A`)
- Chunks: **173**, all embedded at 1024 dimensions
- Topics: PTO and sick leave, holidays, remote and hybrid work, international and
  cross-state work, expenses, information security, benefits, leave of absence,
  onboarding, equipment, code of conduct, HR escalation

**Known shortfall.** The brief asks for 30–120 pages; the corpus is roughly 11–22
pages depending on words-per-page assumptions. This is the largest unmet
requirement and is recorded rather than padded.

### Chunking

Heading-aware, then size-bounded. `MarkdownHeaderTextSplitter` splits on `#`,
`##` and `###`, so a chunk never spans two policy sections; a
`RecursiveCharacterTextSplitter` at 1600 characters with 240 overlap then bounds
any section that is longer. Section metadata (`document_id`, `section_id`,
`heading`) travels on every chunk, which is what makes a citation like
`POL-003 §4.3` possible rather than a document-level reference.

### Embeddings and index

Titan Text Embeddings v2, 1024 dimensions, in-region `us-east-2`, stored in a
`vector(1024)` column with an HNSW cosine index.

### Retrieval

`search_policy_documents(query, limit=5)` computes cosine similarity, keeps
matches at or above a floor of **0.2** (`QUANTIC_MIN_SIMILARITY`), and returns
`document_id`, `section_id`, `heading`, `content` and `score` per hit.

An ILIKE fallback runs when no chunk carries an embedding, when AWS credentials
are absent, or when Bedrock fails — and reports which path it used, so the trace
distinguishes a vector result from a degraded one.

**Two floors, deliberately.** 0.2 governs retrieval, because recall helps the
model; **0.35** governs what is *displayed* as a citation, because a weak match
presented as evidence invites the reader to trust something the corpus only
half-supports. The displayed list is also capped at three and sorted
strongest-first.

### Citations

Built from tool results, not from the model's text. Each citation carries its own
snippet — the passage travels with the citation rather than in a parallel list,
so sorting or capping cannot separate a citation from its evidence. A compliance
result has no passage behind it, so it carries the tool's own `reason` instead.
Traces where `is_error` is true are skipped.

---

## 3. MCP server design

**Transport: stdio.** The server is spawned by the agent as a subprocess
(`python -m quantic_hr.mcp_server`). Chosen because the brief's free-tier shape is
one service, and stdio needs no port, no auth and no second host. The code is
transport-agnostic: the same module would run over Streamable HTTP for a separate
service.

**Discovery.** The agent calls `session.list_tools()` at runtime and builds the
model's `toolConfig` from the returned JSON Schemas. There is no hand-written
tool list, so a schema change cannot drift from what the model sees.

**Tool surface (eight):**

| Tool | Kind | Purpose |
|---|---|---|
| `search_policy_documents` | RAG | Cosine search over `policy_chunks` |
| `get_policy_section` | RAG | One section by `document_id` + `section_id` |
| `lookup_employee_profile` | Structured data | Employee, location, work model |
| `check_pto_balance` | Structured data | PTO in days as of a date |
| `lookup_benefits_status` | Structured data | Benefits election and eligibility |
| `check_policy_compliance` | Rules + RAG | Deterministic route with a real citation |
| `draft_hr_email` | Mock action | Draft only; states that nothing was sent |
| `create_mock_hr_ticket` | Mock action | Requires explicit confirmation |

At least one tool uses the RAG index and at least one uses structured mock data,
as required. All calls go through the MCP session — no tool is invoked as a bare
function.

**Argument safety.** Before each `call_tool`, `employee_id` is overwritten with
the session's employee:

```python
if "employee_id" in arguments:
    arguments["employee_id"] = employee_id  # the session decides whose data is read
```

A model that tries to read another employee's records cannot, because the
argument never reaches the tool unmodified.

**Write safety.** The only write path is `create_mock_hr_ticket`, which returns a
preview unless `confirm=True`. The Data API path additionally refuses anything
that is not a single `SELECT`/`WITH` statement.

---

## 4. Agent orchestration

A LangGraph state machine with one primary path and one degraded path.

**Primary: the Bedrock Converse tool-use loop.** Up to six rounds. Each round
sends the conversation plus the discovered tool schemas; if `stopReason` is
`tool_use`, every returned `toolUse` is executed over MCP and appended as a
`toolResult` before the next round. The loop ends on a non-tool stop reason.

**Conversation history.** Prior turns are seeded ahead of the current message, so
a follow-up resolves in context. Only the question and the final answer are
replayed; earlier tool output is deliberately excluded, because re-sending a
stale `toolResult` invites the model to cite a result it did not retrieve in this
run.

**Abstain.** The agent refuses rather than guesses when the loop produces no
citations, no text, or the model returns the abstain sentence. The message names
where to go instead of inventing policy.

**Degraded path.** If `QUANTIC_AGENT_MODE=keyword`, or `auto` with no credentials,
or the Bedrock call raises `BedrockUnavailable`, a local keyword router plans tool
calls and a template synthesises the answer. `mode` and `fallback_reason` are
returned so the trace distinguishes an LLM answer from a template one.

**Operational traces, not hidden reasoning.** Every tool call is recorded with its
name, arguments and output summary, and returned to the UI as `steps` and
`tool_trace`. Reasoning tags are stripped from the answer text, so the response
carries the answer and the trace carries the steps.

---

## 5. Safety guardrails

Two deterministic pre-flight checks run in `bff.py` before the agent, so they cost
no model call and appear in the trace as an explicit step.

| Trigger | Behaviour | Verified example |
|---|---|---|
| Request too vague to apply policy | Clarification question | "Can I take some time off?" → `needs_clarification: true` |
| Question outside the corpus | Refusal with a redirect | "What is the CEO's salary?" → `refused: true` |
| In-corpus question | Model + tools + citations | "Can I work from Portugal for six weeks?" |

The clarification check distinguishes a **question about policy** from a **request
needing specifics**. "How many vacation days do I accrue?" is answerable from the
corpus and passes through; "Can I take some time off?" is a request with no dates
and asks for them. An inquiry short-circuit runs first, so a question phrased as a
request but asking about the rules is answered rather than deflected.

Beyond the guardrails: no irreversible action exists. `create_mock_hr_ticket`
requires confirmation; `draft_hr_email` never sends. The application is read-only
against the database.

**Known limitation.** The Data API secret is the cluster admin login. The
application refuses writes, but the database itself would not stop a write made
with that credential. A read-only database role with its own secret closes this;
it requires a database write and was not performed, because the shared cluster is
owned by another project.

---

## 6. Deployment

**Host: Render free web service**, region Ohio — closest Render region to
`us-east-2`. One Docker image serves the API, the MCP server as a subprocess, and
the built React UI.

| Variable | Value |
|---|---|
| `AWS_REGION` | `us-east-2` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | IAM user `quantic-hr-render`, set in the dashboard (`sync: false`) |
| `DB_MODE` | `data_api` |
| `DB_CLUSTER_ARN` / `DB_SECRET_ARN` | The existing cluster and admin secret |
| `CLUSTER_ARN` / `SECRET_ARN` | Same values — the names `db.py` reads |
| `DB_NAME` | `quantic_hr_agent` |
| `DB_RESUME_WAIT_SECONDS` | `60` |
| `CHAT_MODEL` | `us.amazon.nova-pro-v1:0` |
| `BEDROCK_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` |
| `QUANTIC_AGENT_MODE` | `auto` |
| `QUANTIC_RETRIEVAL` | `auto` |
| `QUANTIC_MIN_SIMILARITY` | `0.2` |

**IAM least privilege.** One inline policy: `bedrock:InvokeModel` on the Nova Pro
inference profile and the foundation models in each destination region, on the
Titan v2 foundation model, `rds-data:ExecuteStatement` and
`BatchExecuteStatement` on the one cluster ARN, and `secretsmanager:GetSecretValue`
on the one secret ARN. No wildcards. The simulator confirms `rds:DeleteDBCluster`,
`secretsmanager:PutSecretValue` and `s3:ListAllMyBuckets` are denied. Note that
`bedrock:InvokeModel` also authorises Converse — the Converse API reference states
this — so no separate `bedrock:Converse` action is granted.

**Cold start.**

| Event | Cost |
|---|---|
| Render free spin-down after ~15 min idle | 30–60 s on the next request |
| Aurora auto-pause after 300 s idle | up to 60 s, retried inside the app |
| Warm request, two tool rounds | ~6 s |

`/ping` deliberately touches neither the database nor Bedrock, so Render's health
check never keeps Aurora awake. The trade-off is that the first request after an
idle period pays both resume costs.

**Infrastructure as code.** The existing `QuanticHrAgentStack` CDK is kept as a
record of the database stack. `cdk deploy` must not be run from this branch: a
read-only `cdk diff` showed it would replace both isolated DB subnets and the
database security group. `QUANTIC_ALLOW_AWS_DEPLOY=no` guards the deploy script.

---

## 7. Evaluation

### Method

25 gold cases in `evaluation/eval_set.jsonl`, each carrying `gold_answer`,
`gold_docs`, `expected_tools`, `expected_route` and `expected_behavior`.

| Category | n | What it tests |
|---|---|---|
| simple_policy | 8 | Retrieval only |
| multi_document | 5 | Two or more documents, or an escalation route |
| tool_requiring | 6 | Must call a data tool, and retrieve policy |
| ambiguous | 3 | Under-specified requests |
| out_of_scope | 3 | Questions the corpus does not cover |

`evaluation/run_eval.py` drives `/chat`, records the full evidence trail per case
(question, decision path, every MCP call with arguments and output, citations,
route, latency) and writes `results.jsonl`, `summary.md` and one transcript per
case. The dashboard at `/evaluation` reads the same file.

### Results

Measured on the deployment branch.

| Metric | Value |
|---|---|
| Citation accuracy | 0.692 |
| Tool selection accuracy | 0.733 |
| Behaviour accuracy | **1.0** |
| Route accuracy | 0.727 |
| Workflow completion | **1.0** |
| Overall outcome | 17 all-passed · 5 citations · 3 route |

Behaviour accuracy of 1.0 means every case did the right *kind* of thing —
answered, refused or clarified — which is the guardrail requirement. Completion of
1.0 means none hung or errored. The two gaps are citations (5 cases) and route
(3).

### Latency

Measured warm, on the deployed service, over 25 cases.

| p50 | p95 | min | max |
|---|---|---|---|
| 6053 ms | 10328 ms | 4801 ms | 10912 ms |

p95 is not a tail of slow queries — it is the cases that need four sequential
Bedrock calls: tool selection, query embedding, retrieval, then synthesis. p50 at
6 s is the two-call path. Measured cold, add Render's 30–60 s wake plus an Aurora
resume of up to 60 s; those are not in these figures. Much of the warm cost is
re-handshaking: `_converse_loop` opens a fresh MCP session per request, which is
1–2 s before any model call.

### The defect the evaluation found

Every top-level policy section was stored with `section_id = '0'`, so citations
rendered as `s0` and were scored as misses. The corpus writes those headings as
`## 1. Observed Holidays`; the section regex required a space directly after the
number, so the pattern never matched. Making the trailing dot optional
(`^(\d+(?:\.\d+)*)\.?\s+(.*)$`) repaired POL-002 §1, POL-005 §1, POL-006 §7 and
POL-010 §3 — four of five citation failures — and moved citation accuracy from
0.542 to 0.692.

Because chunk ids derive from `document_id`/`section_id`/index, the fix renumbers
affected chunks. `scripts/rebuild_rag.sh` therefore deletes `policy_chunks` and
reloads from `corpus/`, failing the run if any chunk still carries section id `0`.

### A grounding failure the evaluation found

"What if I buy a $400 chair?" was answered as *not* reimbursable, citing
POL-005 §2.3 — the "What is not reimbursed" section. The model applied an
above-the-limit exclusion to a figure *below* the limit and inverted the
conclusion. The citation was real; the inference was not.

Three causes, and the fixes differ:

- `check_policy_compliance` returned `unsupported check_type` for the label the
  model chose, leaving the numeric comparison to be read from prose. The tool now
  accepts the names the model actually produces and performs the comparison in
  code.
- The limit was hardcoded. It is now read from the policy text, so the figure in
  the answer and the citation behind it come from one source, and a corpus edit
  propagates. If no figure can be read, the tool reports that rather than
  inventing a threshold.
- Retrieval was not always attempted, so some runs produced no citations at all
  and abstained. The prompt now requires `search_policy_documents` before any
  policy answer.

A related observation: the relevant per-item limit lives in the **annex**
(`POL-005A §0`, "Home Office Set-Up": desk $320, ergonomic chair $410), while
POL-005 §2.1 states a $500 one-time stipend. Both are in the corpus and they
differ. Which governs is a policy-authoring question, and the annex currently
wins by retrieval score. Worth resolving in the corpus rather than in code.

### Not yet measured

Three items the brief names are absent, and are recorded here rather than implied:

- **An ablation.** Planned: retrieval floor 0.2 versus 0.35, or keyword versus vector.
- **p50/p95 split by cold and warm.** The figures above are warm-only.
- **A groundedness score from a labelled judge.** The harness reports a proxy — an
  answer exists and every citation shown was retrieved this run — not a per-claim
  entailment judgement.

---

## 8. The two demo tasks

### Task A — remote work from another country

**Question:** "Can I work from Portugal for six weeks?" · **Employee:** E1011

```
1. search_policy_documents
     {"query": "remote work abroad"}
2. check_policy_compliance
     {"employee_id": "E1011", "destination_region": "PT", "check_type": "remote_work"}
```

**Result:** "Working from Portugal for six weeks is not compliant with the remote
work policy [POL-003 4.3]. You need both People Operations and Legal approval for
working outside the United States for more than 30 consecutive days."

**Citations:** POL-003 §2.3, §4.3, §2.2 · **Latency:** 12971 ms

The model chose both tools and supplied `destination_region: PT` by parsing the
question; neither call is hard-coded.

### Task B — PTO request with manager approval

**Question:** "Can I take 3 days of PTO next week?" · **Employee:** E1012

```
1. check_pto_balance          {"employee_id": "E1012"}
2. check_policy_compliance    {"employee_id": "E1012", "requested_days": 3, "check_type": "pto"}
```

**Result:** "You have sufficient PTO balance for 3 days, but manager approval is
required [POL-001 2.1]."

**Citations:** POL-001 §2.1

This task chains two tools: the balance establishes sufficiency, the compliance
check establishes the approval requirement.

### Guardrail demonstrations

| Question | Response |
|---|---|
| "What is the CEO's salary?" | `refused: true` — the corpus does not cover compensation |
| "Can I take some time off?" | `needs_clarification: true` — dates and duration requested |

---

## 9. Test suite

`tests/` holds the offline suite, which runs in CI on every push.

| File | Covers |
|---|---|
| `test_tool_contract.py` | Every MCP wrapper matches its `tools.py` signature; defaults agree; docstrings carry Args/Returns and a when-to-call line; the write tool documents confirmation; units are days, not hours |
| `test_agent_and_bff.py` | Endpoint contracts and agent behaviour |
| `test_mcp.py` | Starts the real stdio server and calls a tool over the protocol |

`test_tool_contract.py` exists because of a specific failure: the PTO tool moved
from `requested_hours` to `days_requested`, the wrapper was not updated, and the
published schema was wrong until a request failed. The test compares
`inspect.signature` of wrapper and implementation, which catches that class of
defect without a database.

**CI.** `.github/workflows/app.yml` runs on every push and pull request:
`uv sync --group dev`, `uv run pytest -q`, an import check across the app modules,
and `npm ci && npm run build` for the frontend. The `infrastructure` workflow runs
the CDK jest suite.

**Known gap.** The MCP discovery test needs a database and skips in CI, so no MCP
call currently runs there. A database-free discovery assertion — list tools,
assert the eight names and that `check_policy_compliance` takes `days_requested` —
would close it without infrastructure.

---

## 10. What is not complete

Recorded plainly, because these are what stand between the current state and the
rubric's score-5 wording.

| Item | Status |
|---|---|
| Corpus of 30–120 pages | **Not met** — ~11–22 pages |
| Evaluation ablation | **Not produced** |
| p50/p95 split cold vs warm | **Not produced** |
| Labelled groundedness score | **Not produced** — proxy only |
| MCP discovery test in CI | **Not met** — test exists, skips without a database |
| Read-only database role | **Not done** — needs a database write |
| Escalation flag | No code path sets `escalation=true`; the UI renders the panel only if present |
| Annex section numbering | Annexes use `A.x`, which the section regex does not match, so their citations read `§0` |
| Demo video | Not recorded |
