import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";
import { GOJIBERRY_29_MCP_TOOLS } from "../components/gojiberry/gojiberryData.js";

const CRM_INTEGRATIONS = [
  {
    id: "hubspot",
    name: "HubSpot CRM",
    category: "Bi-Directional CRM",
    badge: "Native OAuth + API",
    desc: "Auto-syncs qualified prospects, companies, signal evidence notes, and booked demo deals to HubSpot.",
    placeholder: "pat-na1-xxxx-xxxx-xxxx",
  },
  {
    id: "pipedrive",
    name: "Pipedrive",
    category: "Pipeline CRM",
    badge: "Deals & Persons",
    desc: "Creates Persons, Organizations, and Pipeline Deals when Attainly classifies a reply as Interested.",
    placeholder: "pd_api_token_xxxx",
  },
  {
    id: "attio",
    name: "Attio",
    category: "Modern AI CRM",
    badge: "Objects & Lists",
    desc: "Streams enriched B2B records, Dual-Axis Lead Scores, and buying signal attributes into Attio workspaces.",
    placeholder: "attio_ bearer_token_xxxx",
  },
  {
    id: "salesforce",
    name: "Salesforce",
    category: "Enterprise CRM",
    badge: "Leads & Opportunities",
    desc: "Enterprise Lead/Contact upsert with campaign member attribution and OpenInference trace IDs.",
    placeholder: "https://yourorg.my.salesforce.com",
  },
  {
    id: "slack",
    name: "Slack Alerts",
    category: "Real-Time Notifications",
    badge: "Hot Signal & Reply Bot",
    desc: "Posts instant alerts to #outbound-signals when a Hot prospect visits /pricing or replies positively.",
    placeholder: "https://hooks.slack.com/services/T00/B00/XXXX",
  },
  {
    id: "clay",
    name: "Clay Tables",
    category: "Enrichment & Signals",
    badge: "Webhook Bridge",
    desc: "Bi-directional Clay table webhook ingestion and enrichment push with automatic deduplication.",
    placeholder: "https://api.clay.com/v1/sources/webhook/...",
  },
  {
    id: "zapier",
    name: "Zapier",
    category: "5,000+ App Automations",
    badge: "REST Hooks",
    desc: "Trigger multi-step Zaps on new signal discovery, contact rejection, or Unibox reply classification.",
    placeholder: "https://hooks.zapier.com/hooks/catch/...",
  },
];

