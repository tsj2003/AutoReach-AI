import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";

function mailboxLabel(counts) {
  const entries = Object.entries(counts || {}).sort(([a], [b]) => a.localeCompare(b));
  if (!entries.length) return "No mailboxes";
  return entries.map(([status, count]) => `${count} ${status}`).join(" / ");
}

export default function Operations() {
  const [summary, setSummary] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [readinessLoading, setReadinessLoading] = useState(true);
  const [err, setErr] = useState("");

  function load() {
    setErr("");
    // Render the page as soon as the fast mission-control call returns.
    api
      .get("/api/operations/mission-control")
      .then(setSummary)
      .catch((e) => setErr(e.message));
    // The deep readiness probe (DB + Redis + Celery) can take ~10s; load it
    // independently so it never blocks the rest of the control room.
    setReadinessLoading(true);
    api
      .get("/api/operations/readiness?deep=true")
      .then(setReadiness)
      .catch(() => setReadiness(null))
      .finally(() => setReadinessLoading(false));
  }

  useEffect(load, []);

  if (err) return <div className="error">{err}</div>;
  if (!summary) return <div className="muted">Loading operations...</div>;

  const stats = [
    { label: "Campaigns", value: summary.campaign_count },
    { label: "Blocked Launches", value: summary.blocked_launch_count },
    { label: "Pending Approvals", value: summary.pending_approval_count },
    { label: "Booked Meetings", value: summary.booked_meeting_count },
    { label: "Budget Risks", value: summary.budget_risk_count },
  ];

  return (
    <div>
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="PILOT CONTROL ROOM" />
          </div>
          <h1 style={{ marginTop: 6 }}>Operations</h1>
          <p className="muted">Daily control room for pilot customers and launch safety.</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={load}>Refresh</button>
          <Link className="btn" to="/operations/mailboxes">Mailboxes</Link>
          <Link className="btn" to="/operations/signals">Signal connectors</Link>
          <Link className="gb-dark-btn" to="/operations/onboarding" style={{ position: "relative", textDecoration: "none" }}>
            <CornerBrackets variant="all" size={5} color="#FA651E" offset={-1} />
            Pilot onboarding
          </Link>
        </div>
      </div>

      <div className="stat-grid">
        {stats.map((stat) => (
          <div className="stat-card" key={stat.label} style={{ position: "relative" }}>
            <CornerBrackets variant="all" size={6} color="#0A0A0A" offset={-1} />
            <div className={`stat-value ${stat.label.includes("Risk") || stat.label.includes("Blocked") ? "bad" : ""}`}>
              {stat.value}
            </div>
            <div className="stat-label">{stat.label}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ position: "relative" }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <div className="section-head">
          <div>
            <HeaderTag variant={1} text="MAILBOX STATE" />
            <h3 style={{ marginTop: 8 }}>Mailbox State</h3>
            <p className="muted small">{mailboxLabel(summary.mailbox_counts)}</p>
          </div>
        </div>
      </div>

      <div className="card" style={{ position: "relative" }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <div className="section-head">
          <div>
            <HeaderTag variant={1} text="READINESS" />
            <h3 style={{ marginTop: 8 }}>Production Readiness</h3>
            <p className="muted small">
              {readinessLoading
                ? "Running deep readiness check (database, Redis, worker)…"
                : readiness?.is_production_ready
                ? "Required launch configuration is present."
                : `${readiness?.missing_required?.length || 0} required check(s) failing.`}
            </p>
          </div>
          <GradientPill variant={readinessLoading ? "yellow" : readiness?.is_production_ready ? "mint" : "yellow"}>
            {readinessLoading ? "Checking…" : readiness?.is_production_ready ? "Ready" : "Needs work"}
          </GradientPill>
        </div>
        <div className="readiness-grid">
          {(readiness?.checks || []).map((check) => (
            <div className={`readiness-row status-${check.status.toLowerCase()}`} key={check.key}>
              <span>{check.status}</span>
              <div>
                <strong>{check.label}</strong>
                <p>{check.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ position: "relative" }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <h3>Blocked launches</h3>
        {summary.blocked_launches.length === 0 && (
          <p className="muted">No blocked campaigns right now.</p>
        )}
        {summary.blocked_launches.length > 0 && (
          <table className="data compact-table">
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Failed checks</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {summary.blocked_launches.map((campaign) => (
                <tr key={campaign.campaign_id}>
                  <td>{campaign.customer_name}</td>
                  <td>{campaign.failed_keys.join(", ")}</td>
                  <td><Link to={`/campaigns/${campaign.campaign_id}`}>open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
