import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client.js";

export default function Inbox() {
  const { id } = useParams();
  const [replies, setReplies] = useState([]);
  const [err, setErr] = useState("");

  function load() {
    api.get(`/api/inbox?campaign_id=${id}`).then(setReplies).catch((e) => setErr(e.message));
  }
  useEffect(load, [id]);

  async function act(replyId, action) {
    try {
      await api.post(`/api/inbox/${replyId}/${action}`, {});
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Inbox</h1>
        <Link className="btn" to={`/campaigns/${id}`}>← Campaign</Link>
      </div>
      {err && <div className="error">{err}</div>}

      {replies.length === 0 && <p className="muted">No replies yet.</p>}
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
    </div>
  );
}
