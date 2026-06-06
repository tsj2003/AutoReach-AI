import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, apiFetch } from "../api/client.js";

export default function Contacts() {
  const { id } = useParams();
  const [rows, setRows] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [err, setErr] = useState("");
  const [uploadMsg, setUploadMsg] = useState("");

  function loadPage(c) {
    const q = new URLSearchParams({ campaign_id: id, limit: "50" });
    if (c) q.set("cursor", c);
    api.get(`/api/contacts?${q}`).then((data) => {
      setRows((prev) => (c ? [...prev, ...data.data] : data.data));
      setCursor(data.next_cursor);
      setHasMore(data.has_more);
    }).catch((e) => setErr(e.message));
  }
  useEffect(() => loadPage(null), [id]);

  async function upload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploadMsg("Uploading…");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await apiFetch(`/api/contacts/upload?campaign_id=${id}`, { method: "POST", body: fd });
      setUploadMsg(`Loaded ${res.loaded}, skipped ${res.skipped_invalid_email} invalid, ${res.skipped_duplicates} dupes, ${res.skipped_existing} existing`);
      loadPage(null);
    } catch (e) {
      setUploadMsg("Error: " + e.message);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Contacts</h1>
        <Link className="btn" to={`/campaigns/${id}`}>← Campaign</Link>
      </div>
      {err && <div className="error">{err}</div>}

      <div className="card">
        <h3>Upload CSV</h3>
        <p className="muted small">Required column: email. Optional: name, company, title.</p>
        <input type="file" accept=".csv" onChange={upload} />
        {uploadMsg && <div className="notice">{uploadMsg}</div>}
      </div>

      <table className="data">
        <thead>
          <tr><th>Email</th><th>Name</th><th>Company</th><th>Status</th></tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td>{p.email}</td>
              <td>{p.full_name || "—"}</td>
              <td>{p.company || "—"}</td>
              <td><span className={`pill pill-${p.status}`}>{p.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && (
        <button className="btn" onClick={() => loadPage(cursor)}>Load more</button>
      )}
    </div>
  );
}
