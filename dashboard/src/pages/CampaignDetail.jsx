import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, getTenantId } from "../api/client.js";

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

export default function CampaignDetail() {
  const { id } = useParams();
  const [c, setC] = useState(null);
  const [roi, setRoi] = useState(null);
  const [launchChecklist, setLaunchChecklist] = useState(null);
  const [proofPackage, setProofPackage] = useState(null);
  const [roiErr, setRoiErr] = useState("");
  const [launchErr, setLaunchErr] = useState("");
  const [proofErr, setProofErr] = useState("");
  const [roiLoading, setRoiLoading] = useState(false);
  const [preflightDomain, setPreflightDomain] = useState("");
  const [preflightRunning, setPreflightRunning] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    setErr("");
    api
      .get(`/api/campaigns/${id}`)
      .then((data) => {
        setC(data);
        setPreflightDomain((current) => current || data.deliverability_preflight?.domain || "");
      })
      .catch((e) => setErr(e.message));
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
    // Tenant is derived server-side from the JWT; the presence check above is
    // just a friendly "are you signed in?" guard.
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

  async function action(path) {
    setBusy(true);
    try {
      await api.post(path, {});
      load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
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
          <h1>{c.customer_name}</h1>
          <span className={`pill pill-${c.status}`}>{c.status}</span>
        </div>
        <div className="actions">
          <Link className="btn" to={`/campaigns/${id}/contacts`}>Contacts ({c.prospect_count})</Link>
          <Link className="btn" to={`/campaigns/${id}/inbox`}>Inbox ({c.pending_replies})</Link>
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

      {c.jobs_awaiting_approval?.length > 0 && (
        <div className="card">
          <h3>HITL approval queue ({c.jobs_awaiting_approval.length})</h3>
          <table className="data">
            <thead><tr><th>To</th><th>Subject</th><th></th></tr></thead>
            <tbody>
              {c.jobs_awaiting_approval.map((j) => (
                <tr key={j.id}>
                  <td>{j.to_email}</td>
                  <td>{j.subject}</td>
                  <td>
                    <button className="btn small primary" disabled={busy}
                      onClick={() => action(`/api/campaigns/${id}/approve-job/${j.id}`)}>Approve</button>
                    <button className="btn small" disabled={busy}
                      onClick={() => action(`/api/campaigns/${id}/reject-job/${j.id}`)}>Reject</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

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
