import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../contexts/AuthContext.jsx";
import OnboardingWizard from "../components/OnboardingWizard.jsx";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";

function money(cents) {
  return `$${((cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [usage, setUsage] = useState(null);
  const [mailboxes, setMailboxes] = useState(null);
  const [err, setErr] = useState("");
  const [showWizard, setShowWizard] = useState(false);

  const dismissKey = user ? `autoreach_onboarded_${user.tenant_id}` : null;

  function load() {
    api.get("/api/billing/usage").then(setUsage).catch(() => setUsage(null));
    api.get("/api/mailboxes").then((d) => setMailboxes(Array.isArray(d) ? d : d?.mailboxes || [])).catch(() => setMailboxes([]));

    return api
      .get("/api/analytics/dashboard")
      .then((d) => {
        setData(d);
        return d;
      })
      .catch((e) => setErr(e.message));
  }

  useEffect(() => {
    load().then((d) => {
      if (!d || !dismissKey) return;
      const dismissed = localStorage.getItem(dismissKey);
      const hasOnboardingSite =
        localStorage.getItem("onboarding_website") ||
        sessionStorage.getItem("onboarding_website");
      if (((d.campaigns || []).length === 0 && !dismissed) || hasOnboardingSite) {
        setShowWizard(true);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dismissKey]);

  function finishWizard(created) {
    if (dismissKey) localStorage.setItem(dismissKey, "1");
    setShowWizard(false);
    if (created?.id) {
      navigate(`/campaigns/${created.id}/contacts`);
      return;
    }
    setData(null);
    load();
  }

  function skipWizard() {
    if (dismissKey) localStorage.setItem(dismissKey, "1");
    setShowWizard(false);
  }

  if (err) return <div className="error">{err}</div>;
  if (!data) return <div className="muted">Loading…</div>;

  const t = data.totals || {};
  const cards = [
    { label: "Campaigns", value: t.campaigns ?? 0 },
    { label: "Active", value: t.active_campaigns ?? 0 },
    { label: "Booked", value: t.total_booked ?? 0 },
    { label: "Qualified", value: t.total_qualified ?? 0 },
    { label: "Revenue", value: money(t.total_revenue_cents) },
    { label: "Cost", value: money(t.total_cost_cents) },
    { label: "Margin", value: money(t.total_margin_cents) },
  ];

  const campaignCount = (data.campaigns || []).length;
  const mailboxCount = Array.isArray(mailboxes) ? mailboxes.length : 0;
  const atCampaignCap =
    usage && usage.usage && usage.usage.campaigns >= usage.usage.campaigns_limit;

  const nextSteps = [];
  if (mailboxCount === 0) {
    nextSteps.push({
      key: "mailbox",
      title: "Connect Gmail",
      body: "Outbound needs a healthy mailbox before anything can send.",
      to: "/operations/mailboxes",
      cta: "Open Mailboxes",
    });
  }
  if (campaignCount === 0) {
    nextSteps.push({
      key: "campaign",
      title: "Create your first campaign",
      body: "Define the offer + ICP, then add contacts.",
      to: "/campaigns",
      cta: "Go to Campaigns",
    });
  } else if (atCampaignCap) {
    nextSteps.push({
      key: "cap",
      title: "Campaign limit reached",
      body: `Free plan allows ${usage.usage.campaigns_limit} active campaign. Archive one or upgrade.`,
      to: "/billing",
      cta: "View plan",
    });
  }
  if (campaignCount > 0 && mailboxCount > 0) {
    nextSteps.push({
      key: "ops",
      title: "Check Operations",
      body: "Confirm launch readiness, pending approvals, and mailbox health.",
      to: "/operations",
      cta: "Open Operations",
    });
    nextSteps.push({
      key: "linkedin",
      title: "Optional: Connect LinkedIn",
      body: "Needed only if your sequence includes LinkedIn steps. Without a seat, those steps skip to email.",
      to: "/operations/linkedin",
      cta: "LinkedIn",
    });
  }

  return (
    <div>
      {showWizard && (
        <OnboardingWizard onComplete={finishWizard} onSkip={skipWizard} />
      )}

      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="REVENUE COCKPIT" />
          </div>
          <h1 style={{ marginTop: 6 }}>Dashboard</h1>
          <p className="muted small" style={{ margin: "2px 0 0" }}>
            Campaign status, approvals, mailbox health, and ROI proof
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="btn" onClick={() => setShowWizard(true)}>
            ⚡ 3-Min Website Wizard
          </button>
          <Link to="/campaigns" className="btn primary">
            Campaigns
          </Link>
        </div>
      </div>

      {nextSteps.length > 0 && (
        <div className="card" style={{ position: "relative", marginBottom: 18 }}>
          <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
          <HeaderTag variant={1} text="NEXT ACTIONS" />
          <div style={{ display: "grid", gap: 12, marginTop: 10 }}>
            {nextSteps.map((step) => (
              <div
                key={step.key}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <div style={{ fontWeight: 700 }}>{step.title}</div>
                  <p className="muted small" style={{ margin: "2px 0 0" }}>
                    {step.body}
                  </p>
                </div>
                <Link className="btn small primary" to={step.to}>
                  {step.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="stat-grid">
        {cards.map((c) => (
          <div key={c.label} className="stat-card" style={{ position: "relative" }}>
            <CornerBrackets variant="diagonal" size={6} color="#0A0A0A" offset={-1} />
            <div className="stat-value">{c.value}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
      </div>

      <h2>Active Campaigns</h2>
      <table className="data">
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th className="num">Qualified</th>
            <th className="num">Revenue</th>
          </tr>
        </thead>
        <tbody>
          {(data.campaigns || []).map((c) => (
            <tr key={c.id}>
              <td>
                <Link to={`/campaigns/${c.id}`}>{c.name || c.customer_name}</Link>
              </td>
              <td>
                <span className={`pill pill-${c.status}`}>{c.status}</span>
              </td>
              <td className="num">{c.qualified ?? c.meetings_booked ?? 0}</td>
              <td className="num">{money(c.revenue_cents)}</td>
            </tr>
          ))}
          {(data.campaigns || []).length === 0 && (
            <tr>
              <td colSpan="4" className="muted">
                No campaigns yet. Use the 3-Min Website Wizard or open Campaigns.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {usage && (
        <p className="muted small" style={{ marginTop: 16 }}>
          Plan <GradientPill variant="peach">{usage.plan}</GradientPill>
          {" "}· campaigns {usage.usage.campaigns}/{usage.usage.campaigns_limit}
          {" "}· leads {usage.usage.leads_total}/{usage.usage.leads_limit}
        </p>
      )}
    </div>
  );
}
