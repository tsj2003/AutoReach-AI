import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";

// NOTE: This view renders ONLY real tenant-scoped outcomes from
// GET /api/learning/weekly (honest event aggregation) and
// GET /api/analytics/dashboard. There are no hardcoded benchmark
// numbers, no fabricated "signal conversion" rows, and no demo lift
// multipliers. When there is not enough data, we say so plainly.

function confidencePill(confidence) {
  const variant =
    confidence === "high" || confidence === "medium"
      ? "mint"
      : confidence === "low"
      ? "yellow"
      : "peach";
  return <GradientPill variant={variant}>{confidence}</GradientPill>;
}

export default function Analytics() {
  const [weekly, setWeekly] = useState(null);
  const [dash, setDash] = useState(null);
  const [loading, setLoading] = useState(true);
  const [disabled, setDisabled] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.resolve(
      api
        .get("/api/learning/weekly")
        .then((d) => active && setWeekly(d))
        .catch((e) => {
          // 503 => learning measurement feature flag is off
          if (active && String(e?.message || "").includes("503")) setDisabled(true);
          if (active) setWeekly(null);
        }),
    ).finally(() => {
      api
        .get("/api/analytics/dashboard")
        .then((d) => active && setDash(d))
        .catch(() => active && setDash(null))
        .finally(() => active && setLoading(false));
    });
    return () => {
      active = false;
    };
  }, []);

  const totals = dash?.totals || {};

  return (
    <div>
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="WEEKLY LEARNING · REAL OUTCOMES ONLY" />
          </div>
          <h1 style={{ marginTop: 6 }}>Weekly AI Learning</h1>
          <p className="muted">
            Aggregated from your real events via <code>GET /api/learning/weekly</code>. Advisory
            only — recommendations never change prompts, campaigns, or send policy automatically.
          </p>
        </div>
      </div>

      {loading && <div className="muted">Loading…</div>}

      {!loading && disabled && (
        <div className="card" style={{ padding: 24 }}>
          <HeaderTag variant={1} text="LEARNING MEASUREMENT DISABLED" />
          <p className="muted" style={{ marginTop: 10 }}>
            Weekly learning measurement is turned off on this deployment. Set{" "}
            <code>AUTOREACH_LEARNING_ENABLED=1</code> to enable honest outcome aggregation.
          </p>
        </div>
      )}

      {!loading && !disabled && (
        <>
          {/* Real outcome totals for the period */}
          <div className="stat-grid" style={{ marginBottom: 22 }}>
            {[
              { label: "Campaigns Analyzed", value: weekly?.campaigns_analyzed ?? 0 },
              { label: "Replies Classified", value: weekly?.replies_total ?? 0 },
              { label: "Positive Replies", value: weekly?.positive_replies ?? 0 },
              { label: "Meetings Booked", value: weekly?.meetings_booked ?? 0 },
            ].map((c) => (
              <div key={c.label} className="stat-card" style={{ position: "relative" }}>
                <CornerBrackets variant="diagonal" size={6} color="#0A0A0A" offset={-1} />
                <div className="stat-value">{c.value}</div>
                <div className="stat-label">{c.label}</div>
              </div>
            ))}
          </div>

          {/* Honest "not enough data" state */}
          {weekly && !weekly.enough_data && (
            <div className="card" style={{ padding: 24, marginBottom: 22 }}>
              <HeaderTag variant={1} text="NOT ENOUGH DATA YET" />
              <p className="muted" style={{ marginTop: 10 }}>
                We need at least 20 classified replies before reporting reply-rate trends. So far
                this period: <strong>{weekly.replies_total ?? 0}</strong> classified{" "}
                {weekly.replies_total === 1 ? "reply" : "replies"}. Keep sending approved outreach and
                classifying replies — benchmarks appear automatically once there is real signal.
              </p>
            </div>
          )}

          {/* Real insights */}
          <div className="card" style={{ position: "relative", padding: 24, marginBottom: 22 }}>
            <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
            <h3 style={{ marginTop: 0 }}>Insights (from your events)</h3>
            {weekly?.insights?.length ? (
              <table className="data">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Insight</th>
                    <th className="num">Evidence</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {weekly.insights.map((i, idx) => (
                    <tr key={i.category + idx}>
                      <td style={{ fontFamily: "var(--gb-font-mono)", fontWeight: 600 }}>
                        {i.category}
                      </td>
                      <td>{i.message}</td>
                      <td className="num">{i.evidence_count}</td>
                      <td>{confidencePill(i.confidence)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No insights yet for this period.</p>
            )}
          </div>

          {/* Real recommendations (advisory only) */}
          <div className="card" style={{ position: "relative", padding: 24 }}>
            <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
            <h3 style={{ marginTop: 0 }}>Recommendations (advisory only)</h3>
            {weekly?.recommendations?.length ? (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {weekly.recommendations.map((r, idx) => (
                  <li key={r.category + idx} style={{ marginBottom: 8 }}>
                    {r.message} {confidencePill(r.confidence)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No recommendations yet.</p>
            )}
            {weekly?.note && (
              <p className="muted small" style={{ marginTop: 12 }}>
                {weekly.note}
              </p>
            )}
          </div>

          {/* Lifetime ROI proof from real ledger totals */}
          {dash && (
            <p className="muted small" style={{ marginTop: 16 }}>
              Lifetime (all-time): {totals.total_booked ?? 0} booked ·{" "}
              {totals.total_qualified ?? 0} qualified · revenue $
              {(((totals.total_revenue_cents || 0) / 100) || 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
              })}{" "}
              · cost $
              {(((totals.total_cost_cents || 0) / 100) || 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
              })}
            </p>
          )}
        </>
      )}
    </div>
  );
}
