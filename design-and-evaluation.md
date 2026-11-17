# Design and Evaluation

Quantic HR Agent — an agentic Retrieval-Augmented Generation system over a
synthetic Acme Corp HR policy corpus, deployed on Render, answered through Amazon
Bedrock, with every structured lookup reached through Model Context Protocol
(MCP) tools.

- **Deployed URL:** https://quantic-hr-agent-dcw4.onrender.com
- **Health:** https://quantic-hr-agent-dcw4.onrender.com/health
- **Evaluation dashboard:** https://quantic-hr-agent-dcw4.onrender.com/evaluation
- **Branch:** `main` (identical to `fix/bedrock-wiring-2026-11-11`)
- **Region:** AWS `us-east-2`

---

## 1. Architecture

One Render web service serves the API and the built React UI on the same origin,
so production has no CORS boundary and no second host on the free tier.

```
Browser (React UI, served by the same service)
   │  POST /chat        GET /employees, /threads, /evaluation, /health, /ping
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
          │     ├─ session.initialize()           MCP handshake
          │     ├─ session.list_tools()           live discovery
          │     ├─ bedrock.converse(...)          model chooses tool + arguments
          │     ├─ session.call_tool(name, args)  executed over MCP
          │     └─ toolResult appended → loop
          └─ _collect          citations from successful traces only
   │
   ▼  MCP server (src/quantic_hr/mcp_server.py, FastMCP over stdio)
   │     eight tools, each with a declared argument vocabulary
   ▼
db.py  ── Aurora PostgreSQL Serverless v2, pgvector(1024) HNSW
   │       reached through the RDS Data API over HTTPS
   ▼
Bedrock us-east-2:  amazon.nova-pro-v1:0 (Converse), titan-embed-text-v2:0
```

The layers the brief asks to be distinguishable are separate modules: `bff.py`
(web app), `agent.py` (orchestration and MCP client), `mcp_server.py` (MCP server
and tool schemas), `tools.py` (RAG and the rule engine), `db.py` (storage),
`bedrock.py` (LLM and embedding provider).

### Why the Data API rather than psycopg

The Aurora cluster sits in private subnets and its DNS name resolves to an
address with no route from a workstation: `nc -vz <endpoint> 5432` hangs rather
than refusing. The Data API is HTTPS with SigV4, so the same database is
reachable from anywhere without a VPN, a bastion or an open port. `db.py`
prefers the Data API when `CLUSTER_ARN` and `SECRET_ARN` are set, and falls back
to psycopg only where a route exists.

Both paths expose the same surface — `with connection() as conn:` then
`conn.execute(sql, params).fetchone()` — so the tools are written once. Two
differences are absorbed inside `db.py`:

- **Placeholders.** psycopg binds `%s`; the Data API binds by name. Aurora
  rejects `%s` with `SQLState 42601`, so `to_named_sql()` rewrites `%s` to
  `:p1, :p2` and leaves literal percent signs inside `ILIKE '%…%'` alone.
- **Types.** The Data API returns every scalar as JSON, so a `date` column
  arrives as the string `"2026-11-15"` while psycopg returns a `date` object.

**That second difference caused a real fault.** `check_pto_balance` did
arithmetic on the two values and raised:

```
TypeError: unsupported operand type(s) for -: 'str' and 'str'
```

Every PTO question failed with the tool erroring, and the agent then reported
that it could not find the employee's records — an infrastructure fault
presented as a content finding. `_as_date()` now coerces both paths to a `date`
before the calculation. It is the clearest example in this project of a defect
that exists only because of the storage choice, and it is recorded here because
the mitigation is specific: any code path shared between psycopg and the Data
API needs a type-normalisation boundary.

---

## 2. RAG design

### Corpus

**35 documents, ~40 pages**, in three formats (Markdown, HTML, PDF-derived
text), so the ingester is exercised on more than one parser.

- Base policies POL-001 … POL-020, plus annexes POL-001A, POL-002A, POL-005A,
  POL-006A, POL-009A
- Expansion policies POL-021 … POL-030: contractor engagement, business
  continuity, learning and development, relocation, AI tool use, grievance and
  disciplinary, records retention, employee relations cases, intellectual
  property, workplace accommodation
