import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, getToken } from "../api";
import "./Dashboard.css";

const CATEGORY_COLORS = [
  "#6f8497",
  "#718a7d",
  "#8a7d70",
  "#6c7487",
  "#7b6f7b",
  "#607a78",
  "#8a6f60",
  "#667789",
  "#7b8272",
  "#756d68",
];

function monthLabel(value) {
  if (!value) return "—";
  const [year, month] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", { month: "short", year: "numeric" }).format(
    new Date(year, month - 1, 1)
  );
}

function money(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(amount);
}

function renderPiePercentLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  if (percent < 0.08) return null;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.53;
  const radians = (-midAngle * Math.PI) / 180;
  const x = cx + radius * Math.cos(radians);
  const y = cy + radius * Math.sin(radians);

  return (
    <text
      x={x}
      y={y}
      fill="#f4f6f8"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={11}
      fontWeight={700}
    >
      {(percent * 100).toFixed(0)}%
    </text>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [error, setError] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [exportPeriod, setExportPeriod] = useState("selected_month");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .dashboard(selectedMonth || undefined)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError("");
        if (!selectedMonth && result?.selected?.month) {
          setSelectedMonth(result.selected.month);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedMonth]);

  const selected = data?.selected;

  const categoryData = useMemo(() => {
    if (!selected) return [];
    return Object.entries(selected.by_category || {})
      .map(([name, value]) => ({ name, value: Number(Number(value).toFixed(2)) }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value);
  }, [selected]);

  const trendData = useMemo(
    () =>
      (data?.months || []).map((item) => ({
        month: monthLabel(item.month),
        rawMonth: item.month,
        spent: Number(item.total_debit || 0),
      })),
    [data]
  );

  const totalSpent = categoryData.reduce((sum, item) => sum + item.value, 0);

  async function downloadExcel() {
    const params = { period: exportPeriod };
    if (exportPeriod === "selected_month") {
      params.selected_month = selectedMonth;
    } else if (exportPeriod === "custom") {
      if (!customStart || !customEnd) {
        setError("Choose both a start date and an end date for the custom report.");
        return;
      }
      params.start_date = customStart;
      params.end_date = customEnd;
    }

    setExporting(true);
    setError("");
    try {
      const response = await fetch(api.exportUrl(params), {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!response.ok) {
        let message = "Could not export report.";
        try {
          const body = await response.json();
          message = body.detail || message;
        } catch {
          // Keep the friendly fallback message.
        }
        throw new Error(message);
      }

      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
      const filename = filenameMatch?.[1] || "spendsense-report.xlsx";

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
      setExportOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="dashboard-page">
      <div className="page-head dashboard-head">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Review one month in detail while keeping the full spending trend in view.</p>
        </div>

        <div className="dashboard-actions">
          <label className="month-control">
            <span>View month</span>
            <select value={selectedMonth} onChange={(event) => setSelectedMonth(event.target.value)}>
              {(data?.available_months || [])
                .slice()
                .reverse()
                .map((month) => (
                  <option key={month} value={month}>
                    {monthLabel(month)}
                  </option>
                ))}
            </select>
          </label>
          <button className="export-button" type="button" onClick={() => setExportOpen((open) => !open)}>
            Export report
          </button>
        </div>
      </div>

      {exportOpen && (
        <div className="card export-panel">
          <div>
            <strong>Excel report period</strong>
            <p className="muted tiny">Categories, merchants and totals will only use this selected period.</p>
          </div>
          <select value={exportPeriod} onChange={(event) => setExportPeriod(event.target.value)}>
            <option value="selected_month">Selected dashboard month ({monthLabel(selectedMonth)})</option>
            <option value="current_month">Current month</option>
            <option value="previous_month">Previous month</option>
            <option value="last_6_months">Last 6 months</option>
            <option value="last_12_months">Last 12 months</option>
            <option value="custom">Custom date range</option>
          </select>

          {exportPeriod === "custom" && (
            <div className="custom-date-grid">
              <label>
                <span>From</span>
                <input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} />
              </label>
              <label>
                <span>To</span>
                <input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} />
              </label>
            </div>
          )}

          <button className="download-button" type="button" onClick={downloadExcel} disabled={exporting}>
            {exporting ? "Preparing report…" : "Download Excel"}
          </button>
        </div>
      )}

      {error && <div className="error dashboard-error">{error}</div>}

      <div className="stats">
        <article className="card">
          <div className="muted">Transactions</div>
          <strong>{selected?.transaction_count ?? 0}</strong>
          <span className="muted tiny">{monthLabel(selected?.month)}</span>
        </article>
        <article className="card">
          <div className="muted">Spent</div>
          <strong>{money(selected?.total_debit)}</strong>
          <span className="muted tiny">Transfers excluded</span>
        </article>
        <article className="card">
          <div className="muted">Credited</div>
          <strong>{money(selected?.total_credit)}</strong>
          <span className="muted tiny">Transfers excluded</span>
        </article>
        <article className="card">
          <div className="muted">Net transfers</div>
          <strong>{money(selected?.net_transfers)}</strong>
          <span className="muted tiny">Sent − received</span>
        </article>
      </div>

      {trendData.length > 0 && (
        <div className="card chart-card chart-card-wide">
          <div className="chart-heading">
            <div>
              <h2>Monthly spend trend</h2>
              <p className="muted tiny">All imported months. Transfers are excluded.</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trendData} margin={{ top: 12, right: 20, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 6" stroke="#28303a" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: "#9aa4b2", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: "#9aa4b2", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => `₹${Math.round(value / 1000)}k`}
              />
              <Tooltip
                formatter={(value) => [money(value), "Spent"]}
                contentStyle={{
                  background: "#161b22",
                  border: "1px solid #303844",
                  borderRadius: 10,
                }}
              />
              <Line
                type="monotone"
                dataKey="spent"
                name="Spent"
                stroke="#71869a"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "#71869a" }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {categoryData.length === 0 ? (
        <div className="card">
          <p className="muted">No spending transactions for {monthLabel(selectedMonth)}.</p>
        </div>
      ) : (
        <div className="charts-grid dashboard-charts">
          <div className="card chart-card">
            <div className="chart-heading">
              <div>
                <h2>Category split</h2>
                <p className="muted tiny">{monthLabel(selected?.month)} · {money(totalSpent)} spent</p>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                <Pie
                  data={categoryData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="44%"
                  outerRadius={105}
                  innerRadius={66}
                  paddingAngle={1}
                  labelLine={false}
                  label={renderPiePercentLabel}
                >
                  {categoryData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value, name) => [money(value), name]}
                  contentStyle={{
                    background: "#161b22",
                    border: "1px solid #303844",
                    borderRadius: 10,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: "#a7b0bb", paddingTop: 8 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="card chart-card">
            <div className="chart-heading">
              <div>
                <h2>Spend by category</h2>
                <p className="muted tiny">Largest categories for {monthLabel(selected?.month)}</p>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={310}>
              <BarChart data={categoryData} layout="vertical" margin={{ top: 4, right: 28, bottom: 4, left: 12 }}>
                <CartesianGrid strokeDasharray="3 6" stroke="#28303a" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: "#9aa4b2", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value) => `₹${Math.round(value / 1000)}k`}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={128}
                  tick={{ fill: "#aeb6c1", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  formatter={(value) => money(value)}
                  contentStyle={{
                    background: "#161b22",
                    border: "1px solid #303844",
                    borderRadius: 10,
                  }}
                />
                <Bar dataKey="value" fill="#71869a" radius={[0, 5, 5, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  );
}
