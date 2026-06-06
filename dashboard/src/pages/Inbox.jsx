import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client.js";

// Unibox V2 — two folders:
//   Primary : tracked replies from known prospects (/api/inbox)
//   Others  : orphaned/untracked replies — forwards, colleague replies (/api/inbox/others)
//             each Other can be attached to an existing lead.
export default function Inbox() {
  const { id } = useParams();
  const [folder, setFolder] = useState("primary");
  const [replies, setReplies] = useState([]);
  const [others, setOthers] = useState([]);
  const [err, setErr] = useState("");

  function loadPrimary() {
    api.get(`/api/inbox?campaign_id=${id}`).then(setReplies).catch((e) => setErr(e.message));
  }
  function loadOthers() {
    // Orphaned replies are tenant-scoped, not campaign-scoped.
    api.get(`/api/inbox/others`).then(setOthers).catch((e) => setErr(e.message));
  }
  function loadAll() {
    loadPrimary();
    loadOthers();
  }
  useEffect(loadAll, [id]);

  async function act(replyId, action) {
    setErr("");
    try {
      await api.post(`/api/inbox/${replyId}/${action}`, {});
      loadPrimary();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Unibox</h1>
        <Link className="btn" to={`/campaigns/${id}`}>← Campaign</Link>
      </div>
      {err && <div className="error">{err}</div>}

      {/* Folder separation: Primary vs Others */}
      <nav className="filters" style={{ marginBottom: 16 }}>
        <a
          href="#primary"
          className={folder === "primary" ? "active" : ""}
          onClick={(e) => { e.preventDefault(); setFolder("primary"); }}
        >
          Primary{replies.length ? ` (${replies.length})` : ""}
        </a>
        <a
          href="#others"
          className={folder === "others" ? "active" : ""}
          onClick={(e) => { e.preventDefault(); setFolder("others"); }}
        >
          Others{others.length ? ` (${others.length})` : ""}
        </a>
      </nav>

      {folder === "primary" && (
        <PrimaryFolder replies={replies} act={act} />
      )}
      {folder === "others" && (
        <OthersFolder
          campaignId={id}
          others={others}
          onChange={loadOthers}
          setErr={setErr}
        />
      )}
    </div>
  );
}

function PrimaryFolder({ replies, act }) {
  if (replies.length === 0) {
    return <p className="muted">No tracked replies yet.</p>;
  }
  return (
    <>
      {replies.map((r) => (
        <div className="card reply" key={r.id}>
          <div className="reply-head">
            <span className={`pill pill-${r.classification}`}>{r.classification}</span>
            <span className={`pill pill-${r.status}`}>{r.status}</span>
            <strong>{r.prospect_email}</strong>
            {r.prospect_company && <span className="muted">· {r.prospect_company}</span>}
          </div>
          <blockquote>{r.snippet}</blockquote>
          {r.suggested_reply && (
            <div className="suggested">
              <div className="muted small">Suggested reply:</div>
              <p>{r.suggested_reply}</p>
            </div>
          )}
          {r.status === "pending" && (
            <div className="actions">
              <button className="btn small primary" onClick={() => act(r.id, "approve")}>Mark sent</button>
              <button className="btn small" onClick={() => act(r.id, "regenerate-draft")}>Regenerate</button>
              <button className="btn small" onClick={() => act(r.id, "discard")}>Discard</button>
            </div>
          )}
        </div>
      ))}
    </>
  );
}

function OthersFolder({ campaignId, others, onChange, setErr }) {
  const [attaching, setAttaching] = useState(null); // orphan id being attached

  async function ignore(orphanId) {
    setErr("");
    try {
      await api.post(`/api/inbox/others/${orphanId}/ignore`, {});
      onChange();
    } catch (e) {
      setErr(e.message);
    }
  }

  if (others.length === 0) {
    return (
      <p className="muted">
        No untracked replies. Forwarded emails and replies from unknown addresses land here.
      </p>
    );
  }

  return (
    <>
      <p className="muted small">
        These replies came from addresses that don't match any known lead (forwards, colleagues,
        personal emails). Attach one to its original lead to fold it into the sequence.
      </p>
      {others.map((o) => (
        <div className="card reply" key={o.id}>
          <div className="reply-head">
            <span className="pill pill-new">untracked</span>
            <strong>{o.from_name || o.from_email}</strong>
            <span className="muted">· {o.from_email}</span>
          </div>
          {o.subject && <div className="muted small">{o.subject}</div>}
          <blockquote>{o.snippet || "(no preview)"}</blockquote>
          <div className="actions">
            <button className="btn small primary" onClick={() => setAttaching(o.id)}>
              Attach lead
            </button>
            <button className="btn small" onClick={() => ignore(o.id)}>Ignore</button>
          </div>
          {attaching === o.id && (
            <AttachPicker
              campaignId={campaignId}
              orphanId={o.id}
              onDone={() => { setAttaching(null); onChange(); }}
              onCancel={() => setAttaching(null)}
              setErr={setErr}
            />
          )}
        </div>
      ))}
    </>
  );
}

// Lets the operator search the campaign's leads and attach the orphan to one.
function AttachPicker({ campaignId, orphanId, onDone, onCancel, setErr }) {
  const [leads, setLeads] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get(`/api/contacts?campaign_id=${campaignId}&limit=200`)
      .then((data) => setLeads(data.data))
      .catch((e) => setErr(e.message));
  }, [campaignId]);

  const filtered = leads.filter((l) =>
    (l.email || "").toLowerCase().includes(q.toLowerCase()) ||
    (l.full_name || "").toLowerCase().includes(q.toLowerCase()) ||
    (l.company || "").toLowerCase().includes(q.toLowerCase())
  );

  async function attach(prospectId) {
    setErr("");
    try {
      await api.post(`/api/inbox/others/${orphanId}/attach`, { prospect_id: prospectId });
      onDone();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <div className="attach-picker">
      <div className="attach-head">
        <strong>Attach to lead</strong>
        <button className="btn small" onClick={onCancel}>Cancel</button>
      </div>
      <input
        className="attach-search"
        placeholder="Search leads by email, name, company…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        autoFocus
      />
      <div className="attach-list">
        {filtered.length === 0 && <div className="muted small">No matching leads.</div>}
        {filtered.slice(0, 20).map((l) => (
          <button key={l.id} className="attach-row" onClick={() => attach(l.id)}>
            <span>{l.email}</span>
            <span className="muted small">{l.full_name || ""} {l.company ? `· ${l.company}` : ""}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