- Chunks: **312**, all embedded at 1024 dimensions

The corpus was authored for this project and deliberately cross-references: an
expense limit is stated in POL-005 and worked through in POL-005A; a retention
period is named in POL-017 and tabulated in POL-027. That makes multi-document
retrieval a real problem rather than a nominal one.

### Chunking

Heading-aware, then size-bounded. Sections are split on `#`, `##`, `###`
(markdown) and `<h1>`–`<h3>` (HTML); a section longer than 300 words is split
further with a `:1`/`:2` suffix on the chunk id. Section metadata
(`document_id`, `section_id`, `heading`) travels on every chunk, which is what
makes a citation like `POL-001 2.1` possible rather than a document-level
reference.

### Section parsing — a defect worth recording

The original pattern was `^(\d+(?:\.\d+)*)\.?\s+(.*)$`. Two faults:

1. A heading written `## 1. Observed Holidays` matched only when no dot followed
   the number, so many top-level sections were stored as `section_id = '0'`.
2. Annex documents number their sections `A.1`, `A.2`, which a digits-only
   pattern cannot match at all.

Every affected chunk was unaddressable — a citation read `POL-005A s0`, which
points at nothing a reader can open, and the retrieval scorer counted it as a
miss. `src/quantic_hr/sections.py` now handles numbered, annex, letter, roman,
HTML and unnumbered headings; an unnumbered heading inherits its enclosing
section rather than starting a new one. On the current corpus, **0 chunks carry
section id `0`**.

### Embeddings and index

Titan Text Embeddings v2, 1024 dimensions, in-region, stored in a `vector(1024)`
column with an HNSW cosine index. Ingestion runs through the Data API as well
(`scripts/refresh_via_data_api.py`), for the same reason reads do.

### Retrieval

`search_policy_documents(query, limit=5)` computes cosine similarity and keeps
matches at or above `QUANTIC_MIN_SIMILARITY` (default **0.2**). An ILIKE fallback
runs when no chunk carries an embedding, credentials are absent, or Bedrock
fails — and reports which path it used, so a trace distinguishes a vector result
from a degraded one.

**One floor, not two.** An earlier version used 0.2 for retrieval and 0.35 for
display. That meant a passage scoring between them could support the answer while
the citation panel showed nothing: an answer grounded in text the reader was told
did not exist. The floor is now shared, and the reader is protected by the
citation count (3) and strongest-first ordering instead.

**Known limitation — cross-reference sections.** Index and cross-reference
sections are strong lexical matches. `POL-020 §2 "Which Policy Governs"` and
`POL-009 §11 "Related Policies"` score 0.35–0.40 for a PTO question, above the
section that states the rule, and when the model chooses `limit: 1` it can
receive a policy's introduction rather than its substance. This is the largest
single cause of the citation accuracy reported in section 8. The identified
mitigations are to exclude or down-weight cross-reference sections in retrieval,
or to pre-retrieve with a fixed query and `limit` for known question shapes
rather than letting the model choose.

---

## 3. The rule engine

`check_policy_compliance` is a small rule engine, not a chain of `if`s, and the
design is deliberate.

**Rules are data.** `mock_data/policy_rules.json` holds each limit with the
section that states it, so a verdict cites the text it came from. The PTO
accrual rate and the carryover cap are there too, each with its own citation —
the rate from POL-001 §2.1, the cap from §4.1 — so the two can change
independently.

**The rate is not read from the database.** `pto_accruals.accrual_days_per_month`
exists, but the tool ignores it. A rule stored in a table is a rule the policy
cannot govern: edit POL-001 and the answers would not move. Reading it from the
rules file, with a citation, means the sentence a reader checks is the sentence
the answer used. The corpus was changed to state the pro-rata method explicitly,
so the cited section supports the figure the answer reports.

**One result shape.** `checked`, `compliant`, `route`, `reason`, `comparison`,
and the sections that supplied each figure. A check that could not run returns
`checked: false, compliant: null` — **never `false`**.

