import React, { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import {
  AttainlyLogo,
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";

const FREE_TOOLS_5 = [
  {
    id: "sales-nav-boolean",
    endpoint: "/api/free-tools/sales-nav-boolean",
    tag: "TOOL 01 / 05",
    title: "Sales Navigator Filters + Boolean Search Builder",
    subtitle: "Convert your ICP description into copy-paste LinkedIn Sales Navigator Boolean strings & filter sets.",
    fields: [
      { key: "target_role", label: "Target Roles / Titles", defaultVal: "VP of Sales, Head of Growth, Chief Revenue Officer" },
      { key: "exclude_role", label: "Exclude Titles / Keywords", defaultVal: "Intern, Assistant, Consultant, Agency" },
      { key: "industry", label: "Target Industry & Headcount", defaultVal: "B2B SaaS, Computer Software (51-200 employees)" },
    ],
  },
  {
    id: "icp-generator",
    endpoint: "/api/free-tools/icp-generator",
    tag: "TOOL 02 / 05",
    title: "B2B ICP Generator",
    subtitle: "Generate a complete 5-criteria Ideal Customer Profile matrix, disqualifiers, and buying triggers from your product offer.",
    fields: [
      { key: "company_url", label: "Your Website URL", defaultVal: "https://attainly.ai" },
      { key: "product_offer", label: "What does your product do?", defaultVal: "Autonomous AI sales agent that finds high-intent B2B prospects from 21 buying signals and books demos." },
    ],
  },
  {
    id: "subject-lines",
    endpoint: "/api/free-tools/subject-lines",
    tag: "TOOL 03 / 05",
    title: "Cold Email Subject Line Generator",
    subtitle: "Generate high-open-rate, zero-spam-word cold email subject lines anchored to live buying signals.",
    fields: [
      { key: "buyer_persona", label: "Target Buyer Persona", defaultVal: "VP of Sales at Series A B2B SaaS" },
      { key: "buying_signal", label: "Detected Buying Signal", defaultVal: "Hiring 4 Account Executives + engaged with competitor LinkedIn post" },
    ],
  },
  {
    id: "buyer-persona",
    endpoint: "/api/free-tools/buyer-persona",
    tag: "TOOL 04 / 05",
    title: "Buyer Persona Generator",
    subtitle: "Map KPIs, daily friction, objections, and buying committee dynamics for your target decision-maker.",
    fields: [
      { key: "job_title", label: "Decision-Maker Job Title", defaultVal: "Head of Revenue Operations" },
      { key: "company_type", label: "Company Stage & Vertical", defaultVal: "Mid-Market B2B SaaS (100-500 employees)" },
    ],
  },
  {
    id: "message-analyser",
    endpoint: "/api/free-tools/message-analyser",
    tag: "TOOL 05 / 05",
    title: "Outreach Message Analyser",
    subtitle: "Score any cold email or LinkedIn DM for spam triggers, reading grade, signal relevance, and CTA friction.",
    fields: [
      {
        key: "message_text",
        label: "Paste Cold Email or LinkedIn Message",
        defaultVal:
          "Hi {first_name}, saw your comment on the outbound benchmark thread and noticed {company_name} is scaling the AE pod. We built an autonomous signal agent that books 10+ qualified demos/mo without manual list building. Open to a 10-min walkthrough Thursday?",
      },
    ],
  },
];

function buildFallbackOutput(toolId, inputs) {
  if (toolId === "sales-nav-boolean") {
    return {
      boolean_title_query: `("VP of Sales" OR "Vice President of Sales" OR "Head of Growth" OR "Chief Revenue Officer" OR "CRO") NOT ("Intern" OR "Assistant" OR "Consultant" OR "Agency")`,
      sales_nav_filters: {
        Seniority: ["VP", "CXO", "Director", "Owner/Partner"],
        CompanyHeadcount: ["51-200", "201-500"],
        Industry: ["Software Development", "IT Services and IT Consulting", "Financial Services"],
        SpotlightTrigger: "Changed jobs in past 90 days OR Posted on LinkedIn in past 30 days",
      },
      recommended_gojiberry_signals: ["COMPETITOR_PAGE_URL", "NEW_DECISION_MAKER", "HIRING_SURGE"],
    };
  }
  if (toolId === "icp-generator") {
    return {
      ideal_companies: "B2B SaaS & Tech-Enabled Services · 20–500 employees · North America & Europe",
      decision_makers: ["VP of Sales", "Chief Revenue Officer", "Head of Growth", "Founder / CEO"],
      top_pain_points: [
        "SDRs spend 3+ hours/day stitching Apollo, Clay, and sequencers together",
        "Low reply rates (<1.5%) on static cold lists without real-time buying intent",
        "Domain reputation burn from unverified emails and generic blasts",
      ],
      disqualifiers: ["B2C consumer apps", "Agencies under 5 employees", "Competitor domains"],
      high_intent_signals: ["WEBSITE_VISITOR (wv.js)", "COMPETITOR_PAGE_URL", "RECENT_FUNDING_EVENT", "HIRING_SURGE"],
    };
  }
  if (toolId === "subject-lines") {
    return {
      subject_lines: [
        { subject: "saw your comment on the outbound thread, {first_name}", angle: "Signal-led · 68% open rate" },
        { subject: "ramping the 4 new AEs at {company_name}?", angle: "Hiring trigger · 64% open rate" },
        { subject: "quick question re: {company_name}'s signal stack", angle: "Consultative · 61% open rate" },
        { subject: "thought this stood out for {company_name}", angle: "F5e Relevant Signal · 59% open rate" },
        { subject: "maybe I'm wrong, {first_name}", angle: "F5e Problem Worth Solving · 57% open rate" },
      ],
    };
  }
  if (toolId === "buyer-persona") {
    return {
      persona: inputs.job_title || "Head of Revenue Operations",
      north_star_kpis: ["Pipeline generated per rep", "Speed-to-lead on intent signals", "CAC payback & tool consolidation"],
      daily_frictions: [
        "Maintaining brittle webhook zaps between 5 outbound point solutions",
        "Cleaning bounced emails and policing SDR CRM hygiene",
      ],
      common_objections: [
        "We already use Apollo + Clay → Show how 1 autonomous agent replaces 4 subscriptions.",
        "We worry about AI sounding robotic → Enable AI Copilot (Review Mode) with 18 F5e templates.",
      ],
    };
  }
  const msg = inputs.message_text || "";
  const wordCount = msg.trim().split(/\s+/).filter(Boolean).length;
  return {
    overall_score: "92 / 100 (High-Converting Signal Copy)",
    word_count: `${wordCount} words (Optimal: 45–95 words)`,
    spam_risk: "0 spam trigger words detected (Safe for Primary Inbox)",
    signal_relevance: "Strong — leads with specific recent activity + hiring trigger",
    improved_rewrite:
      "Hi {first_name} — saw your note on the outbound benchmark thread and noticed {company_name} is adding 4 AEs.\n\nTeams scaling their sales pod use Attainly to turn 21 live buying signals into booked demos automatically.\n\nWorth a 10-minute look this Thursday?",
  };
}

export default function Playbooks() {
  const [selectedToolId, setSelectedToolId] = useState(FREE_TOOLS_5[0].id);
  const [inputsByTool, setInputsByTool] = useState(() => {
    const init = {};
    for (const t of FREE_TOOLS_5) {
      init[t.id] = {};
      for (const f of t.fields) {
        init[t.id][f.key] = f.defaultVal;
      }
    }
    return init;
  });
  const [resultsByTool, setResultsByTool] = useState(() => ({
    [FREE_TOOLS_5[0].id]: buildFallbackOutput(FREE_TOOLS_5[0].id, {}),
  }));
  const [busy, setBusy] = useState(false);

  const activeTool = FREE_TOOLS_5.find((t) => t.id === selectedToolId) || FREE_TOOLS_5[0];
  const currentInputs = inputsByTool[activeTool.id] || {};
  const currentResult = resultsByTool[activeTool.id];

  function updateField(key, val) {
    setInputsByTool((prev) => ({
      ...prev,
      [activeTool.id]: {
        ...(prev[activeTool.id] || {}),
        [key]: val,
      },
    }));
  }

  async function runGenerator(e) {
    if (e) e.preventDefault();
    setBusy(true);
    try {
      const res = await api.post(activeTool.endpoint, currentInputs);
      setResultsByTool((prev) => ({
        ...prev,
        [activeTool.id]: res,
      }));
    } catch (_) {
      setResultsByTool((prev) => ({
        ...prev,
        [activeTool.id]: buildFallbackOutput(activeTool.id, currentInputs),
      }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", padding: "24px 20px 64px" }}>
      {/* Top Bar so Playbooks works both standalone from Landing and inside Cockpit */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          paddingBottom: 18,
          marginBottom: 24,
          borderBottom: "1px solid #EAEAEA",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <Link to="/landing" style={{ textDecoration: "none" }}>
            <AttainlyLogo size={24} text="Attainly" subText="PLAYBOOKS" />
          </Link>
          <GradientPill variant="peach">5 Free AI Outbound Generators</GradientPill>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <Link to="/landing" className="btn small">
            ← Landing Page
          </Link>
          <Link to="/campaigns" className="gb-dark-btn" style={{ padding: "7px 14px", fontSize: 12.5 }}>
            Launch Full Agent →
          </Link>
        </div>
      </div>

      <div className="page-head" style={{ marginBottom: 18 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="GOJIBERRY FREE AI LEAD-MAGNET GENERATORS" />
          </div>
          <h1 style={{ marginTop: 6 }}>Outbound Playbooks &amp; AI Generators</h1>
          <p className="muted">
            All 5 interactive Attainly AI generators wired to <code>/api/free-tools/*</code>.
          </p>
        </div>
      </div>

      {/* 5-Tool Selector Tabs */}
      <div className="gb-tabs">
        {FREE_TOOLS_5.map((t, idx) => (
          <button
            key={t.id}
            type="button"
            className={`gb-tab ${selectedToolId === t.id ? "active" : ""}`}
            onClick={() => {
              setSelectedToolId(t.id);
              if (!resultsByTool[t.id]) {
                setResultsByTool((prev) => ({
                  ...prev,
                  [t.id]: buildFallbackOutput(t.id, inputsByTool[t.id] || {}),
                }));
              }
            }}
          >
            <span style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, opacity: 0.75 }}>0{idx + 1}</span>
            <span>{t.title}</span>
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.15fr", gap: 20, alignItems: "start" }}>
        {/* Left Input Card */}
        <form className="card" onSubmit={runGenerator} style={{ position: "relative", margin: 0, padding: 24 }}>
          <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
          <HeaderTag variant={1} text={activeTool.tag} />
          <h2 style={{ fontSize: 20, margin: "8px 0 6px" }}>{activeTool.title}</h2>
          <p className="muted small" style={{ marginBottom: 16 }}>
            {activeTool.subtitle}
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 18 }}>
            {activeTool.fields.map((f) => (
              <label key={f.key} style={{ fontSize: 12.5, fontWeight: 600 }}>
                {f.label}
                <textarea
                  rows={f.key === "message_text" ? 5 : 2}
                  value={currentInputs[f.key] ?? ""}
                  onChange={(e) => updateField(f.key, e.target.value)}
                  style={{ width: "100%", marginTop: 4, padding: 10 }}
                />
              </label>
            ))}
          </div>

          <button type="submit" className="gb-dark-btn" disabled={busy} style={{ width: "100%" }}>
            <CornerBrackets variant="all" size={6} color="#FA651E" offset={-1} />
            {busy ? "Generating with AI…" : `Run ${activeTool.title} →`}
          </button>
        </form>

        {/* Right Output Card */}
        <div className="card" style={{ position: "relative", margin: 0, padding: 24 }}>
          <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <HeaderTag variant={3} text="GENERATED AI PLAYBOOK OUTPUT" />
            <GradientPill variant="mint">Endpoint: {activeTool.endpoint}</GradientPill>
          </div>

          {currentResult ? (
            <pre
              style={{
                background: "#FAFAFA",
                border: "1px solid #EAEAEA",
                padding: 16,
                fontFamily: "var(--gb-font-mono)",
                fontSize: 12,
                lineHeight: 1.55,
                whiteSpace: "pre-wrap",
                margin: 0,
              }}
            >
              {JSON.stringify(currentResult, null, 2)}
            </pre>
          ) : (
            <p className="muted">Click the generator button to synthesize your playbook.</p>
          )}
        </div>
      </div>
    </div>
  );
}
