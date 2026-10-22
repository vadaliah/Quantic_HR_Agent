import { useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export default function App() {
  const [employeeId, setEmployeeId] = useState("E001");
  const [message, setMessage] = useState("Can I work remotely from another state?");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    const response = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, employee_id: employeeId }),
    });
    if (!response.ok) {
      setError(`BFF error ${response.status}`);
      return;
    }
    setResult(await response.json());
  }

  return (
    <main style={{ fontFamily: "sans-serif", maxWidth: 720, margin: "2rem auto" }}>
      <h1>Quantic HR Agent</h1>
      <p>Local MCP + LangGraph. No AWS resources are used.</p>
      <form onSubmit={onSubmit}>
        <label>
          Employee
          <select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}>
            <option value="E001">E001 Amina Cole (NY, remote-eligible)</option>
            <option value="E002">E002 Ben Ortiz (OH, not remote-eligible)</option>
          </select>
        </label>
        <textarea
          rows={3}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          style={{ width: "100%", marginTop: 12 }}
        />
        <button type="submit">Ask</button>
      </form>
      {error && <p>{error}</p>}
      {result && (
        <section>
          <h2>Answer</h2>
          <pre>{result.answer}</pre>
          <h3>Tool trace</h3>
          <ul>
            {(result.tool_trace || []).map((item, index) => (
              <li key={index}>
                <strong>{item.name}</strong> {JSON.stringify(item.arguments)}
                <div>{item.output_summary}</div>
              </li>
            ))}
          </ul>
          <h3>Citations</h3>
          <ul>
            {(result.citations || []).map((item, index) => (
              <li key={index}>
                {item.title} ({item.document_id}#{item.section_id})
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
