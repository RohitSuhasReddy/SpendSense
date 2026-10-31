import { useEffect, useState } from "react";
import { api } from "../api";

export default function Transactions() {
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [error, setError] = useState("");
  const [month, setMonth] = useState("");

  async function load() {
    try {
      const [txns, cats] = await Promise.all([api.transactions({ month }), api.categories()]);
      setRows(txns);
      setCategories(cats);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [month]);

  async function changeCategory(id, category) {
    const updated = await api.updateCategory(id, category);
    setRows((current) =>
      current.map((row) => (row.merchant === updated.merchant ? { ...row, category: updated.category } : row))
        .map((row) => (row.id === updated.id ? updated : row))
    );
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Review & correct</h1>
          <p className="muted">Corrections are saved to merchant mappings and reused next time.</p>
        </div>
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
      </div>
      {error && <div className="error">{error}</div>}
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