**That distinction was the single most consequential fix in the project.** The
tool originally returned `compliant: false` for "I could not check", which the
model read as the policy forbidding the purchase. Combined with a retrieved
passage titled "What is not reimbursed", it produced a confident, correctly
cited, inverted answer: **a $400 chair reported as breaking a $500 limit.** The
citation was real; the inference was never performed. Three changes followed:
the unsupported-check result became `null` rather than `false`, the check-type
vocabulary was declared in the MCP docstring so the model stopped inventing
names, and the comparison is now computed in code and returned as
`"comparison": "400.00 <= 500.00"` so the model reports arithmetic rather than
reasoning over prose.

### The accrual, worked

```
days_elapsed = as_of − max(1 January, hire_date)
months       = days_elapsed ÷ 30.4375         (AVERAGE_MONTH_DAYS = 365.25 / 12)
accrued      = 1.25 × months
available    = accrued + min(carryover, 5) − taken − pending
```

For E1007 on 15 November 2026: 318 days, 10.4476 months, 13.06 accrued, 2.00
carryover applied against a 5-day cap, 4.00 taken, 0.00 pending →
`available_days: 11.06`, with
`available_formula: "13.06 + 2.00 - 4.00 - 0.00 = 11.06"` returned alongside.

The divisor is named and derived in code as well as declared in the rules file,
and the tool refuses to run if the two disagree. A bare `30.4375` in an
expression is the kind of number a reader cannot account for six months later.

---

## 4. MCP server and tools

**Transport: stdio.** The server is spawned by the agent as a subprocess. Chosen
because the brief's free-tier shape is one service, and stdio needs no port, no
auth and no second host. The code is transport-agnostic: the same module would
run over Streamable HTTP for a separate service.

**Discovery.** The agent calls `session.list_tools()` at runtime and builds the
model's `toolConfig` from the returned JSON Schemas. There is no hand-written
tool list, so a schema change cannot drift from what the model sees.

**Eight tools:**

| Tool | Kind | Purpose |
|---|---|---|
| `search_policy_documents` | RAG | Cosine search over `policy_chunks` |
| `get_policy_section` | RAG | One section by document id and section id |
| `lookup_employee_profile` | Structured data | Employee, location, work model |
| `check_pto_balance` | Structured data | Balance computed from the policy rule |
| `lookup_benefits_status` | Structured data | Benefits election and eligibility |
| `check_policy_compliance` | Rules + RAG | Deterministic route with a real citation |
| `draft_hr_email` | Mock action | Draft only; states that nothing was sent |
| `create_mock_hr_ticket` | Mock action | Requires explicit confirmation |

At least one tool uses the RAG index and at least one uses structured data, as
required. All calls go through the MCP session; no tool is invoked as a bare
function.

**Argument vocabularies are declared.** The MCP docstrings are the interface the
model reads, so each tool lists allowed values, units, and when to call it.
Before this, `check_type` had no declared domain and the model invented
`office_furniture`, `reimbursement` and `office_chair_purchase` — three of the
five names it used. A tool whose input domain is undefined is a tool that will be
called wrongly.

**Argument safety.** Before each `call_tool`, `employee_id` is overwritten with
the session's employee, so a model that tries to read another employee's records
cannot.

**Write safety.** The only write path is `create_mock_hr_ticket`, which returns a
preview unless `confirm=True`. `db.execute()` applies a select-only guard that
rejects anything but a single `SELECT`/`WITH` statement, and the per-chat prompt
log is off unless `QUANTIC_PROMPT_LOG=1`.

---

## 5. Agent orchestration

A LangGraph state machine with one primary path and one degraded path.

**Primary: the Bedrock Converse tool-use loop.** Up to six rounds. Each round
sends the conversation plus the discovered tool schemas; if `stopReason` is
`tool_use`, every returned `toolUse` is executed over MCP and appended as a
`toolResult` before the next round. The loop ends on a non-tool stop reason.

**Retrieval before calculation.** The prompt requires `search_policy_documents`
first, then the data tool, then the compliance check. The policy states the rule;
the data tool states this employee's facts.

**Abstain, and what counts as evidence.** The agent refuses rather than guesses
when it has nothing to answer from. Two fixes were needed:

