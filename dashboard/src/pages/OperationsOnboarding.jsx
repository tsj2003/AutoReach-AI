import { useState } from "react";
import { api } from "../api/client.js";

function money(value) {
  return `$${Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function OperationsOnboarding() {
  const [form, setForm] = useState({
    company_name: "",
    domain: "",
    budget_limit: "5000.00",
    meeting_price: "1000.00",
    linkedin_enabled: true,
    mcp_server_command: "",
    mcp_server_url: "",
  });
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  function update(field, asBool = false) {
    return (event) => {
      const value = asBool ? event.target.checked : event.target.value;
      setForm((current) => ({ ...current, [field]: value }));
    };
  }

  async function submit(event) {
    event.preventDefault();
    setErr("");
    setResult(null);
    setSaving(true);
    try {
      const payload = {
        ...form,
        mcp_server_command: form.mcp_server_command.trim() || null,
        mcp_server_url: form.mcp_server_url.trim() || null,
      };
      const created = await api.post("/api/operations/pilot-onboarding", payload);
      setResult(created);
    } catch (error) {
      setErr(error.message);
    } finally {
      setSaving(false);
    }
  }

  const safe = result?.is_safe_to_send;
  const variables = result?.tenant_context?.variables || {};

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Pilot Onboarding</h1>
          <p className="muted">
            Register a tenant only after sender DNS passes the outbound preflight.
          </p>
        </div>
      </div>

      {err && <div className="error">{err}</div>}

      <div className="ops-grid">
        <form className="card form ops-form" onSubmit={submit}>
          <label>
            Company name
            <input value={form.company_name} onChange={update("company_name")} required />
          </label>
          <label>
            Sending domain
            <input
              value={form.domain}
              onChange={update("domain")}
              placeholder="example.com"
              autoComplete="off"
              required
            />
          </label>
          <div className="row2">
            <label>
              Budget limit
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.budget_limit}
                onChange={update("budget_limit")}
                required
              />
            </label>
            <label>
              Meeting price
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.meeting_price}
                onChange={update("meeting_price")}
                required
              />
            </label>
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.linkedin_enabled}
              onChange={update("linkedin_enabled", true)}
            />
            Enable LinkedIn workflow
          </label>
          <label>
            MCP server command
            <input
              value={form.mcp_server_command}
              onChange={update("mcp_server_command")}
              placeholder="python"
              autoComplete="off"
            />
          </label>
          <label>
            MCP server URL
            <input
              value={form.mcp_server_url}
              onChange={update("mcp_server_url")}
              placeholder="https://mcp.customer.com"
              autoComplete="off"
            />
          </label>
          <button className="btn primary" disabled={saving}>
            {saving ? "Running preflight..." : "Run Preflight & Register"}
          </button>
        </form>

        <section className="card ops-result" aria-live="polite">
          <h2>Preflight Result</h2>
          {!result && (
            <p className="muted">
              SPF and DMARC are checked before the tenant can enter active outreach.
            </p>
          )}
          {result && (
            <>
              <div className={`status-panel ${safe ? "safe" : "blocked"}`}>
                <span className="status-title">
                  {safe ? "ACTIVE" : "PENDING_REMEDIATION"}
                </span>
                <span className="muted small">{result.domain}</span>
              </div>
              {!safe && (
                <ul className="check-list">
                  {result.failure_reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              )}
              <dl className="ops-summary">
                <div>
                  <dt>Tenant ID</dt>
                  <dd>{result.tenant_id}</dd>
                </div>
                <div>
                  <dt>Budget</dt>
                  <dd>{money(variables.budget_limit)}</dd>
                </div>
                <div>
                  <dt>Meeting price</dt>
                  <dd>{money(variables.meeting_price)}</dd>
                </div>
                <div>
                  <dt>LinkedIn</dt>
                  <dd>{variables.linkedin_enabled ? "Enabled" : "Disabled"}</dd>
                </div>
              </dl>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
