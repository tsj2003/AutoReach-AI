import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";

const ACCESS_DENIED_TESTER_HINT =
  "Google blocked this Gmail account because Attainly's OAuth app is still in Testing. A Google Cloud project owner must add your address as a Test user (OAuth consent screen → Test users), then retry Connect Gmail. Publishing the app for production verification is a later step — testers can connect today.";

function oauthErrorMessage(code) {
  if (code === "access_denied") return ACCESS_DENIED_TESTER_HINT;
  if (code === "invalid_or_expired_state") {
    return "Gmail connect expired. Click Connect Gmail again and complete Google consent in the same browser.";
  }
  if (code === "missing_client_secret") {
    return "Google client secret is not configured on the server. Set GOOGLE_CLIENT_SECRET, then retry Connect Gmail.";
  }
  if (code === "redirect_uri_mismatch") {
    return "Google redirect URI does not match this deployment. Retry Connect Gmail from this same Attainly URL.";
  }
  if (code === "scope_mismatch" || code === "token_exchange_failed") {
    return "Google token exchange failed. Retry Connect Gmail. If it keeps failing, the OAuth app may still be in Testing.";
  }
  return `Google OAuth failed (${code}). Try Connect Gmail again.`;
}

export default function Mailboxes() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [connectUrl, setConnectUrl] = useState("");

  function load() {
    api.get("/api/mailboxes").then(setRows).catch((e) => setErr(e.message));
  }

  useEffect(() => {
    const oauthError = searchParams.get("error") || searchParams.get("oauth_error");
    const connected = searchParams.get("connected");
    const warning = searchParams.get("warning");
    const next = new URLSearchParams(searchParams);
    if (oauthError) {
      setErr(oauthErrorMessage(oauthError));
      next.delete("error");
      next.delete("oauth_error");
    } else {
      setErr("");
    }
    if (connected === "1") {
      setNotice(
        warning === "missing_refresh_token"
          ? "Gmail connected, but Google did not return a refresh token. Connect Gmail once more and accept every permission."
          : "Gmail connected. Approve one test email on your campaign."
      );
      next.delete("connected");
      next.delete("warning");
    }
    if (oauthError || connected === "1") {
      setSearchParams(next, { replace: true });
    }
    load();
    // Read oauth_error once on mount; load() is stable for this page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startConnect() {
    setBusy(true);
    setErr("");
    try {
      const res = await api.post("/api/mailboxes/connect/start", {
        redirect_uri: `${window.location.origin}/api/mailboxes/connect/callback`,
      });
      const url = res.authorization_url || res.auth_url;
      if (url) {
        setConnectUrl(url);
        window.location.href = url;
      }
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function pauseOrResume(id, action) {
    setBusy(true);
    try {
      await api.post(`/api/mailboxes/${id}/${action}`, {});
      load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="GMAIL · SEND + CALENDAR SCOPES" />
          </div>
          <h1 style={{ marginTop: 6 }}>Mailboxes</h1>
          <p className="muted">
            Connect Gmail here — login with Google is not enough. Do not Pause before reconnecting.
          </p>
        </div>
        <div className="actions">
          <Link className="btn" to="/operations">← Operations</Link>
          <button className="gb-dark-btn" disabled={busy} onClick={startConnect} style={{ position: "relative" }}>
            <CornerBrackets variant="all" size={5} color="#FA651E" offset={-1} />
            {rows.some((m) => !m.has_refresh_token) ? "Reconnect Gmail" : "Connect Gmail"}
          </button>
        </div>
      </div>
      {err && <div className="error">{err}</div>}
      {notice && <div className="notice">{notice}</div>}
      {rows.some((m) => !m.has_refresh_token || m.status !== "active") && (
        <div className="error">
          This mailbox cannot send yet. Reconnect Gmail and leave it Active, then Approve once.
        </div>
      )}
      {connectUrl && <p className="muted small">Redirecting to Google OAuth…</p>}

      <div className="card" style={{ position: "relative", padding: 0, overflow: "hidden" }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <table className="data">
          <thead>
            <tr><th>Email</th><th>Provider</th><th>Status</th><th>Sent today</th><th>Send ready</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td>{m.email_address}</td>
                <td>{m.provider}</td>
                <td>
                  <GradientPill variant={m.status === "active" ? "mint" : "yellow"}>
                    {m.status}
                  </GradientPill>
                </td>
                <td>{m.emails_sent_today ?? 0} / {m.max_emails_per_day ?? "—"}</td>
                <td>
                  {m.has_refresh_token && m.status === "active"
                    ? "Yes"
                    : m.last_error || "Reconnect Gmail"}
                </td>
                <td>
                  {m.status === "paused" && (
                    <button className="btn small" disabled={busy} onClick={() => pauseOrResume(m.id, "resume")}>Resume</button>
                  )}
                  {m.status === "active" && (
                    <button className="btn small" disabled={busy} onClick={() => pauseOrResume(m.id, "pause")}>Pause</button>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan="6" className="muted">No mailboxes connected yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
