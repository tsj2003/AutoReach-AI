import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
  CoralExpandButton,
} from "./gojiberry/index.js";

const SIGNAL_CATALOG = [
  { key: "SEARCH_KEYWORD", label: "LinkedIn Keyword Engagement", pill: "peach" },
  { key: "RECENT_ACTIVITY", label: "Top 5% active profiles in your ICP", pill: "mint" },
  { key: "RECENTLY_CHANGED_JOB", label: "Recent job changes (< 90 days)", pill: "yellow" },
  { key: "RECENT_FUNDING_EVENT", label: "Companies that recently raised funds", pill: "peach" },
  { key: "HIRING", label: "Companies hiring right now", pill: "yellow" },
  { key: "TECHNOLOGY", label: "Tech Stack Match", pill: "mint" },
  { key: "COMPETITOR_PAGE_URL", label: "Competitor Post Likers/Commenters", pill: "yellow" },
];

const DEFAULT_SEQUENCE = [
  { step: 1, kind: "visitProfile", label: "Day 0 · Visit LinkedIn Profile", delay: "Day 0" },
  { step: 2, kind: "likePosts", label: "Day 1 · Like Recent LinkedIn Post", delay: "Day 1" },
  { step: 3, kind: "invitationNote", label: "Day 1 · Send Connection Request with Signal Note", delay: "Day 1" },
  { step: 4, kind: "message", label: "Day 3 · Signal-First LinkedIn DM", delay: "Day 3" },
  { step: 5, kind: "email", label: "Day 4 · Personalized Cold Email Fallback", delay: "Day 4" },
];

