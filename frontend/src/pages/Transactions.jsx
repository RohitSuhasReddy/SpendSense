import { useEffect, useState } from "react";
import { api } from "../api";

function formatBreakdown(classified = {}) {
  return Object.entries(classified)
    .filter(([, count]) => count)
    .map(([method, count]) => `${method}: ${count}`)
    .join(" · ");
}

export default function Transactions() {
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [classifier, setClassifier] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [month, setMonth] = useState("");
  const [reclassifying, setReclassifying] = useState(false);

  async function load() {
    try {
      const [txns, cats, classifierStatus] = await Promise.all([
        api.transactions({ month }),
        api.categories(),
        api.classifierStatus(),
      ]);
      setRows(txns);
      setCategories(cats);
      setClassifier(classifierStatus);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [month]);

  async function changeCategory(id, category) {
    try {
      const updated = await api.updateCategory(id, category);
      setRows((current) =>
        current
          .map((row) =>
            row.merchant === updated.merchant ? { ...row, category: updated.category } : row
          )
          .map((row) => (row.id === updated.id ? updated : row))
      );
    } catch (err) {
      setError(err.message);
    }
  }

  async function reclassifyAll() {
    setReclassifying(true);
    setError("");
    setNotice("");
    try {
      const result = await api.reclassify();
      const breakdown = formatBreakdown(result.classified);
      const provider = result.llm_provider ? ` · ${result.llm_provider}` : " · LLM disabled";
      setNotice(
        `Reclassified ${result.updated} transaction${result.updated === 1 ? "" : "s"}${breakdown ? ` · ${breakdown}` : ""}${provider}`
      );
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setReclassifying(false);
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Review & correct</h1>
          <p className="muted">Corrections are saved to merchant mappings and reused next time.</p>
          {classifier && (
            <p className="muted tiny">
              {classifier.llm_enabled
                ? `LLM fallback active: ${classifier.llm_provider}`
                : "LLM fallback is disabled. Add GEMINI_API_KEY or OPENAI_API_KEY to the backend environment."}
            </p>
          )}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button type="button" onClick={reclassifyAll} disabled={reclassifying}>
            {reclassifying ? "Reclassifying…" : "Reclassify"}
          </button>
          <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {notice && <div className="success" style={{ marginBottom: 14 }}>{notice}</div>}

      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Merchant</th>
              <th>Amount</th>
              <th>Source</th>
              <th>How</th>
              <th>Category</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.txn_date.slice(0, 10)}</td>
                <td>
                  <div>{row.merchant}</div>
                  <div className="muted tiny">{row.cleaned_description}</div>
                </td>
                <td className={row.direction === "credit" ? "credit" : ""}>
                  {row.direction === "credit" ? "+" : "-"}₹{row.amount.toLocaleString("en-IN")}
                  {row.is_recurring ? <span className="pill">recurring</span> : null}
                </td>
                <td>{row.source}</td>
                <td>{row.classification_method}</td>
                <td>
                  <select value={row.category} onChange={(e) => changeCategory(row.id, e.target.value)}>
                    {categories.map((cat) => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">No transactions yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
