import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, getToken } from "../api";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.dashboard().then(setData).catch((err) => setError(err.message));
  }, []);

  async function downloadExcel() {
    const response = await fetch(api.exportUrl, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "spendsense-report.xlsx";
    link.click();
    URL.revokeObjectURL(url);
  }

  const latest = data?.latest;
  const chartData = latest
    ? Object.entries(latest.by_category).map(([name, value]) => ({ name, value: Number(value.toFixed(2)) }))
    : [];

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Monthly spend by category, with Excel export.</p>
        </div>
        <button onClick={downloadExcel}>Export Excel</button>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="stats">
        <article className="card">
          <div className="muted">Transactions</div>
          <strong>{data?.total_transactions ?? 0}</strong>
        </article>
        <article className="card">
          <div className="muted">This month spent</div>
          <strong>₹{(latest?.total_debit ?? 0).toLocaleString("en-IN")}</strong>
        </article>
        <article className="card">
          <div className="muted">This month credited</div>
          <strong>₹{(latest?.total_credit ?? 0).toLocaleString("en-IN")}</strong>
        </article>
        <article className="card">
          <div className="muted">Latest month</div>
          <strong>{latest?.month || "—"}</strong>
        </article>
      </div>
      <div className="card chart-card">
        <h2>Category split</h2>
        {chartData.length === 0 ? (
          <p className="muted">Upload a credit card or UPI PDF to see charts.</p>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3344" />
              <XAxis dataKey="name" tick={{ fill: "#9aa7bd", fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={80} />
              <YAxis tick={{ fill: "#9aa7bd" }} />
              <Tooltip />
              <Bar dataKey="value" fill="#7dd3fc" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
