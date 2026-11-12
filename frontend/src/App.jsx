import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "";


const DEMOS = [
  { label: "Remote work abroad", employee: "E1007", message: "Can I work from Portugal for six weeks?" },
  { label: "PTO request", employee: "E1012", message: "Can I take 3 days of PTO next week?" },
  { label: "Office chair, $1500", employee: "E1007", message: "I want to buy an office chair for $1500, what does the policy say?" },
];

const S = {
  page: {
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
    maxWidth: 1280, margin: "0 auto", padding: "0 24px 120px",
    color: "#0f172a", background: "#eef2f7", minHeight: "100vh",
  },
  label: {
    fontSize: 10.5, fontWeight: 800, letterSpacing: ".1em",
    textTransform: "uppercase",
  },
  mono: {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    fontSize: 12, color: "#1e293b", wordBreak: "break-word",
  },
  pre: { whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0 },
  control: {
    borderRadius: 9, border: "2px solid #94a3b8", padding: "6px 9px",
    fontSize: 13, fontWeight: 600, background: "#fff",
  },
};

const ACCENT = {
  path:     { solid: "#1d4ed8", soft: "#e0ecff", border: "#93b8f7" },
  tools:    { solid: "#6d28d9", soft: "#efe6ff", border: "#c4a9f7" },
  evidence: { solid: "#047857", soft: "#dcfce9", border: "#8fd9b8" },
};

function Panel({ title, count, accent, children }) {
  return (
    <section style={{
      background: "#fff",
      border: "2px solid #cbd5e1",
      borderTop: `4px solid ${accent.solid}`,
      borderRadius: 14,
      boxShadow: `6px 6px 0 0 ${accent.soft}, 0 10px 28px -14px rgba(15,23,42,.35)`,
      overflow: "hidden",
      display: "flex", flexDirection: "column",
    }}>
      <header style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "11px 15px",
        background: accent.soft,
        borderBottom: `2px solid ${accent.border}`,
      }}>
        <span style={{ ...S.label, color: accent.solid }}>{title}</span>
        {count !== undefined && (
          <span style={{
            fontSize: 11.5, fontWeight: 800, color: "#fff",
            background: accent.solid, borderRadius: 999, padding: "2px 10px",
          }}>
            {count}
          </span>
        )}
      </header>
      <div style={{ padding: 15, flex: 1 }}>{children}</div>
    </section>
  );
}

function Chip({ kind }) {
  const tones = {
    tool_call:     ["#ede9fe", "#5b21b6", "#c4b5fd"],
    decision:      ["#d1fae5", "#065f46", "#6ee7b7"],
    escalation:    ["#fee2e2", "#991b1b", "#fca5a5"],
    confirmation:  ["#fef3c7", "#92400e", "#fcd34d"],
    clarification: ["#fef3c7", "#92400e", "#fcd34d"],
  };
  const [bg, fg, border] = tones[kind] || tones.tool_call;
  return (
    <span style={{
      background: bg, color: fg, border: `2px solid ${border}`,
      padding: "2px 9px", borderRadius: 999, fontSize: 10,
      fontWeight: 800, textTransform: "uppercase", letterSpacing: ".07em",
    }}>
      {kind.replace("_", " ")}
    </span>
  );
}