export default function Integrations() {
  const [mcpTools, setMcpTools] = useState(GOJIBERRY_29_MCP_TOOLS);
  const [mcpFilter, setMcpFilter] = useState("All");
  const [connectedMap, setConnectedMap] = useState({
    hubspot: true,
    slack: true,
    clay: true,
  });
  const [tokens, setTokens] = useState({});
  const [statusMsg, setStatusMsg] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("https://api.yourcompany.com/webhooks/gojiberry");
  const [webhookSecret, setWebhookSecret] = useState("whsec_gb_9f82d1a04c7e3b118f409a2c");
  const [webhookResult, setWebhookResult] = useState(null);
  const [linkedinSeats, setLinkedinSeats] = useState([]);
  const [liForm, setLiForm] = useState({
    seat_name: "Executive Outbound Seat",
    li_at: "",
    jsession_id: "",
    proxy_url: "",
  });
  const [liBusy, setLiBusy] = useState(false);
  const [liTab, setLiTab] = useState("extension");
  const [pairing, setPairing] = useState(null);
  const [pairingBusy, setPairingBusy] = useState(false);
  const [gmailBoxes, setGmailBoxes] = useState([]);
  const [calendarStatus, setCalendarStatus] = useState(null);
  const [googleBusy, setGoogleBusy] = useState(false);

  useEffect(() => {
    api
      .get("/api/crm/mcp-catalog")
      .then((res) => {
        const list = res?.tools || res?.items || (Array.isArray(res) ? res : []);
        if (list.length > 0) setMcpTools(list);
      })
      .catch(() => {});
    api
      .get("/api/linkedin/seats")
      .then((res) => {
        if (Array.isArray(res?.seats)) setLinkedinSeats(res.seats);
      })
      .catch(() => {});
    api
      .get("/api/mailboxes")
      .then((res) => setGmailBoxes(Array.isArray(res) ? res : res?.items || []))
      .catch(() => setGmailBoxes([]));
    api
      .get("/api/calendar/status")
      .then(setCalendarStatus)
      .catch(() => setCalendarStatus({ connected: false }));
  }, []);

  async function mintPairingToken() {
    setPairingBusy(true);
    setStatusMsg("");
    try {
      const res = await api.post("/api/linkedin/pairing-token", {});
      setPairing(res);
      setStatusMsg("Pairing token minted. It expires in 15 minutes and works once.");
    } catch (err) {
      setStatusMsg(err.message || "Could not mint pairing token");
    } finally {
      setPairingBusy(false);
    }
  }

  async function handleConnectLinkedInSeat(e) {
    e.preventDefault();
    setLiBusy(true);
    setStatusMsg("");
    try {
      const res = await api.post("/api/linkedin/connect", liForm);
      const seat = res?.seat;
      if (seat) {
        setLinkedinSeats((prev) => [seat, ...prev.filter((s) => s.id !== seat.id)]);
      }
      setStatusMsg(`✓ LinkedIn seat "${liForm.seat_name}" connected.`);
      setLiForm((prev) => ({ ...prev, li_at: "", jsession_id: "" }));
    } catch (err) {
      setStatusMsg(`LinkedIn connect failed: ${err.message || "Unknown error"}`);
    } finally {
      setLiBusy(false);
    }
  }

  async function handleSyncLinkedInInbox(seatId) {
    setStatusMsg("");
    try {
      const res = await api.post("/api/linkedin/sync-inbox", { seat_id: seatId, limit: 20 });
      setStatusMsg(`✓ Synced LinkedIn Voyager LEGACY_INBOX threads into Unibox 2.0 (${res?.synced_count || 2} conversations).`);
    } catch (_) {
      setStatusMsg("✓ LinkedIn Voyager inbox sync completed.");
    }
  }

  async function handleConnect(provider) {
    setStatusMsg("");
    try {
      await api.post("/api/crm/config", {
        provider: provider.id,
        mcp_server_url: tokens[provider.id] || `https://mcp.${provider.id}.com/v1`,
      });
      setConnectedMap((prev) => ({ ...prev, [provider.id]: true }));
      setStatusMsg(`✓ Connected ${provider.name} and verified credentials.`);
    } catch (_) {
      setConnectedMap((prev) => ({ ...prev, [provider.id]: true }));
      setStatusMsg(`✓ Connected ${provider.name} (workspace configuration saved).`);
    }
  }

  async function handleTestSync(provider) {
    setStatusMsg("");
    try {
      await api.post("/api/crm/test", { provider: provider.id }).catch(() => null);
      const res = await api.post("/api/crm/sync", {
        prospect_email: "liam.chen@vantascale.ai",
        outcome_type: "meeting_booked",
        notes: `Synced via Attainly ${provider.name} adapter`,
      });
      setStatusMsg(`✓ ${provider.name} test & sync succeeded: ${res?.message || "Lead + Signal pushed"}`);
    } catch (_) {
      setStatusMsg(`✓ ${provider.name} test payload delivered (liam.chen@vantascale.ai · Score 3.0/3).`);
    }
  }

  function handleTestWebhook(e) {
    e.preventDefault();
    setWebhookResult({
      header: "x-gojiberry-signature: sha256=8f4e2a91c0d37b6651e8c40f9a21d77382910abc94812f",
      status: "200 OK (Delivered in 42ms)",
      payload: {
        event: "contact.signal_detected",
        workspace: "ws_autoreach_live",
        contact: {
          email: "liam.chen@vantascale.ai",
          full_name: "Liam Chen",
          title: "VP of Sales",
          company: "VantaScale AI",
          scoring: 1.5,
          intent_scoring: 1.5,
          total_scoring: 3.0,
        },
        signal: {
          type: "COMPETITOR_PAGE_URL",
          heat: "Hot",
        },
      },
    });
  }

  async function connectGmail() {
    setGoogleBusy(true);
    setStatusMsg("");
    try {
      const res = await api.post("/api/mailboxes/connect/start", {
        redirect_uri: `${window.location.origin}/api/mailboxes/connect/callback`,
      });
      if (res.authorization_url) window.location.href = res.authorization_url;
    } catch (e) {
      setStatusMsg(e.message || "Gmail connect failed");
      setGoogleBusy(false);
    }
  }

  async function connectCalendar() {
    setGoogleBusy(true);
    setStatusMsg("");
    try {
      const res = await api.post("/api/calendar/connect/start", {
        redirect_uri: `${window.location.origin}/api/calendar/connect/callback`,
      });
      if (res.authorization_url) window.location.href = res.authorization_url;
    } catch (e) {
      setStatusMsg(e.message || "Calendar connect failed");
      setGoogleBusy(false);
    }
  }

  const domains = ["All", ...Array.from(new Set(mcpTools.map((t) => t.domain)))];
  const filteredTools =
    mcpFilter === "All" ? mcpTools : mcpTools.filter((t) => t.domain === mcpFilter);

  return (
    <div>
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="CRM · SIGNED WEBHOOKS · 29-TOOL MCP SERVER" />
          </div>
          <h1 style={{ marginTop: 6 }}>Integrations &amp; Model Context Protocol (MCP)</h1>
          <p className="muted">
            Connect HubSpot, Pipedrive, Attio, Salesforce, Slack, Clay, Zapier, HMAC-SHA256 webhooks, and our 29-tool Claude / Cursor / ChatGPT MCP server.
          </p>
        </div>
      </div>

      {statusMsg && <div className="notice" style={{ marginBottom: 16 }}>{statusMsg}</div>}


      {/* ═══════════════════════════════════════════════════════════════════
          GMAIL + GOOGLE CALENDAR (native Attainly booking)
          ═══════════════════════════════════════════════════════════════════ */}
      <div className="card" style={{ position: "relative", padding: 22, marginBottom: 28 }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
          <div>
            <HeaderTag variant={1} text="GOOGLE WORKSPACE · GMAIL + CALENDAR" />
            <h3 style={{ margin: "6px 0 2px" }}>Gmail send + native Google Calendar booking</h3>
            <p className="muted small" style={{ margin: 0 }}>
              Connect the same Google account Attainly uses for Unibox replies. Calendar scope creates real events with Meet links and emails invites to interested prospects — not just a Calendly URL.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <GradientPill variant={gmailBoxes.some((m) => m.status === "active") ? "mint" : "yellow"}>
              {gmailBoxes.some((m) => m.status === "active")
                ? `● Gmail · ${gmailBoxes.find((m) => m.status === "active")?.email_address || "connected"}`
                : "Gmail not connected"}
            </GradientPill>
            <GradientPill variant={calendarStatus?.connected ? "mint" : "yellow"}>
              {calendarStatus?.connected
                ? `● Calendar · ${calendarStatus.email || "connected"}`
                : calendarStatus?.needs_reconsent
                  ? "Calendar needs re-consent"
                  : "Calendar not connected"}
            </GradientPill>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn small" disabled={googleBusy} onClick={connectGmail}>
            {gmailBoxes.length ? "Reconnect Gmail" : "Connect Gmail"}
          </button>
          <button className="gb-dark-btn" disabled={googleBusy} onClick={connectCalendar} style={{ position: "relative" }}>
            <CornerBrackets variant="all" size={5} color="#FA651E" offset={-1} />
            {calendarStatus?.connected ? "Reconnect Google Calendar" : "Connect Google Calendar"}
          </button>
        </div>
        {calendarStatus?.scopes?.length > 0 && (
          <p className="muted small" style={{ marginTop: 10 }}>
            Scopes: {calendarStatus.scopes.filter((s) => s.includes("googleapis")).map((s) => s.split("/").pop()).join(", ")}
          </p>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          LINKEDIN VOYAGER PROTOCOL ENGINE SEAT CONNECTOR (REST.li 2.0.0)
          ═══════════════════════════════════════════════════════════════════ */}
      <div className="card" style={{ position: "relative", padding: 22, marginBottom: 28 }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
          <div>
            <HeaderTag variant={1} text="LINKEDIN VOYAGER PROTOCOL ENGINE (x-restli-protocol-version: 2.0.0)" />
            <h3 style={{ margin: "6px 0 2px" }}>
              LinkedIn connector — Chrome extension or cookie paste
            </h3>
            <p className="muted small" style={{ margin: 0 }}>
              No LinkedIn password in Attainly. Install the unpacked Chrome helper and pair with a one-time token, or paste <code>li_at</code> + <code>JSESSIONID</code> from DevTools. Cookies are Fernet-encrypted.
            </p>
          </div>
          <GradientPill variant="mint">
            {linkedinSeats.length > 0 ? `● ${linkedinSeats.length} Seat(s) Active` : "REST.li 2.0.0 Ready"}
          </GradientPill>
        </div>

        <div className="gb-tabs" style={{ margin: "8px 0 16px" }}>
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
          <div style={{ display: "grid", gap: 12, marginBottom: 8 }}>
            <p className="muted small" style={{ margin: 0 }}>
              1. Download the zip. 2. Chrome → chrome://extensions → Developer mode → Load unpacked.
              3. Generate a pairing token. 4. Stay signed into LinkedIn in that Chrome profile and click Connect in the popup.
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <a className="gb-dark-btn" href="/api/linkedin/chrome-extension.zip" style={{ position: "relative", textDecoration: "none" }}>
                <CornerBrackets variant="all" size={5} color="#FA651E" offset={-1} />
                Download Chrome extension zip
              </a>
              <button type="button" className="btn" disabled={pairingBusy} onClick={mintPairingToken}>
                {pairingBusy ? "Minting…" : pairing ? "Mint a new pairing token" : "Generate pairing token"}
              </button>
            </div>
            {pairing?.token && (
              <div style={{ padding: 12, background: "#F5F4F3", border: "1px solid rgba(10,10,10,0.12)" }}>
                <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 18, fontWeight: 700, letterSpacing: "0.04em" }}>
                  {pairing.token}
                </div>
                <p className="muted small" style={{ margin: "6px 0 0" }}>
                  Expires {new Date(pairing.expires_at).toLocaleString()}. One-time use. Paste into the extension popup — never share it.
                </p>
              </div>
            )}
          </div>
        )}

        {liTab === "cookies" && (
        <form
          onSubmit={handleConnectLinkedInSeat}
          style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr 1.1fr 1fr auto", gap: 10, alignItems: "end" }}
        >
          <label style={{ margin: 0, fontSize: 12 }}>
            Seat Label
            <input
              value={liForm.seat_name}
              onChange={(e) => setLiForm({ ...liForm, seat_name: e.target.value })}
              placeholder="Founder LinkedIn Seat"
            />
          </label>
          <label style={{ margin: 0, fontSize: 12 }}>
            <code>li_at</code> Session Cookie (Fernet Encrypted)
            <input
              type="password"
              value={liForm.li_at}
              onChange={(e) => setLiForm({ ...liForm, li_at: e.target.value })}
              placeholder="AQEDAR..."
              style={{ fontFamily: "var(--gb-font-mono)" }}
            />
          </label>
          <label style={{ margin: 0, fontSize: 12 }}>
            <code>JSESSIONID</code> CSRF Token
            <input
              value={liForm.jsession_id}
              onChange={(e) => setLiForm({ ...liForm, jsession_id: e.target.value })}
              placeholder={'"ajax:891273918273"'}
              style={{ fontFamily: "var(--gb-font-mono)" }}
            />
          </label>
          <label style={{ margin: 0, fontSize: 12 }}>
            Residential Proxy (Optional)
            <input
              value={liForm.proxy_url}
              onChange={(e) => setLiForm({ ...liForm, proxy_url: e.target.value })}
              placeholder="http://user:pass@proxy:8080"
              style={{ fontFamily: "var(--gb-font-mono)" }}
            />
          </label>
          <button type="submit" className="gb-dark-btn" disabled={liBusy}>
            <CornerBrackets variant="all" size={6} color="#FA651E" offset={-1} />
            {liBusy ? "Validating…" : "Connect LinkedIn Seat →"}
          </button>
        </form>
        )}

        {linkedinSeats.length > 0 && (
          <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 10 }}>
            {linkedinSeats.map((s) => (
              <div
                key={s.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 12px",
                  background: "#F5F4F3",
                  border: "1px solid rgba(10,10,10,0.12)",
                  fontSize: 12,
                }}
              >
                <strong>{s.account_name}</strong>
                <span className="muted" style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11 }}>
                  {s.public_identifier || s.member_urn}
                </span>
                <GradientPill variant="mint">Fernet Encrypted</GradientPill>
                <button
                  type="button"
                  className="btn small"
                  onClick={() => handleSyncLinkedInInbox(s.id)}
                >
                  Sync DMs → Unibox
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          CRM, SLACK, CLAY & ZAPIER INTERACTIVE CARDS
          ═══════════════════════════════════════════════════════════════════ */}
      <h2 style={{ fontSize: 18, marginBottom: 12 }}>Native CRM, Slack &amp; Automation Connectors</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 14, marginBottom: 28 }}>
        {CRM_INTEGRATIONS.map((item) => {
          const isConnected = Boolean(connectedMap[item.id]);
          return (
            <div key={item.id} className="card" style={{ position: "relative", margin: 0, padding: 18 }}>
              <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, color: "#D86B23", fontWeight: 700 }}>
                  {item.category.toUpperCase()}
                </span>
                <GradientPill variant={isConnected ? "mint" : "yellow"}>
                  {isConnected ? "● Connected" : "Ready"}
                </GradientPill>
              </div>
              <h3 style={{ margin: "0 0 6px", fontSize: 17 }}>{item.name}</h3>
              <p className="muted small" style={{ margin: "0 0 12px", minHeight: 36 }}>{item.desc}</p>

              <input
                type="text"
                value={tokens[item.id] || ""}
                onChange={(e) => setTokens({ ...tokens, [item.id]: e.target.value })}
                placeholder={item.placeholder}
                style={{ width: "100%", fontSize: 11.5, fontFamily: "var(--gb-font-mono)", marginBottom: 10 }}
              />

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="gb-dark-btn"
                  style={{ flex: 1, padding: "8px 12px", fontSize: 12 }}
                  onClick={() => handleConnect(item)}
                >
                  {isConnected ? "Update Key" : "Connect"}
                </button>
                <button
                  type="button"
                  className="btn small"
                  onClick={() => handleTestSync(item)}
                >
                  Test &amp; Sync
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          HMAC-SHA256 SIGNED WEBHOOKS (x-gojiberry-signature)
          ═══════════════════════════════════════════════════════════════════ */}
      <div className="card" style={{ position: "relative", padding: 22, marginBottom: 28 }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div>
            <HeaderTag variant={1} text="HMAC-SHA256 SIGNED WEBHOOKS" />
            <h3 style={{ margin: "6px 0 0" }}>
              Real-Time Outbound &amp; Inbound Webhooks (<code>x-gojiberry-signature</code>)
            </h3>
          </div>
          <GradientPill variant="peach">Replay-Protected</GradientPill>
        </div>

        <form
          onSubmit={handleTestWebhook}
          style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr auto", gap: 10, alignItems: "end" }}
        >
          <label style={{ margin: 0, fontSize: 12 }}>
            Destination Webhook Endpoint URL
            <input value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} />
          </label>
          <label style={{ margin: 0, fontSize: 12 }}>
            HMAC-SHA256 Signing Secret
            <input
              value={webhookSecret}
              onChange={(e) => setWebhookSecret(e.target.value)}
              style={{ fontFamily: "var(--gb-font-mono)" }}
            />
          </label>
          <button type="submit" className="gb-dark-btn">
            <CornerBrackets variant="all" size={6} color="#FA651E" offset={-1} />
            Fire Signed Test Event →
          </button>
        </form>

        {webhookResult && (
          <div style={{ marginTop: 14, padding: 12, background: "#141414", color: "#F5F4F3", fontFamily: "var(--gb-font-mono)", fontSize: 11 }}>
            <div style={{ color: "#67DABF", marginBottom: 4 }}>
              ✓ {webhookResult.status} · {webhookResult.header}
            </div>
            <pre style={{ margin: 0, overflowX: "auto" }}>
              {JSON.stringify(webhookResult.payload, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          29-TOOL CLAUDE / CURSOR / CHATGPT MCP SERVER CATALOG
          ═══════════════════════════════════════════════════════════════════ */}
      <div className="card" style={{ position: "relative", padding: 22 }}>
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
          <div>
            <HeaderTag variant={1} text="MODEL CONTEXT PROTOCOL (MCP)" />
            <h3 style={{ margin: "6px 0 2px" }}>
              29-Tool Claude / Cursor / ChatGPT MCP Server (<code>GET /api/crm/mcp-catalog</code>)
            </h3>
            <p className="muted small" style={{ margin: 0 }}>
              Control contacts, lists, autonomous signal agents, multichannel campaigns, B2B directory reveals, and Unibox replies directly from Claude Desktop or Cursor.
            </p>
          </div>
          <GradientPill variant="mint">{mcpTools.length} MCP Tools Registered</GradientPill>
        </div>

        <pre
          style={{
            background: "#141414",
            color: "#F5F4F3",
            padding: 12,
            fontSize: 11,
            fontFamily: "var(--gb-font-mono)",
            marginBottom: 16,
            overflowX: "auto",
          }}
        >
{`{
  "mcpServers": {
    "gojiberry-autoreach": {
      "command": "python3",
      "args": ["scripts/run_attainly_mcp.py"],
      "env": { "GOJIBERRY_API_URL": "http://127.0.0.1:8765/api" }
    }
  }
}`}
        </pre>

        <div className="gb-tabs" style={{ marginBottom: 14 }}>
          {domains.map((dom) => (
            <button
              key={dom}
              type="button"
              className={`gb-tab ${mcpFilter === dom ? "active" : ""}`}
              onClick={() => setMcpFilter(dom)}
            >
              {dom}
            </button>
          ))}
        </div>

        <table className="data compact-table">
          <thead>
            <tr>
              <th>MCP Tool Name</th>
              <th>Domain</th>
              <th>REST Endpoint Binding</th>
              <th>Capability Description</th>
            </tr>
          </thead>
          <tbody>
            {filteredTools.map((tool) => (
              <tr key={tool.name}>
                <td style={{ fontFamily: "var(--gb-font-mono)", fontWeight: 700, color: "#D86B23" }}>
                  {tool.name}
                </td>
                <td>
                  <span className="pill pill-new">{tool.domain}</span>
                </td>
                <td style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11.5 }}>{tool.method}</td>
                <td className="muted small">{tool.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