export default function OnboardingWizard({ onComplete, onSkip }) {
  const initialWebsite = (() => {
    try {
      const params = new URLSearchParams(window.location.search);
      return (
        params.get("onboarding_website") ||
        sessionStorage.getItem("onboarding_website") ||
        localStorage.getItem("onboarding_website") ||
        ""
      );
    } catch (_) {
      return "";
    }
  })();

  const [step, setStep] = useState(initialWebsite ? 1 : 0);
  const [websiteUrl, setWebsiteUrl] = useState(initialWebsite || "https://");
  const [analyzing, setAnalyzing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const [productBlurb, setProductBlurb] = useState("");
  const [draft, setDraft] = useState({
    company_name: "",
    summary: "",
    offer: "",
    icp_description: "",
    client_cure: "",
    status: "",
    need_more_input: "",
    target_job_titles: [],
    target_industries: [],
    target_company_sizes: [],
    target_locations: [],
    selected_signals: [],
    search_keywords: [],
    recommended_signals: [],
    competitors: [],
    product_type: "",
    sequence: DEFAULT_SEQUENCE,
    agent_mode: "copilot", // "copilot" | "full_auto"
    subject_template: "quick question, {first_name}",
    body_template: "",
  });
  const [newJobTitle, setNewJobTitle] = useState("");

  useEffect(() => {
    if (initialWebsite) {
      analyzeSite(initialWebsite);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function analyzeSite(urlToRead) {
    const target = (urlToRead || websiteUrl || "").trim();
    if (!target || target === "https://") {
      setErr("Please enter your company website URL.");
      return;
    }
    setErr("");
    setAnalyzing(true);
    try {
      const res = await api.post("/api/onboarding/analyze-website", {
        url: target,
        product_blurb: productBlurb.trim(),
      });
      const titles = [
        ...(Array.isArray(res.job_titles)
          ? res.job_titles
          : Array.isArray(res.target_job_titles)
            ? res.target_job_titles
            : []),
        ...(Array.isArray(res.adjacent_job_titles)
          ? res.adjacent_job_titles
          : Array.isArray(res.adjacentJobTitles)
            ? res.adjacentJobTitles
            : []),
      ].filter((title, index, all) => title && all.indexOf(title) === index);
      const industries = Array.isArray(res.industries)
        ? res.industries
        : Array.isArray(res.target_industries)
          ? res.target_industries
          : [];
      const sizes = Array.isArray(res.company_sizes)
        ? res.company_sizes
        : Array.isArray(res.target_company_sizes)
          ? res.target_company_sizes
          : [];
      const locations = Array.isArray(res.countries)
        ? res.countries
        : Array.isArray(res.target_locations)
          ? res.target_locations
          : [];
      const keywords = Array.isArray(res.search_keywords) ? res.search_keywords : [];
      const recommended = Array.isArray(res.recommended_signals) ? res.recommended_signals : [];
      const eventDefaults = Array.isArray(res.event_signal_defaults) ? res.event_signal_defaults : [];
      const competitors = Array.isArray(res.ignored_companies)
        ? res.ignored_companies
        : Array.isArray(res.ignoredCompanies)
          ? res.ignoredCompanies
          : Array.isArray(res.competitors)
            ? res.competitors
            : [];
      const seq = Array.isArray(res.multichannel_sequence) && res.multichannel_sequence.length
        ? res.multichannel_sequence.map((s, i) => ({
            step: s.step || i + 1,
            kind: s.type || s.kind || `step-${i + 1}`,
            label: s.label || `${s.type || "step"}`,
            delay: s.delay_days != null ? `Day ${s.delay_days}` : "",
          }))
        : DEFAULT_SEQUENCE;
      const selected = [
        ...recommended.map((s) => String(s.type || s.key || "").toUpperCase()),
        ...eventDefaults
          .filter((s) => s.enabled)
          .map((s) => String(s.type || "").toUpperCase()),
      ].filter((v, i, arr) => v && arr.indexOf(v) === i);

      setDraft((prev) => ({
        ...prev,
        company_name: res.companyName || res.company_name || prev.company_name,
        summary: res.description || res.summary || "",
        offer: res.offer || res.description || "",
        icp_description: res.icp_description || "",
        client_cure: res.client_cure || "",
        status: res.status || "",
        need_more_input: res.need_more_input || "",
        product_type: res.product_type || "",
        target_job_titles: titles,
        target_industries: industries,
        target_company_sizes: sizes,
        target_locations: locations,
        search_keywords: keywords,
        recommended_signals: recommended,
        competitors,
        sequence: seq,
        selected_signals: selected,
        subject_template: res.subject_template || prev.subject_template,
        body_template: res.body_template || "",
      }));
      setStep(1);
    } catch (e) {
      setErr(e.message || "Could not analyze website");
      setStep(1);
    } finally {
      setAnalyzing(false);
    }
  }

  function toggleSignal(sigKey) {
    setDraft((prev) => {
      const exists = prev.selected_signals.includes(sigKey);
      return {
        ...prev,
        selected_signals: exists
          ? prev.selected_signals.filter((k) => k !== sigKey)
          : [...prev.selected_signals, sigKey],
      };
    });
  }

  async function launchFullCycleAgent() {
    setErr("");
    setBusy(true);
    try {
      const created = await api.post("/api/campaigns", {
        customer_name: `${draft.company_name || "Attainly"} AI Agent`,
        offer: draft.offer || draft.summary || "",
        icp_description: draft.icp_description,
        client_cure: draft.client_cure,
        allowed_signal_types: draft.selected_signals.map((s) => s.toLowerCase()),
        monthly_meeting_target: 20,
        hitl_threshold: draft.agent_mode === "copilot" ? 30 : 85,
        personalize_enabled: true,
        subject_template: draft.subject_template,
        body_template: draft.body_template,
        target_job_titles: draft.target_job_titles,
        target_industries: draft.target_industries,
        target_company_sizes: draft.target_company_sizes,
        target_locations: draft.target_locations,
        search_keywords: draft.search_keywords,
        source_website: websiteUrl,
        sequence: draft.sequence || DEFAULT_SEQUENCE,
        signal_variables: (draft.search_keywords || []).slice(0, 10).map((k) => ({
          type: "SEARCH_KEYWORD",
          value: `"${String(k).replace(/^"|"$/g, "")}"`,
        })),
        reply_mode: draft.agent_mode === "copilot" ? "hitl" : "auto",
        min_lead_score: 0.6,
        auto_discover_people: true,
        discovery_cap: 20,
      });
      try {
        sessionStorage.removeItem("onboarding_website");
        localStorage.removeItem("onboarding_website");
      } catch (_) {}
      onComplete?.(created);
    } catch (e) {
      setErr(e.message || "Could not launch agent");
      setBusy(false);
    }
  }

  return (
    <div className="ob-overlay">
      <motion.div
        className="ob-modal"
        style={{
          position: "relative",
          borderRadius: 4,
          border: "var(--gb-hairline)",
          width: 680,
          maxWidth: "96vw",
          padding: "32px 34px",
        }}
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
      >
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <HeaderTag variant={1} text={`0${step + 1}/02 · 3-MINUTE SETUP`} />
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} />
            <span style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, color: "#666" }}>
              Website → ICP → Signals → Multichannel Agent
            </span>
          </div>
        </div>

        {err && <div className="error">{err}</div>}

        <AnimatePresence mode="wait">
          {step === 0 && (
            <motion.div
              key="step0"
              initial={{ opacity: 0, x: 14 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -14 }}
            >
              <h2 style={{ fontFamily: "var(--gb-font-sans)", fontSize: 28, fontWeight: 600, margin: "0 0 8px", letterSpacing: "-0.025em" }}>
                Enter your website. <span style={{ color: "#D86B23" }}>Your agent takes it from there.</span>
              </h2>
              <p style={{ color: "#666", fontSize: 14, margin: "0 0 22px" }}>
                Attainly reads your site and extracts your value proposition, Ideal Customer Profile, buying signals, and multichannel sequence in seconds.
              </p>

              <div className="gb-url-bar" style={{ maxWidth: "100%", margin: "0 0 18px" }}>
                <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
                <input
                  className="gb-url-input"
                  value={websiteUrl}
                  onChange={(e) => setWebsiteUrl(e.target.value)}
                  placeholder="https://yourcompany.com"
                  autoFocus
                />
                <button
                  type="button"
                  className="gb-dark-btn"
                  disabled={analyzing}
                  onClick={() => analyzeSite(websiteUrl)}
                >
                  {analyzing ? "Reading website…" : "Analyze website →"}
                </button>
              </div>
              <label className="auth-label" style={{ fontSize: 12, display: "block", marginBottom: 16 }}>
                Optional product blurb (used if the URL is a login screen)
                <textarea
                  rows={2}
                  value={productBlurb}
                  onChange={(e) => setProductBlurb(e.target.value)}
                  placeholder="One sentence: who you sell to and what the product does"
                  style={{ marginTop: 4, width: "100%", padding: "7px 10px", fontSize: 13 }}
                />
              </label>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 18 }}>
                <span style={{ fontSize: 12, color: "#888", fontFamily: "var(--gb-font-mono)" }}>Try sample:</span>
                {["https://stripe.com", "https://linear.app", "https://supabase.com"].map((u) => (
                  <button
                    key={u}
                    type="button"
                    className="gb-light-btn"
                    style={{ padding: "4px 10px", fontSize: 11.5 }}
                    onClick={() => {
                      setWebsiteUrl(u);
                      analyzeSite(u);
                    }}
                  >
                    {u.replace("https://", "")}
                  </button>
                ))}
              </div>

              <button className="ob-skip" onClick={onSkip}>
                Skip for now — explore cockpit
              </button>
            </motion.div>
          )}

          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: 14 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -14 }}
            >
              <h2 style={{ fontFamily: "var(--gb-font-sans)", fontSize: 24, fontWeight: 600, margin: "0 0 6px" }}>
                {analyzing ? "Analyzing your website…" : `AI Agent Blueprint for ${draft.company_name || "Your Company"}`}
              </h2>
              <p style={{ color: "#666", fontSize: 13, margin: "0 0 16px" }}>
                Review your extracted ICP, buying signals, and multichannel sequence before launching.
              </p>

              {draft.need_more_input && (
                <div style={{ background: "#FFF6E8", border: "1px solid #E8C48A", padding: 12, marginBottom: 14, fontSize: 13 }}>
                  {draft.need_more_input}
                  <textarea
                    rows={2}
                    value={productBlurb}
                    onChange={(e) => setProductBlurb(e.target.value)}
                    placeholder="e.g. Billing and invoicing software for retail shops in India"
                    style={{ marginTop: 8, width: "100%", padding: "7px 10px", fontSize: 13 }}
                  />
                  <button
                    type="button"
                    className="gb-light-btn"
                    style={{ marginTop: 8 }}
                    disabled={analyzing}
                    onClick={() => analyzeSite(websiteUrl)}
                  >
                    {analyzing ? "Re-reading…" : "Re-analyze with blurb"}
                  </button>
                </div>
              )}

              {/* Extracted ICP Tags */}
              <div style={{ background: "#F5F4F3", border: "var(--gb-hairline)", padding: 14, marginBottom: 14, position: "relative" }}>
                <CornerBrackets variant="diagonal" size={7} color="#0A0A0A" offset={-1} />
                <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, fontWeight: 600, marginBottom: 8, color: "#D86B23" }}>
                  EXTRACTED IDEAL CUSTOMER PROFILE (ICP)
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                  {draft.target_job_titles.length === 0 && (
                    <span style={{ fontSize: 12, color: "#888" }}>
                      {draft.product_type === "consumer_marketplace"
                        ? "Consumer/marketplace page — no business buyer titles inferred. Add the role you sell to."
                        : draft.product_type === "app_login"
                          ? "Login wall — titles left empty (same as Gojiberry’s Cloudflare empty form)."
                          : "No buyer titles named on the page. Role types are inferred from “for …” copy when present; add them if still empty."}
                    </span>
                  )}
                  {draft.target_job_titles.map((t) => (
                    <GradientPill key={t} variant="yellow">{t}</GradientPill>
                  ))}
                  {draft.target_industries.map((ind) => (
                    <GradientPill key={ind} variant="peach">{ind}</GradientPill>
                  ))}
                  {draft.target_company_sizes.map((sz) => (
                    <GradientPill key={sz} variant="mint">{sz} emp</GradientPill>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                  <input
                    value={newJobTitle}
                    onChange={(e) => setNewJobTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const next = newJobTitle.trim();
                        if (!next || draft.target_job_titles.includes(next)) return;
                        setDraft({ ...draft, target_job_titles: [...draft.target_job_titles, next] });
                        setNewJobTitle("");
                      }
                    }}
                    placeholder="Add a buyer role type and press Enter"
                    style={{ flex: 1, padding: "7px 10px", fontSize: 13 }}
                  />
                </div>
                {draft.competitors.length > 0 && (
                  <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
                    Excluded companies (from site competitors): {draft.competitors.join(", ")}
                  </div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <label className="auth-label" style={{ fontSize: 12 }}>
                    Agent / Campaign Name
                    <input
                      value={draft.company_name}
                      onChange={(e) => setDraft({ ...draft, company_name: e.target.value })}
                      style={{ marginTop: 4, padding: "7px 10px", fontSize: 13 }}
                    />
                  </label>
                  <label className="auth-label" style={{ fontSize: 12 }}>
                    Target Buyer Description
                    <input
                      value={draft.icp_description}
                      onChange={(e) => setDraft({ ...draft, icp_description: e.target.value })}
                      style={{ marginTop: 4, padding: "7px 10px", fontSize: 13 }}
                    />
                  </label>
                </div>
                <label className="auth-label" style={{ fontSize: 12, marginTop: 8 }}>
                  Pitch / Value Proposition
                  <textarea
                    rows={2}
                    value={draft.offer}
                    onChange={(e) => setDraft({ ...draft, offer: e.target.value })}
                    style={{ marginTop: 4, padding: "7px 10px", fontSize: 13 }}
                  />
                </label>
              </div>

              {/* Buying & Social Signals Selector */}
              <div style={{ border: "var(--gb-hairline)", padding: 14, marginBottom: 14 }}>
                <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, fontWeight: 600, marginBottom: 8 }}>
                  HIGH-INTENT SIGNALS TO TRACK ({draft.selected_signals.length} ACTIVE)
                </div>
                {draft.search_keywords.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                    {draft.search_keywords.map((kw) => (
                      <GradientPill key={kw} variant="peach">{`"${kw}"`}</GradientPill>
                    ))}
                  </div>
                )}
                {draft.search_keywords.length === 0 && draft.status !== "low_evidence" && (
                  <div style={{ fontSize: 12, color: "#888", marginBottom: 8 }}>
                    No LinkedIn keywords extracted from the page. Toggle event signals below, or add a blurb and re-analyze.
                  </div>
                )}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {SIGNAL_CATALOG.map((sig) => {
                    const active = draft.selected_signals.includes(sig.key);
                    return (
                      <button
                        key={sig.key}
                        type="button"
                        onClick={() => toggleSignal(sig.key)}
                        style={{
                          padding: "5px 11px",
                          borderRadius: 999,
                          border: active ? "1.5px solid #FA651E" : "1px solid #DDD",
                          background: active ? "rgba(250, 101, 30, 0.1)" : "#FFF",
                          color: active ? "#D86B23" : "#666",
                          fontFamily: "var(--gb-font-mono)",
                          fontSize: 11,
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        {active ? "● " : "+ "}
                        {sig.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Multichannel Sequence + Copilot vs Full Auto */}
              <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 12, marginBottom: 16 }}>
                <div style={{ border: "var(--gb-hairline)", padding: 12 }}>
                  <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, fontWeight: 600, marginBottom: 6 }}>
                    COORDINATED MULTICHANNEL SEQUENCE
                  </div>
                  {(draft.sequence || DEFAULT_SEQUENCE).map((s) => (
                    <div key={s.step} style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, padding: "3px 0", borderBottom: "1px dashed #EEE" }}>
                      <span>
                        <strong>0{s.step}</strong> {s.label}
                      </span>
                      <span style={{ fontFamily: "var(--gb-font-mono)", color: "#888", fontSize: 10.5 }}>{s.delay}</span>
                    </div>
                  ))}
                </div>

                <div style={{ border: "var(--gb-hairline)", padding: 12, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                  <div>
                    <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, fontWeight: 600, marginBottom: 8 }}>
                      AUTONOMY CONTROL MODE
                    </div>
                    <button
                      type="button"
                      onClick={() => setDraft({ ...draft, agent_mode: "copilot" })}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        padding: "8px 10px",
                        marginBottom: 6,
                        border: draft.agent_mode === "copilot" ? "1.5px solid #0A0A0A" : "1px solid #DDD",
                        background: draft.agent_mode === "copilot" ? "#FBEF76" : "#FFF",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ fontWeight: 700, fontSize: 12 }}>🛡️ AI Copilot (Approve before send)</div>
                      <div style={{ fontSize: 10.5, color: "#444" }}>Agent researches &amp; drafts; you approve in 1 click.</div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setDraft({ ...draft, agent_mode: "full_auto" })}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        padding: "8px 10px",
                        border: draft.agent_mode === "full_auto" ? "1.5px solid #FA651E" : "1px solid #DDD",
                        background: draft.agent_mode === "full_auto" ? "rgba(250,101,30,0.12)" : "#FFF",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ fontWeight: 700, fontSize: 12 }}>⚡ Full Auto (24/7 Autonomous)</div>
                      <div style={{ fontSize: 10.5, color: "#444" }}>Auto-dispatches safe sends; gates risky ones.</div>
                    </button>
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <button className="gb-light-btn" type="button" onClick={() => setStep(0)} disabled={busy}>
                  ← Change Website
                </button>
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  <button className="ob-skip" style={{ margin: 0 }} onClick={onSkip} disabled={busy}>
                    Skip
                  </button>
                  <CoralExpandButton size="sm" onClick={launchFullCycleAgent} disabled={busy}>
                    {busy ? "Launching Agent…" : "Launch Full-Cycle Agent →"}
                  </CoralExpandButton>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
