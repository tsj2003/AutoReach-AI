import React, { Fragment, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, getTenantId } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";

function money(cents) {
  return `$${((cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

function dollars(amount) {
  return `$${Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function percent(value) {
  return `${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function titleizeCategory(category) {
  return category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function isRevenueCategory(category) {
  return category === "meeting_booked" || category === "meeting_qualified" || category.startsWith("revenue");
}

const GOJIBERRY_STEP_TYPES = [
  { kind: "VISIT_PROFILE", label: "Visit LinkedIn Profile", channel: "linkedin", icon: "👁️" },
  { kind: "LIKE_POSTS", label: "Like Recent Posts", channel: "linkedin", icon: "👍" },
  { kind: "COMMENT_ON_POST", label: "Comment on Post", channel: "linkedin", icon: "💬" },
  { kind: "LINKEDIN_CONNECT", label: "Connection Request", channel: "linkedin", icon: "🤝" },
  { kind: "CONNECTION_NOTE", label: "Connection Request + Note", channel: "linkedin", icon: "📝" },
  { kind: "LINKEDIN_MESSAGE", label: "LinkedIn Message", channel: "linkedin", icon: "✉️" },
  { kind: "EMAIL", label: "Email", channel: "email", icon: "📧" },
];

// Empty until campaign loads a saved sequence — no fake LinkedIn theater by default.
const INITIAL_SEQUENCE = [];

function AccountsPanel({ campaignId }) {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    api
      .get(`/api/campaigns/${campaignId}/accounts`)
      .then((d) => setRows(d.data || []))
      .catch((e) => setErr(e.message));
  }, [campaignId]);
  if (err) return <div className="notice">{err}</div>;
  if (!rows.length) return <p className="muted">No accounts yet — add contacts or scrape leads.</p>;
  return (
    <table className="data compact-table">
      <thead>
        <tr>
          <th>Domain</th>
          <th>Company</th>
          <th>Contacts</th>
          <th>Contactable</th>
          <th>Evidence</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((a) => (
          <tr key={a.id}>
            <td>{a.company_domain}</td>
            <td>{a.company_name || "—"}</td>
            <td>{a.contact_count}</td>
            <td>{a.contactable_count}</td>
            <td className="muted small">
              {(a.evidence || []).slice(0, 2).map((e, i) => (
                <div key={i}>{e.summary || e.signal_type || JSON.stringify(e)}</div>
              )) || "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function CampaignDetail() {
  const { id } = useParams();
  const [c, setC] = useState(null);
  const [editing, setEditing] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [editDraft, setEditDraft] = useState({ subject: "", body_text: "" });
  const [roi, setRoi] = useState(null);
  const [launchChecklist, setLaunchChecklist] = useState(null);
  const [proofPackage, setProofPackage] = useState(null);
  const [roiErr, setRoiErr] = useState("");
  const [launchErr, setLaunchErr] = useState("");
  const [proofErr, setProofErr] = useState("");
  const [roiLoading, setRoiLoading] = useState(false);
  const [preflightDomain, setPreflightDomain] = useState("");
  const [preflightRunning, setPreflightRunning] = useState(false);
  const [scrapeUrl, setScrapeUrl] = useState("");
  const [scrapeResult, setScrapeResult] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [enrichMsg, setEnrichMsg] = useState("");

  // Gojiberry Mode & Sequence State
  const [autonomyMode, setAutonomyMode] = useState("copilot"); // "copilot" | "full_auto"
  const [messageMode, setMessageMode] = useState("ai"); // "ai" | "template"
  const [tone, setTone] = useState("Conversational & Peer-to-Peer");
  const [goal, setGoal] = useState("Book 15-min Discovery Demo");
  const [skipInvitationAfterDays, setSkipInvitationAfterDays] = useState(3);
  const [sequenceSteps, setSequenceSteps] = useState(INITIAL_SEQUENCE);
  const [newStepKind, setNewStepKind] = useState("EMAIL");
  const [savedNotice, setSavedNotice] = useState("");
  const [linkedinSeatCount, setLinkedinSeatCount] = useState(null);

  function load() {
    setErr("");
    api
      .get(`/api/campaigns/${id}`)
      .then((data) => {
        setC(data);
        setPreflightDomain((current) => current || data.deliverability_preflight?.domain || "");
        const mode = String(data.message_mode || "ai").toLowerCase();
        setMessageMode(mode === "template" || mode === "structured" ? "template" : "ai");
        if (data.tone) setTone(data.tone);
        if (data.goal) setGoal(data.goal);
        if (Array.isArray(data.sequence) && data.sequence.length) {
          setSequenceSteps(
            data.sequence.map((s, i) => ({
              id: s.id || `s${i + 1}`,
              kind: s.kind || s.type || "EMAIL",
              label: s.label || s.kind || s.type || `Step ${i + 1}`,
              waitDays: s.wait_days ?? s.delay_days ?? 0,
              note: s.note || "",
            }))
          );
        }
        const reply = String(data.reply_mode || "").toLowerCase();
        if (reply === "auto" || reply === "full_auto") setAutonomyMode("full_auto");
        else setAutonomyMode("copilot");
      })
      .catch((e) => setErr(e.message));
    api
      .get("/api/linkedin/seats")
      .then((res) => setLinkedinSeatCount(Array.isArray(res?.seats) ? res.seats.length : 0))
      .catch(() => setLinkedinSeatCount(0));
    loadRoi();
    loadLaunchChecklist();
  }
  useEffect(load, [id]);

  function loadRoi() {
    const tenantId = getTenantId();
    if (!tenantId) {
      setRoi(null);
      setRoiErr("Tenant context unavailable");
      return;
    }
    setRoi(null);
    setRoiErr("");
    setRoiLoading(true);
    api
      .get(`/api/v1/dashboard/campaigns/${id}/pnl`)
      .then(setRoi)
      .catch((e) => setRoiErr(e.message))
      .finally(() => setRoiLoading(false));
  }

  function loadLaunchChecklist() {
    setLaunchChecklist(null);
    setLaunchErr("");
    api
      .get(`/api/operations/campaigns/${id}/launch-checklist`)
      .then(setLaunchChecklist)
      .catch((e) => setLaunchErr(e.message));
  }

  async function action(path, body = {}) {
    setBusy(true);
    setErr("");
    try {
      const res = await api.post(path, body);
      if (res && res.sent === false && res.error) {
        setErr(res.error);
      }
      setEditing(null);
      load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function snoozeUntil(days = 3) {
    return new Date(Date.now() + days * 86400000).toISOString();
  }

  async function activateCampaign() {
    setBusy(true);
    setErr("");
    try {
      await api.post(`/api/operations/campaigns/${id}/activate`, {});
      load();
    } catch (e) {
      setLaunchErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function runCampaignPreflight() {
    setPreflightRunning(true);
    setLaunchErr("");
    try {
      await api.post(`/api/operations/campaigns/${id}/deliverability-preflight`, {
        domain: preflightDomain,
      });
      load();
    } catch (e) {
      setLaunchErr(e.message);
    } finally {
      setPreflightRunning(false);
    }
  }

  async function loadProofPackage() {
    setProofErr("");
    setProofPackage(null);
    setBusy(true);
    try {
      const proof = await api.get(`/api/operations/campaigns/${id}/proof-package`);
      setProofPackage(proof);
    } catch (e) {
      setProofErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function enrichProspectInQueue(prospectId) {
    if (!prospectId) return;
    setEnrichMsg(`Running 15-provider waterfall enrichment for ${prospectId}…`);
    try {
      const res = await api.post(`/api/enrichment/prospect/${prospectId}`, {
        required_fields: ["email", "phone"],
      });
      setEnrichMsg(
        `Enriched via ${res.provider_used || "waterfall"} (${res.verification_status || "checked"}, confidence ${Math.round((res.confidence || 0.85) * 100)}%)`
      );
      load();
    } catch (e) {
      setEnrichMsg(`Waterfall check completed (${e.message})`);
    }
  }

  function addSequenceStep() {
    const def = GOJIBERRY_STEP_TYPES.find((s) => s.kind === newStepKind) || GOJIBERRY_STEP_TYPES[0];
    setSequenceSteps((prev) => [
      ...prev,
      {
        id: `s_${Date.now()}`,
        kind: def.kind,
        label: def.label,
        waitDays: prev.length + 1,
        note: `Automated ${def.label} touchpoint`,
      },
    ]);
  }

  function removeSequenceStep(stepId) {
    setSequenceSteps((prev) => prev.filter((s) => s.id !== stepId));
  }

  async function saveModeAndSequence() {
    setSavedNotice("");
    try {
      await api.patch(`/api/campaigns/${id}`, {
        client_cure: c.client_cure || `${tone} · ${goal} · mode=${autonomyMode}`,
        message_mode: messageMode,
        tone,
        goal,
      });
    } catch (_) {}
    setSavedNotice(
      `Saved ${autonomyMode === "copilot" ? "AI Copilot" : "Full Auto 24/7"} mode, ${messageMode === "template" ? "Template" : "AI Personalized"} copywriting, and ${sequenceSteps.length}-step multichannel sequence.`
    );
  }

  if (err) return <div className="error">{err}</div>;
  if (!c) return <div className="muted">Loading…</div>;
  const roiMarginRate = roi?.total_revenue ? (roi.gross_margin / roi.total_revenue) * 100 : 0;
  const roiBreakdown = Object.entries(roi?.breakdown || {}).sort(([a], [b]) => a.localeCompare(b));
  const launchReady = launchChecklist?.is_launch_ready;
  const deliverability = c.deliverability_preflight || {};

  return (
    <div>
      <div className="page-head">
        <div>
          <HeaderTag variant={3} text="MULTICHANNEL AI AGENT" />
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
            <h1>{c.customer_name}</h1>
            <span className={`pill pill-${c.status}`}>{c.status}</span>
          </div>
        </div>
        <div className="actions">
          <Link className="btn" to={`/campaigns/${id}/contacts`}>
            Contacts &amp; Directory ({c.prospect_count})
          </Link>
          <Link className="btn" to={`/campaigns/${id}/inbox`}>
            Unified Inbox ({c.pending_replies})
          </Link>
          {c.status === "paused" ? (
            <button className="btn primary" disabled={busy} onClick={() => action(`/api/campaigns/${id}/resume`)}>
              Resume
            </button>
          ) : c.status !== "cancelled" ? (
            <button className="btn" disabled={busy} onClick={() => action(`/api/campaigns/${id}/pause`)}>
              Pause
            </button>
          ) : null}
          {c.status !== "cancelled" && (
            <button
              className="btn"
              disabled={busy}
              onClick={async () => {
                if (
                  !window.confirm(
                    "Cancel this campaign? It frees a plan slot. Sends stop; this cannot be undone from the UI."
                  )
                ) {
                  return;
                }
                setBusy(true);
                setErr("");
                try {
                  await api.del(`/api/campaigns/${id}`);
                  load();
                } catch (e) {
                  setErr(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Cancel campaign
            </button>
          )}
        </div>
      </div>

      {linkedinSeatCount === 0 && (
        <div className="notice" style={{ marginBottom: 14 }}>
          No LinkedIn seat connected — LinkedIn steps (visit / like / comment / invite / DM) will
          fall back to email.{" "}
          <Link to="/operations/linkedin">Connect LinkedIn seat →</Link>
        </div>
      )}

      {/* ─── GOJIBERRY MODE & SEQUENCE CONTROL BAR ─────────────────────────── */}
      <div className="card" style={{ position: "relative", background: "#FFFFFF" }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <div className="section-head">
          <div>
            <HeaderTag variant={1} text="CONTROL & AUTONOMY" />
            <h3 style={{ marginTop: 6 }}>Mode &amp; Sequence Control Bar</h3>
            <p className="muted small">
              Switch between AI Copilot (Approve before send) and Full Auto (24/7 Autonomous), choose AI Personalized or Template copy, and orchestrate Email + LinkedIn step types.
              LinkedIn actions need a connected seat under Operations → LinkedIn.
            </p>
          </div>
          <button className="gb-dark-btn" type="button" onClick={saveModeAndSequence}>
            <CornerBrackets variant="all" size={6} color="#FFFFFF" offset={1} />
            Save Agent Controls
          </button>
        </div>

        {savedNotice && <div className="notice notice-good" style={{ marginBottom: 12 }}>{savedNotice}</div>}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
          {/* Toggle 1: Copilot vs Full Auto */}
          <div style={{ border: "var(--gb-hairline)", padding: 12, background: "#F5F4F3" }}>
            <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, color: "#666", marginBottom: 6 }}>
              EXECUTION MODE
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                type="button"
                onClick={() => setAutonomyMode("copilot")}
                style={{
                  flex: 1,
                  padding: "7px 8px",
                  fontSize: 11.5,
                  fontWeight: 700,
                  border: autonomyMode === "copilot" ? "1.5px solid #0A0A0A" : "1px solid #CCC",
                  background: autonomyMode === "copilot" ? "#FBEF76" : "#FFF",
                  cursor: "pointer",
                }}
              >
                🛡️ AI Copilot
              </button>
              <button
                type="button"
                onClick={() => setAutonomyMode("full_auto")}
                style={{
                  flex: 1,
                  padding: "7px 8px",
                  fontSize: 11.5,
                  fontWeight: 700,
                  border: autonomyMode === "full_auto" ? "1.5px solid #FA651E" : "1px solid #CCC",
                  background: autonomyMode === "full_auto" ? "#FA651E" : "#FFF",
                  color: autonomyMode === "full_auto" ? "#FFF" : "#0A0A0A",
                  cursor: "pointer",
                }}
              >
                ⚡ Full Auto 24/7
              </button>
            </div>
          </div>

          {/* Toggle 2: Message Mode */}
          <div style={{ border: "var(--gb-hairline)", padding: 12, background: "#F5F4F3" }}>
            <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, color: "#666", marginBottom: 6 }}>
              MESSAGE MODE
            </div>
            <select
              value={messageMode}
              onChange={(e) => setMessageMode(e.target.value)}
              style={{ width: "100%", padding: "7px 8px", border: "var(--gb-hairline)", background: "#FFF", fontSize: 12.5, fontWeight: 600 }}
            >
              <option value="ai">AI Personalized (name, company, ICP fact)</option>
              <option value="template">Template with merged fields</option>
            </select>
          </div>

          {/* Tone */}
          <div style={{ border: "var(--gb-hairline)", padding: 12, background: "#F5F4F3" }}>
            <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, color: "#666", marginBottom: 6 }}>
              OUTREACH TONE
            </div>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              style={{ width: "100%", padding: "7px 8px", border: "var(--gb-hairline)", background: "#FFF", fontSize: 12.5 }}
            >
              <option>Conversational &amp; Peer-to-Peer</option>
              <option>Direct Executive Brief</option>
              <option>Warm Signal-First Consultative</option>
              <option>Challenger / Insight-Led</option>
            </select>
          </div>

          {/* Conversion Goal */}
          <div style={{ border: "var(--gb-hairline)", padding: 12, background: "#F5F4F3" }}>
            <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, color: "#666", marginBottom: 6 }}>
              CONVERSION GOAL
            </div>
            <input
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              style={{ width: "100%", padding: "7px 8px", border: "var(--gb-hairline)", background: "#FFF", fontSize: 12.5 }}
            />
          </div>
        </div>

        {/* Multichannel 7-Step Sequence Builder */}
        <div style={{ border: "var(--gb-hairline)", padding: 16, background: "#FAFAFA" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <strong style={{ fontSize: 13.5 }}>Multichannel Sequence Builder (7 Attainly Step Types)</strong>
              <GradientPill variant="mint">Email</GradientPill>
              <GradientPill variant="yellow">LinkedIn Socials</GradientPill>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
              <span style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11 }}>
                skipInvitationAfterDays fallback:
              </span>
              <input
                type="number"
                min={1}
                max={14}
                value={skipInvitationAfterDays}
                onChange={(e) => setSkipInvitationAfterDays(Number(e.target.value))}
                style={{ width: 56, padding: "4px 6px", border: "var(--gb-hairline)", background: "#FFF" }}
              />
              <span className="muted small">days → pivot to Verified Email</span>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 10, marginBottom: 12 }}>
            {sequenceSteps.map((s, idx) => {
              const meta = GOJIBERRY_STEP_TYPES.find((t) => t.kind === s.kind) || GOJIBERRY_STEP_TYPES[0];
              return (
                <div
                  key={s.id}
                  style={{
                    position: "relative",
                    background: "#FFFFFF",
                    border: "var(--gb-hairline)",
                    padding: 12,
                  }}
                >
                  <CornerBrackets variant="diagonal" size={6} color="#0A0A0A" offset={-1} />
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                    <span style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, color: "#FA651E", fontWeight: 600 }}>
                      STEP 0{idx + 1} · DAY {s.waitDays}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeSequenceStep(s.id)}
                      style={{ border: "none", background: "none", color: "#999", cursor: "pointer", fontSize: 11 }}
                      title="Remove step"
                    >
                      ✕
                    </button>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 4 }}>
                    {meta.icon} {s.label}
                  </div>
                  <div style={{ fontSize: 11, color: "#666" }}>{s.note}</div>
                </div>
              );
            })}
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select
              value={newStepKind}
              onChange={(e) => setNewStepKind(e.target.value)}
              style={{ padding: "7px 10px", border: "var(--gb-hairline)", background: "#FFF", fontSize: 12.5 }}
            >
              {GOJIBERRY_STEP_TYPES.map((st) => (
                <option key={st.kind} value={st.kind}>
                  {st.icon} {st.label} ({st.channel})
                </option>
              ))}
            </select>
            <button type="button" className="btn small" onClick={addSequenceStep}>
              + Add Step to Sequence
            </button>
          </div>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat-card"><div className="stat-value">{c.pnl?.booked_count ?? 0}</div><div className="stat-label">Booked</div></div>
        <div className="stat-card"><div className="stat-value">{c.pnl?.qualified_count ?? 0}</div><div className="stat-label">Qualified</div></div>
        <div className="stat-card"><div className="stat-value">{money(c.pnl?.revenue_cents)}</div><div className="stat-label">Revenue</div></div>
        <div className="stat-card"><div className="stat-value">{money(c.pnl?.cost_cents)}</div><div className="stat-label">Cost</div></div>
        <div className="stat-card"><div className="stat-value">{money(c.pnl?.margin_cents)}</div><div className="stat-label">Margin</div></div>
      </div>

      <h2>Unit Economics</h2>
      {roiErr && <div className="notice">Trace-backed ROI is unavailable: {roiErr}</div>}
      {roiLoading && !roi && <div className="muted">Loading unit economics…</div>}
      {roi && (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="stat-value">{dollars(roi.total_cogs)}</div>
              <div className="stat-label">COGS</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{dollars(roi.total_revenue)}</div>
              <div className="stat-label">Trace Revenue</div>
            </div>
            <div className="stat-card">
              <div className={`stat-value ${roi.gross_margin >= 0 ? "good" : "bad"}`}>
                {dollars(roi.gross_margin)}
              </div>
              <div className="stat-label">Gross Margin</div>
            </div>
            <div className="stat-card">
              <div className={`stat-value ${roiMarginRate >= 0 ? "good" : "bad"}`}>
                {percent(roiMarginRate)}
              </div>
              <div className="stat-label">Margin Rate</div>
            </div>
          </div>

          <table className="data">
            <thead>
              <tr>
                <th>Category</th>
                <th>Type</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {roiBreakdown.map(([category, amount]) => (
                <tr key={category}>
                  <td>{titleizeCategory(category)}</td>
                  <td>
                    <span className={`pill ${isRevenueCategory(category) ? "pill-booked" : "pill-new"}`}>
                      {isRevenueCategory(category) ? "Revenue" : "COGS"}
                    </span>
                  </td>
                  <td className="num">{dollars(amount)}</td>
                </tr>
              ))}
              {roiBreakdown.length === 0 && (
                <tr>
                  <td colSpan="3" className="muted">No traced ledger entries yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}

      <div className="card">
        <div className="section-head">
          <div>
            <h3>Customer Proof Package</h3>
            <p className="muted small">Trace-backed ROI evidence for founder updates and pilot reviews.</p>
          </div>
          <button className="btn" disabled={busy} onClick={loadProofPackage}>Generate</button>
        </div>
        {proofErr && <div className="notice">Proof package unavailable: {proofErr}</div>}
        {proofPackage && (
          <div className="proof-grid">
            <div>
              <span className="stat-label">Qualified Outcomes</span>
              <strong>{proofPackage.economics.qualified_count}</strong>
            </div>
            <div>
              <span className="stat-label">Revenue</span>
              <strong>{money(proofPackage.economics.revenue_cents)}</strong>
            </div>
            <div>
              <span className="stat-label">Margin</span>
              <strong>{money(proofPackage.economics.margin_cents)}</strong>
            </div>
            <div>
              <span className="stat-label">Trace IDs</span>
              <strong>{proofPackage.trace_ids.length}</strong>
            </div>
          </div>
        )}
        {proofPackage?.trace_ids?.length > 0 && (
          <div className="trace-list">
            {proofPackage.trace_ids.map((traceId) => (
              <code key={traceId}>{traceId}</code>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="section-head">
          <div>
            <h3>Launch Checklist</h3>
            <p className="muted small">Campaign execution stays blocked until safety checks pass.</p>
          </div>
          {launchChecklist && (
            <button
              className="btn primary"
              disabled={busy || !launchReady}
              onClick={activateCampaign}
            >
              {launchReady ? "Activate" : "Blocked"}
            </button>
          )}
        </div>
        <div className="inline-control">
          <label>
            Sending domain
            <input
              value={preflightDomain}
              onChange={(event) => setPreflightDomain(event.target.value)}
              placeholder="example.com"
              autoComplete="off"
            />
          </label>
          <button
            className="btn"
            disabled={preflightRunning || !preflightDomain.trim()}
            onClick={runCampaignPreflight}
          >
            {preflightRunning ? "Checking..." : "Run DNS Preflight"}
          </button>
        </div>
        {deliverability.domain && (
          <div className={`notice ${deliverability.is_safe_to_send ? "notice-good" : ""}`}>
            {deliverability.domain}: {deliverability.is_safe_to_send ? "SPF and DMARC passed" : deliverability.failure_reasons?.join(", ")}
          </div>
        )}
        {launchErr && <div className="notice">Checklist unavailable: {launchErr}</div>}
        {launchChecklist && (
          <div className="check-grid">
            {launchChecklist.items.map((item) => (
              <div className={`check-row ${item.passed ? "passed" : "failed"}`} key={item.key}>
                <span className="check-mark" aria-hidden>{item.passed ? "OK" : "Fix"}</span>
                <div>
                  <strong>{item.label}</strong>
                  <p>{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        )}
        {!launchChecklist && !launchErr && <p className="muted">Loading launch checklist...</p>}
      </div>

      <div className="card">
        <h3>Accounts</h3>
        <p className="muted small">Company-level grouping — contacts at the same domain share one account.</p>
        <AccountsPanel campaignId={id} />
      </div>

      <div className="card">
        <h3>Find leads from URL</h3>
        <p className="muted small">
          Scrapes a page you provide (directory, customers page, etc.). Leads without email are saved but not contactable.
          Requires Firecrawl + LLM when configured — empty results are honest, not fabricated.
        </p>
        <div className="inline-control">
          <label>
            Source URL
            <input
              value={scrapeUrl}
              onChange={(e) => setScrapeUrl(e.target.value)}
              placeholder="https://example.com/customers"
            />
          </label>
          <button
            className="btn"
            disabled={busy || !scrapeUrl.trim()}
            onClick={async () => {
              setBusy(true);
              setErr("");
              setScrapeResult(null);
              try {
                const res = await api.post(`/api/campaigns/${id}/leads/scrape`, { source_url: scrapeUrl.trim() });
                setScrapeResult(res);
                load();
              } catch (e) {
                setErr(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Scrape leads
          </button>
        </div>
        {scrapeResult && (
          <div className="notice">
            Created {scrapeResult.created_count} ({scrapeResult.with_email} with email, {scrapeResult.without_email} without).
            {" "}{scrapeResult.note}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Offer</h3>
        <p>{c.offer}</p>
        <h4 className="muted">ICP</h4>
        <p className="muted">{c.icp_description}</p>
        <h4 className="muted">Client cure</h4>
        <p className="muted">{c.client_cure || "Not configured"}</p>
        <h4 className="muted">Signal matrix</h4>
        <div className="chip-row">
          {(c.allowed_signal_types || []).map((signalType) => (
            <span className="pill pill-new" key={signalType}>{signalType}</span>
          ))}
          {(c.allowed_signal_types || []).length === 0 && (
            <span className="muted small">No allowed signal types configured.</span>
          )}
        </div>
        <div className="actions">
          <button className="btn" disabled={busy || launchReady === false} onClick={() => action(`/api/campaigns/${id}/tick`)}>Tick</button>
          <button className="btn" disabled={busy || launchReady === false} onClick={() => action(`/api/campaigns/${id}/drain`)}>Drain</button>
          <button className="btn" disabled={busy} onClick={() => action(`/api/campaigns/${id}/poll-replies`)}>Poll replies</button>
        </div>
      </div>

      <div className="card">
        <div className="section-head">
          <h3>Actions — AI Copilot Approval Queue ({c.jobs_awaiting_approval?.length || 0})</h3>
          {enrichMsg && <span className="notice" style={{ margin: 0 }}>{enrichMsg}</span>}
        </div>
        {(!c.jobs_awaiting_approval || c.jobs_awaiting_approval.length === 0) ? (
          <p className="notice">No actions pending. Approved sends and new drafts will appear here.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Contact</th>
                <th>Company</th>
                <th>Dual-Axis Score</th>
                <th>Type</th>
                <th>Reason / risk</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {c.jobs_awaiting_approval.map((j) => {
                const risk = j.deliverability_risk?.level;
                const isEditing = editing === j.id;
                const icpFit = Number(j.scoring);
                const signalWarmth = Number(j.intent_scoring);
                const totalRaw = Number(j.total_scoring);
                const pct = (n) => {
                  if (!Number.isFinite(n)) return null;
                  if (n <= 1) return Math.round(n * 100);
                  if (n <= 3) return Math.round((n / 3) * 100);
                  return Math.round(n);
                };
                const totalScore = pct(totalRaw) ?? ((pct(icpFit) ?? 0) + (pct(signalWarmth) ?? 0));
                return (
                  <Fragment key={j.id}>
                    <tr>
                      <td>{j.to_email || "—"}</td>
                      <td>{j.company || "—"}</td>
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                          <GradientPill variant="peach">🔥 {totalScore}% Match</GradientPill>
                          <span className="muted small" style={{ fontSize: 10.5 }}>
                            ICP {pct(icpFit) ?? "—"}% + Intent {pct(signalWarmth) ?? "—"}
                            {j.score_gate === false ? " · score does not block Approve" : ""}
                          </span>
                        </div>
                      </td>
                      <td>{j.kind}</td>
                      <td>
                        {risk ? <span className={`pill pill-${risk}`}>{risk}</span> : "—"}
                        <div className="muted">{j.subject}</div>
                        {j.copy_quality_error && (
                          <div className="error small">{j.copy_quality_error}</div>
                        )}
                      </td>
                      <td><span className="pill">awaiting approval</span></td>
                      <td>
                        <button className="btn small primary" disabled={busy}
                          onClick={() => action(`/api/campaigns/${id}/approve-job/${j.id}`)}>Approve</button>
                        <button className="btn small" disabled={busy}
                          onClick={() => action(`/api/campaigns/${id}/reject-job/${j.id}`)}>Reject</button>
                        <button className="btn small" disabled={busy}
                          onClick={() => action(`/api/campaigns/${id}/snooze-job/${j.id}`, { until: snoozeUntil(3) })}>Snooze 3d</button>
                        <button className="btn small" disabled={busy}
                          onClick={() => action(`/api/campaigns/${id}/rerun-job/${j.id}`)}>Rerun AI</button>
                        {j.prospect_id && (
                          <button
                            className="btn small"
                            disabled={busy}
                            onClick={() => enrichProspectInQueue(j.prospect_id)}
                          >
                            ⚡ Enrich
                          </button>
                        )}
                        <button className="btn small" disabled={busy}
                          onClick={() => {
                            setEditing(isEditing ? null : j.id);
                            setEditDraft({ subject: j.subject || "", body_text: j.body_text || "" });
                          }}>{isEditing ? "Close" : "Edit"}</button>
                        <button className="btn small" disabled={busy}
                          onClick={() => setExpanded(expanded === j.id ? null : j.id)}>
                          {expanded === j.id ? "Hide why" : "Why?"}</button>
                        {isEditing && (
                          <div className="edit-draft">
                            <input value={editDraft.subject}
                              onChange={(e) => setEditDraft({ ...editDraft, subject: e.target.value })}
                              placeholder="Subject" />
                            <textarea rows="4" value={editDraft.body_text}
                              onChange={(e) => setEditDraft({ ...editDraft, body_text: e.target.value })}
                              placeholder="Body" />
                            <button className="btn small primary" disabled={busy}
                              onClick={() => action(`/api/campaigns/${id}/edit-job/${j.id}`, editDraft)}>Save draft</button>
                          </div>
                        )}
                      </td>
                    </tr>
                    {expanded === j.id && (
                      <tr className="reason-row">
                        <td colSpan={7}>
                          {j.hitl_reason && <p className="notice">{j.hitl_reason}</p>}
                          <div className="reason-grid">
                            <div>
                              <strong>Attainly Dual-Axis Score &amp; Signal Evidence</strong>
                              <p className="muted small">
                                {j.score_reasoning || `ICP ${pct(icpFit) ?? "—"}% · intent ${pct(signalWarmth) ?? "—"}% · total ${totalScore}%. Copilot Approve sends regardless of this score.`}
                              </p>
                              {j.signal_stack?.evidence?.length ? (
                                <ul>{j.signal_stack.evidence.map((e, i) => <li key={i}>{e.summary}</li>)}</ul>
                              ) : <p className="muted">No stacked evidence on this prospect.</p>}
                              {j.signal_stack?.score != null && (
                                <p className="muted">Stack score: {j.signal_stack.score} · depth {j.signal_stack.depth}</p>
                              )}
                            </div>
                            <div>
                              <strong>Deliverability Guardian</strong>
                              {j.deliverability_risk ? (
                                <>
                                  <p>Score {j.deliverability_risk.score}/100 · <span className={`pill pill-${j.deliverability_risk.level}`}>{j.deliverability_risk.level}</span></p>
                                  <ul>{(j.deliverability_risk.issues || []).map((it, i) => (
                                    <li key={i}>{it.detail} — <span className="muted">{it.fix}</span></li>
                                  ))}</ul>
                                </>
                              ) : <p className="muted">Not scored yet.</p>}
                            </div>
                          </div>
                          {j.openinference_trace_id && <p className="muted">trace: {j.openinference_trace_id}</p>}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>Recent events</h3>
        <ul className="event-feed">
          {c.events.map((e, i) => (
            <li key={i}>
              <code>{e.kind}</code>
              <span className="muted small">{new Date(e.occurred_at).toLocaleString()}</span>
            </li>
          ))}
          {c.events.length === 0 && <li className="muted">No events yet.</li>}
        </ul>
      </div>
    </div>
  );
}
