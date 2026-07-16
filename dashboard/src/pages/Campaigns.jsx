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
    client_cure: "", allowed_signal_types: "funding_round",
    booking_url: "", monthly_meeting_target: 20,
    price_per_outcome_cents: 50000, monthly_budget_cents: 200000,
    hitl_threshold: 50,
    personalize_enabled: false,
  });
  const [err, setErr] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [autofilling, setAutofilling] = useState(false);
  const [autofillNote, setAutofillNote] = useState("");

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
      }));
      setAutofillNote(
        d.source === "llm"
          ? "Drafted from your website — review and edit, then create."
          : "Couldn't read the site (or AI is off) — starter template loaded; edit the fields."
      );
    } catch (e) {
      setErr(e.message);
    } finally {
      setAutofilling(false);
    }
  }

  function load() {
    api.get("/api/campaigns").then(setCampaigns).catch((e) => setErr(e.message));
  }
  useEffect(load, []);

  async function create(e) {
    e.preventDefault();
    setErr("");
    try {
      const payload = {
        ...form,
        allowed_signal_types: form.allowed_signal_types
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
      };
      await api.post("/api/campaigns", payload);
      setShowForm(false);
      setForm({ ...form, customer_name: "", offer: "", icp_description: "", client_cure: "" });
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
          <div className="autofill">
            <label>⚡ Set up in seconds — paste your website
              <input
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                placeholder="https://yourcompany.com"
              />
            </label>
            <button type="button" className="btn" disabled={autofilling} onClick={autofillFromWebsite}>
              {autofilling ? "Reading your site…" : "Auto-fill from website"}
            </button>
            {autofillNote && <p className="notice">{autofillNote}</p>}
          </div>
          <label>Customer name<input value={form.customer_name} onChange={upd("customer_name")} required /></label>
          <label>Offer<textarea rows="2" value={form.offer} onChange={upd("offer")} required /></label>
          <label>ICP description<textarea rows="2" value={form.icp_description} onChange={upd("icp_description")} required /></label>
          <label>Client cure<textarea rows="2" value={form.client_cure} onChange={upd("client_cure")} placeholder="The specific pain this offer solves right now" /></label>
          <label>Allowed signal types<input value={form.allowed_signal_types} onChange={upd("allowed_signal_types")} placeholder="funding_round, job_posting" /></label>
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
