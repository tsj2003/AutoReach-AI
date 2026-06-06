import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client.js";

function money(cents) {
  return `$${((cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

export default function CampaignDetail() {
  const { id } = useParams();
  const [c, setC] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    api.get(`/api/campaigns/${id}`).then(setC).catch((e) => setErr(e.message));
  }
  useEffect(load, [id]);

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

  if (err) return <div className="error">{err}</div>;
  if (!c) return <div className="muted">Loading…</div>;

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

      <div className="card">
        <h3>Offer</h3>
        <p>{c.offer}</p>
        <h4 className="muted">ICP</h4>
        <p className="muted">{c.icp_description}</p>
        <div className="actions">
          <button className="btn" disabled={busy} onClick={() => action(`/api/campaigns/${id}/tick`)}>Tick</button>
          <button className="btn" disabled={busy} onClick={() => action(`/api/campaigns/${id}/drain`)}>Drain</button>
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
