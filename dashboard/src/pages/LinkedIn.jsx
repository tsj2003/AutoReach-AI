import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";

/**
 * Gojiberry-style LinkedIn seat: Voyager session (extension or cookie paste).
 * This is what enables visit / like / comment / connection request / DM.
 */
export default function LinkedIn() {
  const [seats, setSeats] = useState([]);
  const [liTab, setLiTab] = useState("extension");
  const [pairing, setPairing] = useState(null);
  const [pairingBusy, setPairingBusy] = useState(false);
  const [liBusy, setLiBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [liForm, setLiForm] = useState({
    seat_name: "Founder LinkedIn",
    li_at: "",
    jsession_id: "",
    proxy_url: "",
  });

  function loadSeats() {
    api
      .get("/api/linkedin/seats")
      .then((res) => setSeats(Array.isArray(res?.seats) ? res.seats : []))
      .catch((e) => setErr(e.message));
  }

  useEffect(loadSeats, []);

  async function mintPairingToken() {
    setPairingBusy(true);
    setErr("");
    setMsg("");
    try {
      const res = await api.post("/api/linkedin/pairing-token", {});
      setPairing(res);
      setMsg("Pairing token ready — expires in 15 minutes, one-time use.");
    } catch (e) {
      setErr(e.message || "Could not mint pairing token");
    } finally {
      setPairingBusy(false);
    }
  }

  async function connectCookies(e) {
    e.preventDefault();
    setLiBusy(true);
    setErr("");
    setMsg("");
    try {
      const res = await api.post("/api/linkedin/connect", liForm);
      if (!res?.ok && !res?.seat) {
        throw new Error(res?.detail || "Connect failed");
      }
      if (res?.seat) {
        setSeats((prev) => [res.seat, ...prev.filter((s) => s.id !== res.seat.id)]);
      } else {
        loadSeats();
      }
      setMsg(`LinkedIn seat connected${res?.seat?.account_name ? `: ${res.seat.account_name}` : ""}.`);
      setLiForm((f) => ({ ...f, li_at: "", jsession_id: "" }));
    } catch (e) {
      setErr(e.message || "LinkedIn connect failed");
    } finally {
      setLiBusy(false);
    }
  }

  async function disconnectSeat(seatId) {
    if (!window.confirm("Disconnect this LinkedIn seat? Sequence LinkedIn steps will fall back to email.")) {
      return;
    }
    setErr("");
    try {
      await api.del(`/api/linkedin/seats/${seatId}`);
      setSeats((prev) => prev.filter((s) => s.id !== seatId));
      setMsg("LinkedIn seat disconnected.");
    } catch (e) {
      setErr(e.message);
    }
  }

  async function syncInbox(seatId) {
    setErr("");
    setMsg("");
    try {
      const res = await api.post("/api/linkedin/sync-inbox", { seat_id: seatId, limit: 20 });
      setMsg(`Synced ${res?.synced_count ?? 0} LinkedIn conversation(s) into Inbox.`);
    } catch (e) {
      setErr(e.message || "Inbox sync failed");
    }
  }

  const liveSeats = seats.filter((s) => s.can_auto_message || s.has_cookie || s.auth_method === "legacy_cookie");

  return (
    <div>
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#0A66C2" />
            <HeaderTag variant={3} text="LINKEDIN SEAT · VOYAGER" />
          </div>
          <h1 style={{ marginTop: 6 }}>LinkedIn</h1>
          <p className="muted">
            Connect a LinkedIn seat so campaigns can visit profiles, like/comment on posts,
            send connection requests, and DMs — same multichannel model as Gojiberry.
            We never collect your LinkedIn password.
          </p>
        </div>
        <GradientPill variant={liveSeats.length ? "mint" : "yellow"}>
          {liveSeats.length ? `${liveSeats.length} seat ready` : "No seat"}
        </GradientPill>
      </div>

      {msg && <div className="notice">{msg}</div>}
      {err && <div className="error">{err}</div>}

      <div className="card" style={{ position: "relative", marginBottom: 18 }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <HeaderTag variant={1} text="CONNECT SEAT" />
        <p className="muted small" style={{ marginTop: 8 }}>
          Chrome extension (recommended) or paste <code>li_at</code> + <code>JSESSIONID</code> from
          DevTools. Cookies are encrypted at rest.
        </p>

        <div className="gb-tabs" style={{ margin: "12px 0 16px" }}>
          <button
            type="button"
            className={`gb-tab ${liTab === "extension" ? "active" : ""}`}
            onClick={() => setLiTab("extension")}
          >
            Chrome extension
          </button>
          <button
            type="button"
            className={`gb-tab ${liTab === "cookies" ? "active" : ""}`}
            onClick={() => setLiTab("cookies")}
          >
            Cookie paste
          </button>
        </div>

        {liTab === "extension" && (
          <div style={{ display: "grid", gap: 12 }}>
            <ol className="muted small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.6 }}>
              <li>Download the extension zip and unzip it.</li>
              <li>
                Chrome → <code>chrome://extensions</code> → Developer mode → Load unpacked →{" "}
                <code>attainly-linkedin-helper</code>.
              </li>
              <li>Generate a pairing token below.</li>
              <li>Stay signed into LinkedIn → open the popup → Connect.</li>
            </ol>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <a
                className="gb-dark-btn"
                href="/api/linkedin/chrome-extension.zip"
                style={{ textDecoration: "none" }}
              >
                Download Chrome extension
              </a>
              <button type="button" className="btn" disabled={pairingBusy} onClick={mintPairingToken}>
                {pairingBusy ? "Minting…" : pairing ? "Mint new token" : "Generate pairing token"}
              </button>
            </div>
            {pairing?.token && (
              <div style={{ padding: 12, background: "#F5F4F3", border: "1px solid #EAEAEA" }}>
                <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 18, fontWeight: 700 }}>
                  {pairing.token}
                </div>
                <p className="muted small" style={{ margin: "6px 0 0" }}>
                  Expires {pairing.expires_at ? new Date(pairing.expires_at).toLocaleString() : "soon"}.
                  One-time. Never share it.
                </p>
              </div>
            )}
          </div>
        )}

        {liTab === "cookies" && (
          <form onSubmit={connectCookies} className="form" style={{ display: "grid", gap: 10 }}>
            <label>
              Seat label
              <input
                value={liForm.seat_name}
                onChange={(e) => setLiForm({ ...liForm, seat_name: e.target.value })}
                required
              />
            </label>
            <label>
              <code>li_at</code> cookie
              <input
                type="password"
                value={liForm.li_at}
                onChange={(e) => setLiForm({ ...liForm, li_at: e.target.value })}
                placeholder="AQEDAR…"
                required
                style={{ fontFamily: "var(--gb-font-mono)" }}
              />
            </label>
            <label>
              <code>JSESSIONID</code>
              <input
                value={liForm.jsession_id}
                onChange={(e) => setLiForm({ ...liForm, jsession_id: e.target.value })}
                placeholder={'"ajax:…"'}
                style={{ fontFamily: "var(--gb-font-mono)" }}
              />
            </label>
            <label>
              Proxy URL (optional)
              <input
                value={liForm.proxy_url}
                onChange={(e) => setLiForm({ ...liForm, proxy_url: e.target.value })}
                placeholder="http://user:pass@proxy:8080"
                style={{ fontFamily: "var(--gb-font-mono)" }}
              />
            </label>
            <button type="submit" className="btn primary" disabled={liBusy}>
              {liBusy ? "Validating…" : "Connect LinkedIn seat"}
            </button>
          </form>
        )}
      </div>

      <div className="card" style={{ position: "relative" }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <HeaderTag variant={1} text="CONNECTED SEATS" />
        {seats.length === 0 ? (
          <p className="muted" style={{ marginTop: 10 }}>
            No seat yet — LinkedIn sequence steps will fall back to email until you connect.{" "}
            <Link to="/campaigns">Campaigns</Link>
          </p>
        ) : (
          <table className="data" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Account</th>
                <th>Automation</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {seats.map((s) => {
                const canAuto = Boolean(s.can_auto_message || s.has_cookie);
                return (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.account_name}</strong>
                      <div className="muted small" style={{ fontFamily: "var(--gb-font-mono)" }}>
                        {s.public_identifier || s.email || s.id}
                      </div>
                    </td>
                    <td>
                      <GradientPill variant={canAuto ? "mint" : "yellow"}>
                        {canAuto ? "Visit · Like · Comment · Invite · DM" : "Identity only"}
                      </GradientPill>
                    </td>
                    <td>
                      <span className={`pill pill-${s.status}`}>{s.status}</span>
                    </td>
                    <td style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      {canAuto && (
                        <button type="button" className="btn small" onClick={() => syncInbox(s.id)}>
                          Sync DMs
                        </button>
                      )}
                      <button type="button" className="btn small" onClick={() => disconnectSeat(s.id)}>
                        Disconnect
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
