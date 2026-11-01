import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, getToken } from "../api";

const COLORS = [
  "#38bdf8",
  "#a78bfa",
  "#34d399",
  "#f472b6",
  "#fbbf24",
  "#fb7185",
  "#2dd4bf",
  "#818cf8",
  "#c084fc",
  "#4ade80",
  "#f87171",
  "#94a3b8",
];

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
    ? Object.entries(latest.by_category)
        .map(([name, value]) => ({ name, value: Number(value.toFixed(2)) }))
        .filter((d) => d.value > 0)
        .sort((a, b) => b.value - a.value)
    : [];

  const totalSpent = chartData.reduce((s, d) => s + d.value, 0);

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Your spending overview with category breakdown.</p>
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

      {chartData.length === 0 ? (
        <div className="card">
          <p className="muted">Upload a credit card or UPI PDF to see charts.</p>
        </div>
      ) : (
        <div className="charts-grid">
          {/* Pie Chart */}
          <div className="card chart-card">
            <h2>Category split</h2>
            <p className="muted tiny">Total spent this month: ₹{totalSpent.toLocaleString("en-IN")}</p>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={110}
                  innerRadius={55}
                  paddingAngle={2}
                  label={({ name, percent }) =>
                    percent > 0.05 ? `${name} ${(percent * 100).toFixed(0)}%` : ""
                  }
                >
                  {chartData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => `₹${Number(value).toLocaleString("en-IN")}`}
                  contentStyle={{
                    background: "#111",
                    border: "1px solid #333",
                    borderRadius: 8,
                  }}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Bar Chart */}
          <div className="card chart-card">
            <h2>Spend by category</h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                <XAxis type="number" tick={{ fill: "#888", fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={110}
                  tick={{ fill: "#aaa", fontSize: 11 }}
                />
                <Tooltip
                  formatter={(value) => `₹${Number(value).toLocaleString("en-IN")}`}
                  contentStyle={{
                    background: "#111",
                    border: "1px solid #333",
                    borderRadius: 8,
                  }}
                />
                <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                  {chartData.map((_, index) => (
                    <Cell key={`bar-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  );
}