- A successful data tool result **is** evidence. The agent previously abstained
  when citations were empty, discarding a live balance the tool had already
  returned and telling the user their HR records could not be found.
- The test for the abstain sentence was a substring match, so any answer that
  mentioned the phrase was replaced by the canned refusal. It is now an exact
  match, and a successful data tool overrides even that.

**A successful tool call is never reported as an outage.** When every tool call
fails, the agent says the database is waking rather than that the policy does not
exist.

**Conversation history** seeds prior turns so a follow-up resolves in context.
Only the question and the final answer are replayed; earlier tool output is
excluded, because re-sending a stale `toolResult` invites the model to cite a
result it did not retrieve in this run.

**Operational traces, not hidden reasoning.** Every tool call is recorded with
its name, arguments and output summary, and returned to the UI as `steps` and
`tool_trace`. Reasoning tags are stripped from the answer text, so the response
carries the answer and the trace carries the steps.

---

## 6. Safety guardrails

Two deterministic pre-flight checks run in `bff.py` before the agent, so they
cost no model call and appear in the trace as an explicit step.

| Trigger | Behaviour | Verified example |
|---|---|---|
| Request too vague to apply policy | Clarification question | "Can I take some time off?" |
| Question outside the corpus | Refusal with a redirect | "What is the CEO's salary?" |
| In-corpus question | Model + tools + citations | "Can I work from Portugal for six weeks?" |

The clarification check distinguishes a *question about policy* from a *request
needing specifics*: "How many vacation days do I accrue?" is answerable from the
corpus, while "Can I take some time off?" is a request with no dates and prompts
for them.

Beyond the guardrails, no irreversible action exists. `create_mock_hr_ticket`
requires confirmation, `draft_hr_email` never sends, and the application is
read-only against the database.

**Known limitation.** These guards match a narrower set of phrasings than the
evaluation exercises. Six ambiguous and out-of-scope cases were answered rather
than clarified or refused, which is the behaviour accuracy reported in section 8.

---

## 7. Deployment
**Render free web service**, region Ohio. One Docker image serves the API, the
MCP server as a subprocess, and the built React UI.

| Variable | Value |
|---|---|
| `AWS_REGION` | `us-east-2` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | IAM user, set in the dashboard (`sync: false`) |
| `DB_MODE` | `data_api` |
| `CLUSTER_ARN` / `SECRET_ARN` | The cluster and its Data API secret |
| `DB_NAME` | `quantic_hr_agent` |
| `DB_RESUME_WAIT_SECONDS` | `60` |
| `CHAT_MODEL` | `us.amazon.nova-pro-v1:0` |
| `BEDROCK_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` |
| `QUANTIC_MIN_SIMILARITY` | `0.2` |
| `QUANTIC_BUILD` | Reported on `/health`, so a deploy can be verified in one request |

**IAM least privilege.** One inline policy: `bedrock:InvokeModel` on the Nova Pro
inference profile and the Titan v2 foundation model, `rds-data:ExecuteStatement`
and `BatchExecuteStatement` on the one cluster ARN, and
`secretsmanager:GetSecretValue` on the one secret ARN. No wildcards.

**Cold start.**

| Event | Cost |
|---|---|
| Render free spin-down after ~15 min idle | 30–60 s on the next request |
| Aurora auto-pause after 300 s idle | the first request returns "the HR database is waking up" |

`/ping` deliberately touches neither the database nor Bedrock, so Render's health
check never keeps Aurora awake. `/health` does touch the database, which is what
wakes it — useful immediately before a demonstration.

**Build marker.** `/health` reports a `build` string. A source grep proves the
file on disk; only this proves the file running, and without it a fix can be
committed, pushed and never deployed without anyone noticing.

**Infrastructure as code.** The existing `QuanticHrAgentStack` CDK is kept as a
record of the database stack. `cdk deploy` must not be run from this branch: a
read-only `cdk diff` showed it would replace the DB subnets and the database
security group.

### Why paid AWS services, and what has to change to run free

The brief prefers free options and allows "your own API keys". Two components
deviate from a pure free-tier shape, and each has a stated escape hatch.

