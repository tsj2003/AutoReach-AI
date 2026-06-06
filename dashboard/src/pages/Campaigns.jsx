import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";

function money(cents) {
  return `$${((cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    customer_name: "", offer: "", icp_description: "",
    booking_url: "", monthly_meeting_target: 20,
    price_per_outcome_cents: 50000, hitl_threshold: 50,
    personalize_enabled: false,
  });
  const [err, setErr] = useState("");

  function load() {
    api.get("/api/campaigns").then(setCampaigns).catch((e) => setErr(e.message));
  }
  useEffect(load, []);

  async function create(e) {
    e.preventDefault();
    setErr("");
    try {
      await api.post("/api/campaigns", form);
      setShowForm(false);
      setForm({ ...form, customer_name: "", offer: "", icp_description: "" });
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
        <h1>Campaigns</h1>
        <button className="btn primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? "Cancel" : "+ New campaign"}
        </button>
      </div>
      {err && <div className="error">{err}</div>}

      {showForm && (
        <form className="card form" onSubmit={create}>
          <label>Customer name<input value={form.customer_name} onChange={upd("customer_name")} required /></label>
          <label>Offer<textarea rows="2" value={form.offer} onChange={upd("offer")} required /></label>
          <label>ICP description<textarea rows="2" value={form.icp_description} onChange={upd("icp_description")} required /></label>
          <label>Booking URL<input value={form.booking_url} onChange={upd("booking_url")} placeholder="https://cal.com/you" /></label>
          <div className="row3">
            <label>Meeting target<input type="number" value={form.monthly_meeting_target} onChange={upd("monthly_meeting_target", true)} /></label>
            <label>Price/meeting (cents)<input type="number" value={form.price_per_outcome_cents} onChange={upd("price_per_outcome_cents", true)} /></label>
            <label>HITL threshold<input type="number" value={form.hitl_threshold} onChange={upd("hitl_threshold", true)} /></label>
          </div>
          <label className="checkbox">
            <input type="checkbox" checked={form.personalize_enabled}
              onChange={(e) => setForm({ ...form, personalize_enabled: e.target.checked })} />
            Enable Gemini personalization
          </label>
          <button className="btn primary">Create</button>
        </form>
      )}

      <table className="data">
        <thead>
          <tr><th>Name</th><th>Status</th><th className="num">Qualified</th><th className="num">Revenue</th><th></th></tr>
        </thead>
        <tbody>
          {campaigns.map((c) => (
            <tr key={c.id}>
              <td><Link to={`/campaigns/${c.id}`}>{c.customer_name}</Link></td>
              <td><span className={`pill pill-${c.status}`}>{c.status}</span></td>
              <td className="num">{c.pnl?.qualified_count ?? 0}</td>
              <td className="num">{money(c.pnl?.revenue_cents)}</td>
              <td><Link to={`/campaigns/${c.id}`}>open →</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
