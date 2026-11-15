import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
  CoralExpandButton,
} from "../components/gojiberry/index.js";

function money(cents) {
  return `$${((cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

export default function Campaigns() {
  const navigate = useNavigate();
  const [campaigns, setCampaigns] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    customer_name: "",
    offer: "",
    icp_description: "",
    client_cure: "",
    allowed_signal_types: "funding_round, hiring_surge, job_change, tech_adoption",
    booking_url: "",
    monthly_meeting_target: 20,
    price_per_outcome_cents: 50000,
    monthly_budget_cents: 200000,
    hitl_threshold: 50,
    personalize_enabled: true,
    subject_template: "",
    body_template: "",
    agent_mode: "copilot",
    include_linkedin_sequence: false,
  });
  const [extractedIcp, setExtractedIcp] = useState(null);
  const [err, setErr] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [autofilling, setAutofilling] = useState(false);
  const [autofillNote, setAutofillNote] = useState("");
  const [usage, setUsage] = useState(null);

  async function autofillFromWebsite() {
    if (!websiteUrl.trim()) return;
    setAutofilling(true);
    setAutofillNote("");
    setErr("");
    try {
      const d = await api.post("/api/onboarding/analyze-website", { url: websiteUrl.trim() });
      setForm((f) => ({
        ...f,
        customer_name: d.company_name || f.customer_name,
        offer: d.offer || f.offer,
        icp_description: d.icp_description || f.icp_description,
        client_cure: d.client_cure || f.client_cure,
        allowed_signal_types: (d.suggested_signal_types || []).join(", ") || f.allowed_signal_types,
        subject_template: d.subject_template || f.subject_template,
        body_template: d.body_template || f.body_template,
      }));
      const rec = Array.isArray(d.recommended_signals) ? d.recommended_signals : [];
      const jobTitles = [
        ...(Array.isArray(d.job_titles) ? d.job_titles : Array.isArray(d.target_job_titles) ? d.target_job_titles : []),
        ...(Array.isArray(d.adjacent_job_titles) ? d.adjacent_job_titles : Array.isArray(d.adjacentJobTitles) ? d.adjacentJobTitles : []),
      ].filter((title, index, all) => title && all.indexOf(title) === index);
      setExtractedIcp({
        target_job_titles: jobTitles,
        target_industries: Array.isArray(d.target_industries) ? d.target_industries : [],
        target_company_sizes: Array.isArray(d.target_company_sizes) ? d.target_company_sizes : [],
        target_locations: Array.isArray(d.target_locations) ? d.target_locations : [],
        search_keywords: Array.isArray(d.search_keywords) ? d.search_keywords : [],
        signals: rec.map((s) => s.type || s.label).filter(Boolean),
        status: d.status || "",
        need_more_input: d.need_more_input || "",
      });
      setAutofillNote(
        d.status === "low_evidence"
          ? (d.need_more_input || "Not enough page evidence — add a marketing URL or product blurb.")
          : d.source === "llm"
            ? "Drafted from your website — review extracted ICP & signals, then launch."
            : "Website analyzed from on-page evidence — review ICP & signals, then launch."
      );
    } catch (e) {
      setErr(e.message);
    } finally {
      setAutofilling(false);
    }
  }

  function load() {
    api.get("/api/campaigns").then(setCampaigns).catch((e) => setErr(e.message));
    api.get("/api/billing/usage").then(setUsage).catch(() => setUsage(null));
  }
  useEffect(load, []);

  const atCampaignCap =
    usage && usage.usage && usage.usage.campaigns >= usage.usage.campaigns_limit;

  async function create(e) {
    e.preventDefault();
    setErr("");
    if (atCampaignCap) {
      setErr(
        `Plan '${usage.plan}' allows ${usage.usage.campaigns_limit} campaign(s). Upgrade or archive one first.`
      );
      return;
    }
    try {
      const payload = {
        ...form,
        hitl_threshold: form.agent_mode === "copilot" ? 30 : 85,
        allowed_signal_types: form.allowed_signal_types
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
        target_job_titles: extractedIcp?.target_job_titles || [],
        target_industries: extractedIcp?.target_industries || [],
        target_company_sizes: extractedIcp?.target_company_sizes || [],
        target_locations: extractedIcp?.target_locations || [],
        search_keywords: extractedIcp?.search_keywords || [],
        source_website: websiteUrl.trim() || undefined,
        auto_discover_people: true,
        discovery_cap: 20,
        reply_mode: form.agent_mode === "full_auto" ? "auto" : "hitl",
        ...(form.include_linkedin_sequence
          ? {
              sequence: [
                { kind: "VISIT_PROFILE", channel: "linkedin", wait_days: 0, label: "Visit LinkedIn Profile" },
                { kind: "LIKE_POSTS", channel: "linkedin", wait_days: 0, label: "Like Recent Posts" },
                { kind: "LINKEDIN_CONNECT", channel: "linkedin", wait_days: 1, label: "Connection Request" },
                { kind: "EMAIL", channel: "email", wait_days: 2, label: "Email" },
                { kind: "LINKEDIN_MESSAGE", channel: "linkedin", wait_days: 3, label: "LinkedIn Message" },
              ],
              skip_invitation_after_days: 7,
            }
          : {}),
      };
      const created = await api.post("/api/campaigns", payload);
      setShowForm(false);
      setForm({ ...form, customer_name: "", offer: "", icp_description: "", client_cure: "" });
      if (created?.id) {
        navigate(`/campaigns/${created.id}/contacts`);
        return;
      }
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  function upd(k, isNum) {
    return (e) => setForm({ ...form, [k]: isNum ? Number(e.target.value) : e.target.value });
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <HeaderTag variant={3} text="AI OUTBOUND AGENTS" />
          <h1 style={{ marginTop: 6 }}>Campaigns</h1>
        </div>
        <CoralExpandButton
          size="sm"
          onClick={() => {
            if (!showForm && atCampaignCap) {
              setErr(
                `Plan '${usage.plan}' allows ${usage.usage.campaigns_limit} campaign(s). Upgrade on Billing or archive one first.`
              );
              return;
            }
            setErr("");
            setShowForm(!showForm);
          }}
        >
          {showForm ? "Cancel" : "+ New campaign"}
        </CoralExpandButton>
      </div>
      {err && <div className="error">{err}</div>}
      {atCampaignCap && !showForm && (
        <div className="notice" style={{ marginBottom: 12 }}>
          Campaign limit reached ({usage.usage.campaigns}/{usage.usage.campaigns_limit} on{" "}
          {usage.plan}).{" "}
          <Link to="/billing">View plan</Link>
        </div>
      )}

      {showForm && !atCampaignCap && (
        <form className="card form" onSubmit={create} style={{ position: "relative" }}>
          <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
          <div className="autofill" style={{ background: "#F5F4F3", padding: 16, border: "var(--gb-hairline)", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <PulseDot size={10} />
              <strong style={{ fontSize: 13.5 }}>⚡ 3-Minute Setup — Paste your website</strong>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                placeholder="https://yourcompany.com"
                style={{ flex: 1, marginTop: 0, background: "#FFF" }}
              />
              <button type="button" className="gb-dark-btn" disabled={autofilling} onClick={autofillFromWebsite}>
                {autofilling ? "Reading your site…" : "Auto-fill from website"}
              </button>
            </div>
            {autofillNote && <p className="notice">{autofillNote}</p>}
            {extractedIcp && (
              <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
                {extractedIcp.target_job_titles.map((t) => (
                  <GradientPill key={t} variant="yellow">{t}</GradientPill>
                ))}
                {extractedIcp.target_industries.map((i) => (
                  <GradientPill key={i} variant="peach">{i}</GradientPill>
                ))}
                {extractedIcp.signals.map((s) => (
                  <GradientPill key={s} variant="mint">{s}</GradientPill>
                ))}
              </div>
            )}
          </div>

          <div className="row2">
            <label>
              Customer / Agent name
              <input value={form.customer_name} onChange={upd("customer_name")} required />
            </label>
            <label>
              Autonomy Mode
              <select
                value={form.agent_mode}
                onChange={(e) => setForm({ ...form, agent_mode: e.target.value })}
                style={{ display: "block", width: "100%", marginTop: 4, padding: "8px 10px", border: "var(--gb-hairline)", borderRadius: 6, background: "#F5F4F3" }}
              >
                <option value="copilot">🛡️ AI Copilot (Approve before send)</option>
                <option value="full_auto">⚡ Full Auto (24/7 Autonomous)</option>
              </select>
            </label>
          </div>

          <label>Offer<textarea rows="2" value={form.offer} onChange={upd("offer")} required /></label>
          <label>ICP description<textarea rows="2" value={form.icp_description} onChange={upd("icp_description")} required /></label>
          <label>Client cure<textarea rows="2" value={form.client_cure} onChange={upd("client_cure")} placeholder="The specific pain this offer solves right now" /></label>
          <label>Allowed signal types<input value={form.allowed_signal_types} onChange={upd("allowed_signal_types")} placeholder="funding_round, hiring_surge, SEARCH_KEYWORD, WEBSITE_VISITOR" /></label>
          <label>First email subject<input value={form.subject_template} onChange={upd("subject_template")} placeholder="Quick question for {first_name}" /></label>
          <label>First email body<textarea rows="3" value={form.body_template} onChange={upd("body_template")} placeholder="Optional — from website autofill" /></label>
          <label>Booking URL<input value={form.booking_url} onChange={upd("booking_url")} placeholder="https://cal.com/you" /></label>
          <div className="row3">
            <label>Meeting target<input type="number" value={form.monthly_meeting_target} onChange={upd("monthly_meeting_target", true)} /></label>
            <label>Price/meeting (cents)<input type="number" value={form.price_per_outcome_cents} onChange={upd("price_per_outcome_cents", true)} /></label>
            <label>Monthly budget (cents)<input type="number" value={form.monthly_budget_cents} onChange={upd("monthly_budget_cents", true)} /></label>
          </div>
          <div className="row3">
            <label>HITL threshold<input type="number" value={form.hitl_threshold} onChange={upd("hitl_threshold", true)} /></label>
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.personalize_enabled}
              onChange={(e) => setForm({ ...form, personalize_enabled: e.target.checked })}
            />
            Enable AI personalization (name, company, ICP fact)
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.include_linkedin_sequence}
              onChange={(e) => setForm({ ...form, include_linkedin_sequence: e.target.checked })}
            />
            Include LinkedIn sequence (visit → like → connect → email → DM). Requires a LinkedIn seat.
          </label>
          <button className="btn primary">Create</button>
        </form>
      )}

      <table className="data">
        <thead>
          <tr>
            <th>Name</th>
            <th>Mode</th>
            <th>Channels</th>
            <th>Status</th>
            <th className="num">Qualified</th>
            <th className="num">Revenue</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c) => {
            const channels = Array.isArray(c.channels) && c.channels.length
              ? c.channels
              : ["Email"];
            const mode = c.execution_mode || "AI Copilot";
            return (
            <tr key={c.id}>
              <td>
                <Link to={`/campaigns/${c.id}`} style={{ fontWeight: 700, color: "#0A0A0A" }}>
                  {c.customer_name}
                </Link>
              </td>
              <td>
                <GradientPill variant="yellow">{mode}</GradientPill>
              </td>
              <td>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  {channels.map((ch) => (
                    <GradientPill key={ch} variant={ch === "LinkedIn" ? "peach" : "mint"}>
                      {ch}
                    </GradientPill>
                  ))}
                </div>
              </td>
              <td><span className={`pill pill-${c.status}`}>{c.status}</span></td>
              <td className="num">{c.pnl?.qualified_count ?? 0}</td>
              <td className="num">{money(c.pnl?.revenue_cents)}</td>
              <td><Link to={`/campaigns/${c.id}`}>open →</Link></td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