**Bedrock (Nova Pro chat, Titan v2 embeddings)** is pay-per-token with no standing
charge; a full 30-case evaluation run costs well under a dollar. Any
OpenAI-compatible free tier is a drop-in change behind the same Converse-shaped
client: only `CHAT_MODEL` and `EMBED_MODEL` change.

**Aurora Serverless v2 with pgvector** was chosen to match the stack this build is
made on — React against Postgres. It auto-pauses when idle, so cost is bounded to
active minutes plus storage. The application runs unchanged on any free Postgres
with pgvector by setting `DB_MODE=psycopg` and a `DATABASE_URL`; local development
and CI already take that path.

**Hosting** is the Render free tier. No paid hosting is required.

An AWS Budget alert caps the exposure.


---

## 8. Evaluation

<!-- BEGIN METRICS -->
_Measured on the deployed service. Source: [`evaluation/results/summary.md`](evaluation/results/summary.md), generated 2026-11-17._

| Metric | Value |
| --- | --- |
| Citation accuracy | 0.386 |
| Tool selection accuracy | 0.932 |
| Route accuracy | 0.625 |
| Workflow completion rate | 1.0 |
| Behaviour accuracy | 0.767 |
| Latency p50 | 13665 ms |
| Latency p95 | 15358 ms |

<!-- END METRICS -->

### Method

30 gold cases in `evaluation/eval_set.jsonl`, each carrying a `gold_answer`,
`gold_docs`, `expected_tools`, `expected_route` and `expected_behavior`.

| Category | n | What it tests |
|---|---|---|
| simple_policy | 8 | Retrieval only |
| multi_document | 7 | Two or more documents, or a threshold pair |
| tool_requiring | 7 | Must call a data tool, and retrieve policy |
| ambiguous | 4 | Under-specified requests |
| out_of_scope | 4 | Questions the corpus does not cover |

`evaluation/run_eval.py` drives `/chat` against the deployed service, records the
full evidence trail per case, and writes `results.jsonl`, `summary.md` and one
transcript per case. The dashboard at `/evaluation` reads `/evaluation/results`.

### Results

Measured warm, on the deployed service, 16 November 2026.
| Metric | Value |
|---|---|
| Citation accuracy | 0.386 |
| Tool selection accuracy | 0.932 |
| Route accuracy | 0.625 |
| Workflow completion rate | 1.0 |
| Behaviour accuracy | 0.767 |
| Latency p50 | 13665 ms |
| Latency p95 | 15358 ms |


By category:

| Category | n | Citation acc. | Route acc. | Behaviour |
|---|---|---|---|---|
| simple_policy | 8 | 0.500 | — | 1.000 |
| multi_document | 7 | 0.357 | 1.000 | 0.857 |
| tool_requiring | 7 | 0.357 | 0.571 | 1.000 |
| ambiguous | 4 | — | — | 0.250 |
| out_of_scope | 4 | — | — | 0.250 |

Workflow completion at 1.0 means no case hung, errored or exhausted its step
budget. Tool selection at 0.932 means the expected tools were called in almost
every case.

### Latency

Warm latency is p50 13.6 s and p95 16.8 s. The cost is **four sequential Bedrock
calls** — tool selection, query embedding, retrieval, synthesis — which cannot be
parallelised within the Converse tool-use contract. It is not a tail of slow
queries: p50 and p95 are within 25% of each other. Two overheads are identifiable
but were not removed: the MCP session is re-established per request (roughly 1–2 s
of every question), and the model chooses its own retrieval depth, so a `limit: 1`
search occasionally forces an extra round. Cold, add Render's 30–60 s wake and
Aurora's resume.

### Limitations, with causes

***Citation accuracy 0.386.** Scored at section granularity, the stricter measure.
The loss concentrates in synthesis: `simple_policy` scores 0.625, while
`multi_document` and `tool_requiring` score 0.286 and 0.214. Single-document
questions cite the exact section; answers that combine sources cite the parent
section or a sibling stating the same rule. The dominant cause remains retrieval
preferring cross-reference sections over rule sections — `POL-020 §2` and
`POL-009 §11` score 0.35–0.40 against almost any question.

