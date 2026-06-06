import { useEffect, useState } from "react";
import { api } from "../api/client.js";

function money(cents) {
  return `$${((cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get("/api/analytics/dashboard").then(setData).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="error">{err}</div>;
  if (!data) return <div className="muted">Loading…</div>;

  const t = data.totals;
  const cards = [
    { label: "Campaigns", value: t.campaigns },
    { label: "Active", value: t.active_campaigns },
    { label: "Booked", value: t.total_booked },
    { label: "Qualified", value: t.total_qualified },
    { label: "Revenue", value: money(t.total_revenue_cents) },
    { label: "Cost", value: money(t.total_cost_cents) },
    { label: "Margin", value: money(t.total_margin_cents) },
  ];

  return (
    <div>
      <h1>Dashboard</h1>
      <div className="stat-grid">
        {cards.map((c) => (
          <div key={c.label} className="stat-card">
            <div className="stat-value">{c.value}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
      </div>

      <h2>Campaigns</h2>
      <table className="data">
        <thead>
          <tr><th>Name</th><th>Status</th><th className="num">Qualified</th><th className="num">Revenue</th></tr>
        </thead>
        <tbody>
          {data.campaigns.map((c) => (
            <tr key={c.id}>
              <td><a href={`/app/campaigns/${c.id}`}>{c.name}</a></td>
              <td><span className={`pill pill-${c.status}`}>{c.status}</span></td>
              <td className="num">{c.qualified}</td>
              <td className="num">{money(c.revenue_cents)}</td>
            </tr>
          ))}
          {data.campaigns.length === 0 && (
            <tr><td colSpan="4" className="muted">No campaigns yet. Create one from the Campaigns tab.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
