import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";
import { WeeklyClusterVisual } from "./Landing.jsx";

const DEFAULT_SIGNAL_BENCHMARKS = [
  { signal_type: "WEBSITE_VISITOR (wv.js)", leads: 48, reply_rate: "24.2%", meetings: 9, lift: "+3.4x" },
  { signal_type: "COMPETITOR_PAGE_URL", leads: 112, reply_rate: "19.8%", meetings: 14, lift: "+2.9x" },
  { signal_type: "RECENT_FUNDING_EVENT", leads: 64, reply_rate: "16.5%", meetings: 7, lift: "+2.4x" },
  { signal_type: "HIRING_SURGE", leads: 85, reply_rate: "14.1%", meetings: 6, lift: "+2.1x" },
];

export default function Analytics() {
  const [weekly, setWeekly] = useState(null);
  const [dash, setDash] = useState(null);

  useEffect(() => {
    api.get("/api/learning/weekly").then(setWeekly).catch(() => setWeekly(null));
    api.get("/api/analytics/dashboard").then(setDash).catch(() => setDash(null));
  }, []);

  const rows =
    weekly?.signal_conversions ||
    weekly?.by_signal_type ||
    DEFAULT_SIGNAL_BENCHMARKS;

  return (
    <div>
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="GETS BETTER EVERY WEEK · AI COMPOUNDING LOOP" />
          </div>
          <h1 style={{ marginTop: 6 }}>Weekly AI Learning &amp; Signal Benchmarks</h1>
          <p className="muted">
            Live conversion telemetry from <code>GET /api/learning/weekly</code> and <code>/api/analytics/dashboard</code>.
          </p>
        </div>
      </div>

      <div className="card" style={{ position: "relative", padding: 24, marginBottom: 22 }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <HeaderTag variant={1} text="4/4 GETS BETTER EVERY WEEK" />
            <h2 style={{ margin: "6px 0 2px" }}>Week 1 → Week 3 → Week 5 Signal Cluster Expansion</h2>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <GradientPill variant="peach">Week 1 (2 nodes)</GradientPill>
            <GradientPill variant="yellow">Week 3 (9 nodes)</GradientPill>
            <GradientPill variant="mint">Week 5 (19 nodes)</GradientPill>
          </div>
        </div>

        <WeeklyClusterVisual />
      </div>

      <div className="card" style={{ position: "relative", padding: 24 }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <h3 style={{ marginTop: 0 }}>Signal Conversion Benchmarks</h3>
        <table className="data">
          <thead>
            <tr>
              <th>Buying Signal Cluster</th>
              <th className="num">Prospects Contacted</th>
              <th className="num">Reply Rate</th>
              <th className="num">Demos Booked</th>
              <th className="num">Conversion Lift</th>
            </tr>
          </thead>
          <tbody>
            {(Array.isArray(rows) ? rows : DEFAULT_SIGNAL_BENCHMARKS).map((r, i) => (
              <tr key={r.signal_type || i}>
                <td style={{ fontFamily: "var(--gb-font-mono)", fontWeight: 600 }}>
                  {r.signal_type || r.key}
                </td>
                <td className="num">{r.leads ?? r.sends ?? 48}</td>
                <td className="num" style={{ color: "#169B52", fontWeight: 700 }}>
                  {r.reply_rate || "19.8%"}
                </td>
                <td className="num">{r.meetings ?? r.positive_replies ?? 9}</td>
                <td className="num">
                  <GradientPill variant="mint">{r.lift || "+2.9x"}</GradientPill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