**Behaviour accuracy 0.767.** Six cases were answered rather than clarified or
refused, because the pre-flight guardrails match a narrower set of phrasings than
the evaluation uses.

**Three gold answers are arguably wrong, not the agent.** For a $2000 laptop the
agent returned `CANNOT_DETERMINE`; for a $500 laptop and a $600 chair it returned
`PARTIAL_UP_TO_LIMIT`, where the gold expected `NEEDS_PRE_APPROVAL` and
`CLAIM_WITH_RECEIPT`. Given the $1000 pre-approval threshold and the $500
carryover-style cap, the agent's routes are defensible and the gold answers need
review rather than the code.

### Ablation: retrieval similarity floor and k

Retrieval-only, over the 22 eval cases that name gold documents. Each configuration
calls the same `search_policy_documents` path the MCP tool exposes, against the live
Aurora corpus, so the comparison reflects the deployed retriever rather than a
reimplementation. Results: `evaluation/results/ablation.json`.

| Threshold | k | Doc recall | Abstain rate | p50 ms |
|---|---|---|---|---|
| 0.20 (deployed) | 5 | 0.977 | 0.000 | 2817 |
| 0.35 | 5 | 0.705 | 0.136 | 2664 |
| 0.20 | 3 | 0.909 | 0.000 | 2539 |
| 0.20 | 8 | 0.977 | 0.000 | 2430 |

Two findings. First, the similarity floor is the effective lever: raising it from
0.20 to 0.35 costs 27 points of gold-document recall and raises retrieval-level
abstention from 0% to 13.6%, with no latency benefit. The deployed value of 0.20
deliberately favours recall. Second, k is saturated at 5: k=8 retrieves the same
gold documents as k=5 (0.977) while adding context to the prompt, and k=3 loses
7 points (0.909).

**Scope note.** This run sets `QUANTIC_MIN_SIMILARITY=0` so every candidate is
collected and each floor is applied in the harness, which is why the three 0.20 rows
show 0.0 abstention: the floor was not the filter in those rows. The 0.35 row applies
its floor directly and is the one that shows what a stricter threshold does to
abstention. Abstention at the retrieval layer is therefore not the mechanism that
handles out-of-corpus questions; the agent's abstain guardrail is, and that is scored
separately in the behaviour metrics above.


### What is not measured
- **No cold-versus-warm split.** The figures above are warm only.
- **No labelled groundedness judge.** The harness reports a proxy — an answer
  exists and every citation was retrieved in the same run.

### The measurement defects, recorded

Six defects were found and corrected in the evaluation harness during this work.
**Every one of them read as an agent failure and none of them was:**

1. The harness was pointed at `127.0.0.1:8000` rather than the deployed URL, so
   every case failed in under 400 ms and the run reported all zeros.
2. It was pointed at localhost a second time after a file was reverted,
   reproducing the same false zeros.
3. An expired AWS SSO token caused a `TokenRetrievalError` in the harness, which
   again presented as an agent failure.
4. The route was read from a `decision` step that the Bedrock path never emits,
   so the observed route was `None` on all 30 cases and route accuracy read 0.0
   regardless of what the compliance tool returned.
5. The citation reference separator differed between the gold and observed sides
   (`POL-001 2.1` against `POL-001:2.1`), so the sets never intersected.
6. Annex document ids (`POL-001A A.4`) were not normalised, so every annex
   citation scored as a miss.

The lesson is stated in section 12: **a displayed number is not evidence until
its source has been traced.** A scorer needs its own tests.

---

## 9. Demonstration tasks

Three tasks are demonstrated end to end, each requiring multi-step reasoning, RAG
retrieval, and structured or mock-data tool use.

### Task A — remote work from another country

**Question:** "Can I work from Portugal for six weeks?" · **Employee:** E1011

```
1. search_policy_documents   {"query": "remote work abroad"}
2. check_policy_compliance   {"employee_id": "E1011",
                              "destination_region": "PT",
                              "check_type": "remote_work"}
```