function ResultHeadline({ turn }) {
  const decision = (turn.steps || []).find((s) => s.kind === "decision");
  if (!decision) {
    return <div style={{ fontSize: 16, ...S.pre }}>{turn.answer}</div>;
  }
  const tone = turn.escalation
    ? { band: "#fee2e2", edge: "#b91c1c", text: "#7f1d1d" }
    : { band: "#d1fae5", edge: "#047857", text: "#065f46" };

  return (
    <div style={{
      background: tone.band,
      border: `3px solid ${tone.edge}`,
      borderRadius: 12,
      padding: "18px 20px",
      boxShadow: "0 8px 24px -12px rgba(15,23,42,.30)",
    }}>
      <div style={{
        fontSize: 27, fontWeight: 900, letterSpacing: "-.02em",
        color: tone.text, lineHeight: 1.15,
      }}>
        {decision.detail}
      </div>
      {decision.reason && (
        <div style={{ fontSize: 14.5, color: "#334155", marginTop: 9, fontWeight: 500 }}>
          {decision.reason}
        </div>
      )}
      {(decision.policy_refs || []).length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 13 }}>
          {decision.policy_refs.map((ref) => (
            <span key={ref} style={{
              ...S.mono, fontSize: 12, fontWeight: 700,
              background: "#fff", border: `2px solid ${tone.edge}`,
              borderRadius: 8, padding: "3px 9px", color: tone.text,
            }}>
              {ref}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* Tool calls and decisions only. The model's own narration is not rendered: it
   is unverified, and it has stated policy obligations that do not exist in the
   corpus. Everything shown here is built from tool output. */
function DecisionPath({ turn }) {
  const visible = (turn.steps || []).filter(
    (s) => ["tool_call", "decision", "escalation", "clarification", "confirmation"]
             .includes(s.kind)
  );

  if (!visible.length) {
    return <em style={{ fontSize: 13, color: "#94a3b8" }}>No steps recorded.</em>;
  }

  return (
    <ol style={{ margin: 0, paddingLeft: 20 }}>
      {visible.map((step, i) => (
        <li key={i} style={{ marginBottom: 14, fontSize: 13.5 }}>
          <Chip kind={step.kind} />
          {step.kind === "tool_call" ? (
            <>
              <code style={{ fontWeight: 800, marginLeft: 7, color: "#6d28d9",
                             fontSize: 13.5 }}>
                {step.tool}
              </code>
              <div style={{
                ...S.mono, marginTop: 6, background: "#faf5ff",
                border: "2px solid #ddd6fe", borderRadius: 8, padding: "7px 9px",
              }}>
                {JSON.stringify(step.arguments)}
              </div>
            </>
          ) : (
            <div style={{ marginTop: 6 }}>
              <strong style={{ fontSize: 14 }}>{step.detail}</strong>
              {step.reason && (
                <div style={{ color: "#475569", marginTop: 2 }}>{step.reason}</div>
              )}
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

function ToolCalls({ turn }) {
  const trace = turn.tool_trace || [];
  if (!trace.length) {
    return <em style={{ fontSize: 13, color: "#94a3b8" }}>No tools were called.</em>;
  }
  return trace.map((t, i) => (
    <div key={i} style={{
      borderTop: i ? "2px dashed #e2e8f0" : "none",
      paddingTop: i ? 14 : 0, marginTop: i ? 14 : 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <code style={{ fontWeight: 800, fontSize: 13.5, color: "#6d28d9" }}>{t.name}</code>
        {t.iteration !== undefined && (
          <span style={{
            fontSize: 10.5, fontWeight: 800, color: "#fff",
            background: "#6d28d9", borderRadius: 6, padding: "1px 7px",
          }}>
            iter {t.iteration}
          </span>
        )}
      </div>
      <div style={{
        ...S.mono, marginTop: 6, background: "#faf5ff",
        border: "2px solid #ddd6fe", borderRadius: 8, padding: "7px 9px",
      }}>
        {JSON.stringify(t.arguments)}
      </div>
      <div style={{ ...S.mono, color: "#64748b", marginTop: 7 }}>
        {String(t.output_summary).slice(0, 200)}
      </div>
    </div>
  ));
}

function Citations({ turn }) {
  const cites = turn.citations || [];
  if (!cites.length) {
    return <em style={{ fontSize: 13, color: "#94a3b8" }}>No passages retrieved.</em>;
  }
  return cites.map((c, i) => (
    <div key={i} style={{
      borderTop: i ? "2px dashed #e2e8f0" : "none",
      paddingTop: i ? 14 : 0, marginTop: i ? 14 : 0,
    }}>
      <div style={{ display: "flex", alignItems: "baseline",
                    justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: 13.5, fontWeight: 800, color: "#047857" }}>
          {c.document_id} §{c.section_id}
        </span>
        {typeof c.score === "number" && (
          <span style={{
            ...S.mono, fontSize: 11, fontWeight: 700, color: "#fff",
            background: "#047857", borderRadius: 6, padding: "2px 8px",
          }}>
            {c.score.toFixed(3)}
          </span>
        )}
      </div>
      <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{c.title}</div>
      <div style={{
        fontSize: 12, color: "#1e293b", marginTop: 8, ...S.pre,
        background: "#f8fafc", border: "2px solid #e2e8f0",
        borderRadius: 8, padding: "9px 11px",
      }}>
        {(c.snippet || "").slice(0, 260)}
      </div>
    </div>
  ));
}

function Turn({ turn, expanded, onToggle }) {
  const escalation = (turn.steps || []).find((s) => s.kind === "escalation");
  const needsPreApproval = (turn.steps || []).some(
    (s) => s.kind === "decision" && s.detail === "NEEDS_PRE_APPROVAL"
  );

  return (
    <article style={{ marginBottom: expanded ? 42 : 22 }}>
      <div
        onClick={onToggle}
        style={{
          background: "#fff", borderRadius: 12,
          border: "2px solid #cbd5e1", borderLeft: "6px solid #64748b",
          boxShadow: "0 6px 18px -12px rgba(15,23,42,.4)",
          padding: "14px 18px", marginBottom: 14, cursor: "pointer",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between",
                      alignItems: "flex-start", gap: 12 }}>
          <div>
            <div style={{ ...S.label, color: "#64748b", marginBottom: 6 }}>
              Question · {turn.employee_id}
              {turn.latency_ms ? ` · ${turn.latency_ms} ms` : ""}
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, ...S.pre }}>{turn.question}</div>
          </div>
          <span style={{ fontSize: 12, color: "#475569", whiteSpace: "nowrap",
                         fontWeight: 800 }}>
            {expanded ? "▲ collapse" : "▼ details"}
          </span>
        </div>
      </div>

      <div style={{
        background: "#fff", borderRadius: 14, padding: "18px 20px",
        border: `2px solid ${turn.escalation ? "#fca5a5" : "#6ee7b7"}`,
        borderLeft: `6px solid ${turn.escalation ? "#b91c1c" : "#047857"}`,
        boxShadow: "0 12px 34px -18px rgba(15,23,42,.45)",
      }}>
        <div style={{ ...S.label, color: "#64748b", marginBottom: 12 }}>Result</div>
        <ResultHeadline turn={turn} />

        {escalation && (
          <div style={{
            background: "#fee2e2", border: "2px solid #fca5a5", borderRadius: 10,
            padding: "12px 14px", marginTop: 16, fontSize: 14, color: "#7f1d1d",
            fontWeight: 600,
          }}>
            <strong>Escalation.</strong> {escalation.detail}
          </div>
        )}
        {turn.needs_clarification && (
          <div style={{
            background: "#fef3c7", border: "2px solid #fcd34d", borderRadius: 10,
            padding: "12px 14px", marginTop: 16, fontSize: 14, color: "#78350f",
            fontWeight: 600,
          }}>
            <strong>Clarification needed.</strong> {turn.answer}
          </div>
        )}
        {needsPreApproval && (
          <div style={{ fontSize: 13, color: "#475569", marginTop: 14, fontWeight: 500 }}>
            Ask a follow-up to compare, for example “what if it were $500 instead?”
          </div>
        )}
      </div>

      {expanded && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
          gap: 20, marginTop: 20, alignItems: "start",
        }}>
          <Panel title="Decision path" count={(turn.steps || []).length}
                 accent={ACCENT.path}>
            <DecisionPath turn={turn} />
          </Panel>
          <Panel title="MCP tool calls" count={(turn.tool_trace || []).length}
                 accent={ACCENT.tools}>
            <ToolCalls turn={turn} />
          </Panel>
          <Panel title="Policy citations" count={(turn.citations || []).length}
                 accent={ACCENT.evidence}>
            <Citations turn={turn} />
          </Panel>
        </div>
      )}
    </article>
  );
}

export default function App() {
  const [employeeId, setEmployeeId] = useState("E1007");
  const [employees, setEmployees] = useState([]);
  const [employeeError, setEmployeeError] = useState("");
  const [message, setMessage] = useState("Can I work from Portugal for six weeks?");
  const [turns, setTurns] = useState([]);
  const [threadId, setThreadId] = useState(null);
  const [threads, setThreads] = useState([]);
  const [openTurn, setOpenTurn] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Employees come from the database, so the dropdown cannot drift from the
  // seeded records that the compliance logic reads.
  useEffect(() => {
    fetch(`${API}/employees`)
      .then((r) => r.json())
      .then((d) => {
        const rows = d.employees || [];
        setEmployees(rows);
        if (rows.length) {
          setEmployeeId((current) =>
            rows.some((e) => e.employee_id === current)
              ? current
              : rows[0].employee_id);
        }
      })
      .catch((err) => setEmployeeError(String(err)));
  }, []);

  // Session threads, refreshed after each run so a new one appears immediately.
  useEffect(() => {
    fetch(`${API}/threads`)
      .then((r) => r.json())
      .then((d) => setThreads(d.threads || []))
      .catch(() => setThreads([]));
  }, [turns.length]);

  async function ask(question, employee, forcedThread = null) {
    if (!question.trim() || busy) return;
    setError("");
    setBusy(true);
    try {
      const response = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: question,
          employee_id: employee,
          thread_id: forcedThread ?? threadId,
        }),
      });
      if (!response.ok) {
        setError(`BFF error ${response.status}`);
        return;
      }
      const turn = await response.json();
      // Newest first. A new thread replaces the view rather than appending —
      // otherwise two employees' questions interleave under one header.
      const sameThread = turn.thread_id === threadId;
      setThreadId(turn.thread_id);
      setTurns((prev) => {
        const next = sameThread ? [turn, ...prev] : [turn];
        const clipped = next.slice(0, 6);
        setOpenTurn(0);
        return clipped;
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  // Reopen a session thread: render its stored turns newest first, and point the
  // composer at the last question. Nothing is executed — the user decides
  // whether to re-run it.
  async function loadThread(idToLoad) {
    if (busy || !idToLoad) return;
    setError("");
    try {
      const detail = await fetch(`${API}/thread/${idToLoad}`).then((r) => r.json());
      const stored = detail.turns || [];
      setTurns(stored.slice(-6).reverse());
      setOpenTurn(stored.length ? 0 : null);
      setThreadId(idToLoad);
      const last = stored[stored.length - 1];
      if (last) {
        setMessage(last.question || "");
        if (last.employee_id) setEmployeeId(last.employee_id);
      }
    } catch (err) {
      setError(String(err));
    }
  }

  // A thread belongs to one employee: the server records whose data was read for
  // every turn. Changing employee therefore starts a fresh conversation rather
  // than mixing two people's answers under one header.
  function startNewThread() {
    setTurns([]);
    setThreadId(null);
    setOpenTurn(null);
  }

  function switchEmployee(next) {
    setEmployeeId(next);
    if (turns.length) startNewThread();
  }

  const mixedEmployees = new Set(turns.map((t) => t.employee_id)).size > 1;

  return (
    <div style={S.page}>
      <header style={{
        position: "sticky", top: 0, zIndex: 10,
        background: "rgba(238,242,247,.94)", backdropFilter: "blur(10px)",
        paddingTop: 24, paddingBottom: 16, marginBottom: 10,
        borderBottom: "3px solid #cbd5e1",
      }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 900,
                     letterSpacing: "-.025em" }}>
          Quantic HR Agent
        </h1>
        <p style={{ margin: "6px 0 16px", color: "#475569", fontSize: 13.5 }}>
          Agentic RAG over Aurora pgvector, reached through MCP tools.
        </p>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 10,
                      alignItems: "center" }}>
          {DEMOS.map((demo) => (
            <button
              key={demo.label}
              onClick={() => {
                switchEmployee(demo.employee);
                setMessage(demo.message);
              }}
              style={{ ...S.control, cursor: "pointer" }}
            >
              {demo.label}
            </button>
          ))}

          <button onClick={startNewThread} style={{ ...S.control, cursor: "pointer" }}>
            New thread
          </button>

          <select
            value={threadId || ""}
            onChange={(e) => e.target.value && loadThread(e.target.value)}
            style={{ ...S.control, minWidth: 220 }}
          >
            <option value="">{threadId ? `current ${threadId}` : "new thread"}</option>
            {threads
              .filter((t) => t.thread_id !== threadId)
              .map((t) => (
                <option key={t.thread_id} value={t.thread_id}>
                  {t.thread_id} · {t.turns} turn{t.turns === 1 ? "" : "s"} ·{" "}
                  {(t.last_question || "").slice(0, 40)}
                </option>
              ))}
          </select>

          {/* Same tab, so the browser Back button returns here too. */}
          <a
            href="/evaluation"
            style={{ ...S.control, marginLeft: "auto", textDecoration: "none",
                     color: "#1d4ed8", borderColor: "#93b8f7", background: "#e0ecff",
                     fontWeight: 800, fontSize: 12.5, cursor: "pointer" }}
          >
            Evaluation dashboard
          </a>

          <label style={{ fontSize: 13, color: "#334155", fontWeight: 600,
                          display: "flex", alignItems: "center", gap: 7 }}>
            Employee
            <select
              value={employeeId}
              onChange={(e) => switchEmployee(e.target.value)}
              style={{ ...S.control, minWidth: 200 }}
            >
              {employees.length === 0 && (
                <option value={employeeId}>{employeeId}</option>
              )}
              {employees.map((e) => (
                <option key={e.employee_id} value={e.employee_id}>
                  {e.employee_id} — {e.display_name}
                  {e.employment_type !== "FT" ? ` · ${e.employment_type}` : ""}
                </option>
              ))}
            </select>
          </label>

          {employeeError && (
            <span style={{ color: "#b91c1c", fontSize: 12, fontWeight: 700 }}>
              employee list unavailable
            </span>
          )}
        </div>
      </header>

      <div style={{ display: "flex", alignItems: "center", gap: 12,
                    flexWrap: "wrap", marginBottom: 14 }}>
        <span style={{ ...S.label, color: "#64748b" }}>Conversation</span>
        <span style={{ ...S.mono, textTransform: "none", letterSpacing: 0 }}>
          {threadId || "new thread"} · {turns.length} turn{turns.length === 1 ? "" : "s"}
          {turns.length ? ` · prompt ${turns[0].prompt_id}` : ""}
        </span>
        {mixedEmployees && (
          <span style={{ color: "#b45309", fontWeight: 800, fontSize: 11 }}>
            mixed employees — start a new thread
          </span>
        )}
      </div>

      {error && (
        <div style={{ background: "#fee2e2", border: "2px solid #fca5a5",
                      borderRadius: 10, padding: "10px 14px", marginBottom: 16,
                      color: "#7f1d1d", fontSize: 13, fontWeight: 600 }}>
          {error}
        </div>
      )}

      {turns.map((turn, i) => (
        <Turn
          key={turn.prompt_id || i}
          turn={turn}
          expanded={openTurn === i}
          onToggle={() => setOpenTurn(openTurn === i ? null : i)}
        />
      ))}

      <div style={{ position: "fixed", bottom: 0, left: 0, right: 0,
                    background: "rgba(238,242,247,.96)",
                    backdropFilter: "blur(10px)", borderTop: "3px solid #cbd5e1",
                    padding: "14px 24px" }}>
        <div style={{ maxWidth: 1280, margin: "0 auto", display: "flex",
                      gap: 12, alignItems: "flex-end" }}>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={2}
            placeholder="Ask an HR policy or workflow question…"
            style={{ flex: 1, borderRadius: 10, border: "2px solid #94a3b8",
                     padding: "10px 12px", fontSize: 14, fontFamily: "inherit",
                     resize: "vertical" }}
          />
          <button
            onClick={() => ask(message, employeeId)}
            disabled={busy}
            style={{ borderRadius: 10, border: "none", padding: "12px 22px",
                     fontSize: 14, fontWeight: 800, color: "#fff",
                     background: busy ? "#94a3b8" : "#047857",
                     cursor: busy ? "wait" : "pointer" }}
          >
            {busy ? "Working…" : "Ask"}
          </button>
        </div>
      </div>
    </div>
  );
}