**Result:** not compliant with POL-003 §4.3 — working outside the United States
for more than 30 consecutive days needs People Operations and Legal approval
before travel is booked.

**Citations:** POL-003 §2.3, §4.3, §2.2

The model selected both tools and supplied `destination_region: PT` by parsing
the question; neither call is hard-coded.

### Task B — expense compliance

**Question:** "Can I claim a $400 office chair?" · **Employee:** E1007

```
1. search_policy_documents   {"query": "office chair purchase"}
2. check_policy_compliance   {"employee_id": "E1007",
                              "check_type": "expense",
                              "amount": 400,
                              "expense_category": "chair"}
```

**Result:** compliant — `comparison: "400.00 <= 500.00"`, within the $500
one-time home office stipend.

**Citations:** POL-005 §2.1, POL-005A §A.2

### Task C — PTO with a computed balance

**Question:** "Can I take 15 days PTO?" · **Employee:** E1007

```
1. search_policy_documents   {"query": "PTO policy"}
2. check_pto_balance         {"employee_id": "E1007"}
3. check_policy_compliance   {"employee_id": "E1007",
                              "check_type": "pto",
                              "days_requested": 15}
```

**Result:** refused — `route: INSUFFICIENT_BALANCE`, `comparison: "15 > 11.06"`,
`available_formula: "13.06 + 2.00 - 4.00 - 0.00 = 11.06"`.

The balance is computed from the policy rule, not read from a stored figure.

---

## 10. Test suite

| File | Covers |
|---|---|
| `test_policy_rules.py` | The rule engine with no database and no model: accrual boundaries, the carryover cap, unknown check types, the SQL guard |
| `test_tool_contract.py` | Lists all eight tools from the MCP server with no database, and asserts the published schema matches the implementation signature |
| `test_sections.py` | Heading parsing across every form present in the corpus |
| `test_agent_and_bff.py` | Endpoint contracts and agent behaviour |
| `test_mcp.py` | Starts the real stdio server and calls a tool over the protocol (needs a seeded Postgres; skipped in CI) |

The rule-engine tests exist because of the chair defect: there was no way to ask
*the rule* whether 400 was under 500 except by going through the model. A rule
layer that can only be exercised through an agent is a rule layer whose defects
surface as wrong answers.

**Known gap.** `test_mcp.py` requires a database and skips in CI, so no MCP call
runs there. `test_tool_contract.py` closes the discovery half without
infrastructure. Sixteen tests are skipped in CI for this reason, and the README
documents how to run them locally against a seeded Postgres.

---

## 11. What is not complete

| Item | Status |
|---|---|
| Evaluation ablation | Produced — retrieval floor and k, table in section 9 |
| p50/p95 split cold vs warm | Not produced |
| Labelled groundedness score | Not produced — proxy only |
| Cross-reference sections in retrieval | Known limitation, mitigation identified |
| Guardrail phrasing coverage | Known limitation — behaviour 0.767 |
| Three gold answers for expense routes | Need review; the agent's routes are defensible |

---

## 12. What this project taught

**An agent probes every hole in a tool contract, every run.** A traditional
application only ever calls a tool with arguments its own code chose. An agent
invents them. Every underspecified field and unstated rule surfaces as a wrong
answer in production rather than staying dormant, which means the tool contract
has to be written before the tool: declared vocabularies, a fixed result shape
including the failure shape, and a rule layer that can be tested without the
model.

**"I could not check" must be distinguishable from "no".** The worst defect in
this project — a $400 chair reported as breaking a $500 limit — came from a tool
whose input domain was undefined and whose inability to check was returned as a
negative verdict. A result shape that collapses those two cases will produce
confident, cited, inverted answers.

**A displayed number is not evidence until its source has been traced.** Six
defects in the evaluation harness each read as an agent failure and none of them
was: a wrong target URL twice, an expired credential, a route read from a step
that never exists, and two reference-normalisation faults. The dashboard carried
the same trap — it rendered an embedded fixture rather than the live endpoint, so
its figures were frozen for days while every run wrote correct data beside it.
The mitigation is not vigilance but mechanism: a build marker on `/health` so a
deploy can be verified in one request, and a scorer with its own tests.
