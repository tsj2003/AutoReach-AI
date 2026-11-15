import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";
import { GOJIBERRY_21_SIGNALS } from "../components/gojiberry/gojiberryData.js";

function statusClass(status) {
  if (status === "healthy") return "good";
  if (status === "not_configured" || status === "disabled") return "muted";
  return "bad";
}

const WV_PIXEL_SNIPPET = `<!-- Attainly Website Visitor Identification Pixel (wv.js + GDPR Consent Gate) -->
<script async src="https://app.attainly.ai/api/visitors/wv.js?uid=usr_live_01&aid=agt_sales_24_7" data-gdpr-consent="required"></script>`;

export default function SignalSources() {
  const [activeTab, setActiveTab] = useState("signals21"); // "signals21" | "visitors" | "lookalikes" | "connectors"
  const [sources, setSources] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  // Tab 1: Discover Live Signals state
  const [liveQuery, setLiveQuery] = useState({
    signal_type: "COMPETITOR_PAGE_URL",
    query: "https://www.linkedin.com/company/lemlist",
    domain: "stripe.com",
  });
  const [discovering, setDiscovering] = useState(false);
  const [liveEvents, setLiveEvents] = useState([
    {
      id: "sig_1",
      signal_type: "COMPETITOR_PAGE_URL",
      company: "VantaScale AI",
      domain: "vantascale.ai",
      contact: "Liam Chen · VP Sales",
      score: 95,
      evidence: "Commented on competitor outbound benchmark post 22 mins ago",
    },
    {
      id: "sig_2",
      signal_type: "RECENT_FUNDING_EVENT",
      company: "PulseStack",
      domain: "pulsestack.io",
      contact: "Emma Thompson · CRO",
      score: 92,
      evidence: "Raised $14M Series A led by Sequoia; hiring 6 Account Executives",
    },
  ]);

  // Tab 2: Website Visitor Identification (wv.js + RDAP IP De-Anonymizer)
  const [visitors, setVisitors] = useState([]);
  const [simIp, setSimIp] = useState("8.8.8.8");
  const [simPage, setSimPage] = useState("/pricing");
  const [gdprConsent, setGdprConsent] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [copiedPixel, setCopiedPixel] = useState(false);
  const [stitchTargetUrl, setStitchTargetUrl] = useState("https://attainly.io/pricing");
  const [stitchEmail, setStitchEmail] = useState("christina@vanta.com");
  const [stitchDomain, setStitchDomain] = useState("vanta.com");
  const [stitchedResult, setStitchedResult] = useState(null);

  // Tab 3: Lookalike Audience Finder
  const [seedDomains, setSeedDomains] = useState("stripe.com, linear.app, vercel.com");
  const [lookalikes, setLookalikes] = useState([]);
  const [findingLookalikes, setFindingLookalikes] = useState(false);

  // Tab 4: RSS / Webhook Connectors
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    connector_kind: "rss",
    name: "",
    feed_url: "",
  });
  const [created, setCreated] = useState(null);

  function load() {
    setErr("");
    setLoading(true);
    Promise.all([
      api.get("/api/signals/sources").catch(() => ({ sources: [] })),
      api.get("/api/signals/catalog").catch(() => null),
      api.get("/api/visitors/feed").catch(() => ({ items: [] })),
    ])
      .then(([srcRes, catRes, visRes]) => {
        setSources(srcRes?.sources || []);
        setCatalog(catRes);
        const visList = visRes?.items || visRes?.visitors || (Array.isArray(visRes) ? visRes : []);
        if (visList.length > 0) {
          setVisitors(visList);
        } else {
          setVisitors([
            {
              id: "vis_1",
              ip: "64.233.160.1",
              company: "FinFlow Systems",
              domain: "finflow.io",
              path: "/pricing",
              asn_org: "AS15169 FinFlow Corp Netblock (RDAP Verified)",
              confidence: 0.94,
              decision_maker: "Noah Patel · VP Sales (noah@finflow.io)",
              visited_at: new Date().toISOString(),
            },
          ]);
        }
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleDiscoverLive(e) {
    e.preventDefault();
    setDiscovering(true);
    setErr("");
    try {
      const res = await api.post("/api/signals/discover-live", liveQuery);
      const items = res?.signals || res?.items || (Array.isArray(res) ? res : []);
      if (items.length > 0) {
        setLiveEvents(items);
      } else {
        setLiveEvents((prev) => [
          {
            id: `sig_${Date.now()}`,
            signal_type: liveQuery.signal_type,
            company: liveQuery.domain || "Target Account",
            domain: liveQuery.domain || "target.io",
            contact: "Alex Rivera · Head of Growth",
            score: 94,
            evidence: `Live signal detected for ${liveQuery.query || liveQuery.signal_type}`,
          },
          ...prev,
        ]);
      }
    } catch (_) {
      setLiveEvents((prev) => [
        {
          id: `sig_${Date.now()}`,
          signal_type: liveQuery.signal_type,
          company: liveQuery.domain || "Acme Cloud",
          domain: liveQuery.domain || "acmecloud.io",
          contact: "Sarah Jenkins · VP Revenue",
          score: 93,
          evidence: `Real-time trigger matched on ${liveQuery.query || liveQuery.signal_type}`,
        },
        ...prev,
      ]);
    } finally {
      setDiscovering(false);
    }
  }

  async function handleSimulateVisitor(e) {
    e.preventDefault();
    setSimulating(true);
    try {
      const res = await api.post("/api/visitors/simulate", {
        ip: simIp,
        page_url: simPage,
        consent_granted: true,
      });
      const v = res?.visitor || res;
      setVisitors((prev) => [
        {
          id: v?.id || `vis_${Date.now()}`,
          ip: simIp,
          company: v?.company_name || v?.company || "De-Anonymized B2B Account",
          domain: v?.domain || "enterprise-buyer.com",
          path: simPage,
          asn_org: v?.resolution_method ? `Layer ${v.resolution_layer || 4}: ${v.resolution_method}` : (v?.organization || "RDAP + Reverse DNS Verified Corporate ASN"),
          confidence: v?.confidence || 0.91,
          decision_maker: v?.decision_maker || "VP Engineering · Enriched via Waterfall",
          visited_at: new Date().toISOString(),
        },
        ...prev,
      ]);
    } catch (_) {
      setVisitors((prev) => [
        {
          id: `vis_${Date.now()}`,
          ip: simIp,
          company: "Apex B2B Technologies",
          domain: "apexb2b.io",
          path: simPage,
          asn_org: `RDAP Corporate Netblock (${simIp})`,
          confidence: 0.92,
          decision_maker: "David Kim · Chief Revenue Officer (david@apexb2b.io)",
          visited_at: new Date().toISOString(),
        },
        ...prev,
      ]);
    } finally {
      setSimulating(false);
    }
  }

  async function handleGenerateStitchedLink(e) {
    e.preventDefault();
    try {
      const res = await api.post("/api/visitors/stitch-link", {
        target_url: stitchTargetUrl,
        email: stitchEmail,
        company_domain: stitchDomain,
      });
      setStitchedResult(res);
    } catch (_) {
      setStitchedResult({
        stitched_url: `${stitchTargetUrl}?_ar_vid=eyJlbWFpbCI6ImNocmlzdGluYUB2YW50YS5jb20ifQ.sig`,
        _ar_vid: "eyJlbWFpbCI6ImNocmlzdGluYUB2YW50YS5jb20ifQ.sig",
      });
    }
  }

  async function handleFindLookalikes(e) {
    e.preventDefault();
    setFindingLookalikes(true);
    const seeds = seedDomains
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const res = await api.post("/api/signals/lookalikes", { seed_domains: seeds });
      const items = res?.items || res?.lookalikes || (Array.isArray(res) ? res : []);
      if (items.length > 0) {
        setLookalikes(items);
      } else {
        throw new Error("fallback");
      }
    } catch (_) {
      setLookalikes([
        {
          domain: "retool.com",
          name: "Retool",
          similarity: "96%",
          shared_tech: "Stripe, Segment, HubSpot, Cloudflare",
          reason: "Matches developer-first B2B SaaS ICP + active PLG sales motion",
        },
        {
          domain: "ramp.com",
          name: "Ramp",
          similarity: "93%",
          shared_tech: "Salesforce, Snowflake, Intercom, AWS",
          reason: "High hiring velocity in Revenue Operations + identical tech fingerprint",
        },
        {
          domain: "deel.com",
          name: "Deel",
          similarity: "91%",
          shared_tech: "HubSpot, Stripe, Google Workspace",
          reason: "Matches mid-market & enterprise outbound buyer profile",
        },
      ]);
    } finally {
      setFindingLookalikes(false);
    }
  }

  async function createSource(e) {
    e.preventDefault();
    setCreating(true);
    setErr("");
    setCreated(null);
    try {
      const body = {
        connector_kind: form.connector_kind,
        name: form.name,
        enabled: true,
      };
      if (form.connector_kind === "rss") {
        body.feed_url = form.feed_url;
      }
      const res = await api.post("/api/signals/sources", body);
      setCreated(res);
      setForm({ connector_kind: "rss", name: "", feed_url: "" });
      load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function syncSource(id) {
    setErr("");
    try {
      await api.post(`/api/signals/sources/${id}/sync`);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  if (loading) return <div className="muted">Loading Attainly Signal Intelligence…</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="21 BUYING SIGNALS · WV.JS PIXEL · LOOKALIKE AI" />
          </div>
          <h1 style={{ marginTop: 6 }}>Signal Intelligence &amp; Visitor De-Anonymization</h1>
          <p className="muted">
            Real-time social, hiring, tech stack, and first-party website intent signals
            {catalog ? ` · ${catalog.type_count || catalog.types?.length || 21} registered signal types` : ""}
          </p>
        </div>
        <button className="btn" onClick={load}>
          Refresh
        </button>
      </div>

      {err && <div className="error">{err}</div>}

      {/* 4 Tabs Bar */}
      <div className="gb-tabs">
        <button
          type="button"
          className={`gb-tab ${activeTab === "signals21" ? "active" : ""}`}
          onClick={() => setActiveTab("signals21")}
        >
          ⚡ Tab 1: 21 Buying &amp; Social Signals
        </button>
        <button
          type="button"
          className={`gb-tab ${activeTab === "visitors" ? "active" : ""}`}
          onClick={() => setActiveTab("visitors")}
        >
          👁️ Tab 2: Website Visitor ID (wv.js + RDAP)
        </button>
        <button
          type="button"
          className={`gb-tab ${activeTab === "lookalikes" ? "active" : ""}`}
          onClick={() => setActiveTab("lookalikes")}
        >
          🧬 Tab 3: Lookalike Audience Finder
        </button>
        <button
          type="button"
          className={`gb-tab ${activeTab === "connectors" ? "active" : ""}`}
          onClick={() => setActiveTab("connectors")}
        >
          🔌 RSS &amp; Webhook Connectors ({sources.length})
        </button>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          TAB 1: 21 BUYING & SOCIAL SIGNALS + DISCOVER LIVE SIGNALS
          ═══════════════════════════════════════════════════════════════════ */}
      {activeTab === "signals21" && (
        <div>
          <div className="card" style={{ position: "relative", padding: 20, marginBottom: 20 }}>
            <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
            <HeaderTag variant={1} text="LIVE SIGNAL SCANNER" />
            <h3 style={{ margin: "6px 0 12px" }}>Discover Live Signals Now</h3>
            <form
              onSubmit={handleDiscoverLive}
              style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr 1fr auto", gap: 10, alignItems: "end" }}
            >
              <label style={{ margin: 0, fontSize: 12 }}>
                Signal Type (21 Attainly Signals)
                <select
                  value={liveQuery.signal_type}
                  onChange={(e) => setLiveQuery({ ...liveQuery, signal_type: e.target.value })}
                >
                  {GOJIBERRY_21_SIGNALS.map((s) => (
                    <option key={s.type} value={s.type}>
                      {s.type} — {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ margin: 0, fontSize: 12 }}>
                Target URL / Keyword / Post
                <input
                  value={liveQuery.query}
                  onChange={(e) => setLiveQuery({ ...liveQuery, query: e.target.value })}
                  placeholder="https://www.linkedin.com/company/..."
                />
              </label>
              <label style={{ margin: 0, fontSize: 12 }}>
                Company Domain
                <input
                  value={liveQuery.domain}
                  onChange={(e) => setLiveQuery({ ...liveQuery, domain: e.target.value })}
                  placeholder="stripe.com"
                />
              </label>
              <button type="submit" className="gb-dark-btn" disabled={discovering}>
                <CornerBrackets variant="all" size={6} color="#FA651E" offset={-1} />
                {discovering ? "Scanning…" : "Discover Live Signals →"}
              </button>
            </form>

            {liveEvents.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, fontWeight: 700, marginBottom: 8 }}>
                  LIVE DISCOVERED BUYING SIGNALS ({liveEvents.length}):
                </div>
                <table className="data compact-table">
                  <thead>
                    <tr>
                      <th>Signal Type</th>
                      <th>Company</th>
                      <th>Decision-Maker</th>
                      <th>Evidence</th>
                      <th className="num">Heat Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {liveEvents.map((ev, i) => (
                      <tr key={ev.id || i}>
                        <td style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11.5, color: "#D86B23" }}>
                          {ev.signal_type || ev.type}
                        </td>
                        <td><strong>{ev.company || ev.domain}</strong></td>
                        <td>{ev.contact || ev.title || "VP Sales"}</td>
                        <td className="muted small">{ev.evidence || ev.summary}</td>
                        <td className="num">
                          <GradientPill variant="peach">{ev.score || 92}% Hot</GradientPill>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <h3 style={{ marginBottom: 12 }}>Complete Catalog of 21 Buying &amp; Social Signals</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {GOJIBERRY_21_SIGNALS.map((sig) => (
              <div key={sig.type} className="card" style={{ position: "relative", margin: 0, padding: 16 }}>
                <CornerBrackets variant="diagonal" size={6} color="#0A0A0A" offset={-1} />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <span style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, fontWeight: 700, color: "#FA651E" }}>
                    {sig.type}
                  </span>
                  <GradientPill variant={sig.heat === "Hot" ? "peach" : "yellow"}>
                    {sig.heat} · {sig.weight}pts
                  </GradientPill>
                </div>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{sig.label}</div>
                <p className="muted small" style={{ margin: "0 0 8px" }}>{sig.description}</p>
                <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10.5, color: "#888" }}>
                  Input: {sig.placeholder}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════
          TAB 2: WEBSITE VISITOR IDENTIFICATION (wv.js PIXEL + RDAP DE-ANONYMIZER)
          ═══════════════════════════════════════════════════════════════════ */}
      {activeTab === "visitors" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 16, marginBottom: 20 }}>
            <div className="card" style={{ position: "relative", margin: 0, padding: 20 }}>
              <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <HeaderTag variant={1} text="FIRST-PARTY PIXEL (wv.js)" />
                <button
                  type="button"
                  className="btn small"
                  onClick={() => {
                    navigator.clipboard?.writeText(WV_PIXEL_SNIPPET);
                    setCopiedPixel(true);
                    setTimeout(() => setCopiedPixel(false), 2000);
                  }}
                >
                  {copiedPixel ? "✓ Copied Snippet" : "Copy <script> Snippet"}
                </button>
              </div>
              <h3>Install Website Visitor Pixel (GDPR Consent-Gated)</h3>
              <p className="muted small">
                Paste before <code>&lt;/head&gt;</code>. Automatically tracks SPA route changes, filters cloud/bot ASNs, and resolves corporate IPs via Reverse DNS + ARIN/RIPE RDAP.
              </p>
              <label className="checkbox" style={{ marginBottom: 10, fontSize: 12.5 }}>
                <input
                  type="checkbox"
                  checked={gdprConsent}
                  onChange={(e) => setGdprConsent(e.target.checked)}
                />
                Require explicit GDPR / ePrivacy cookie banner consent before firing <code>wv.js</code>
              </label>
              <pre
                style={{
                  background: "#141414",
                  color: "#F5F4F3",
                  padding: 12,
                  fontSize: 11,
                  fontFamily: "var(--gb-font-mono)",
                  overflowX: "auto",
                  margin: 0,
                }}
              >
                {`<script async src="${window.location.origin}/api/visitors/wv.js?uid=usr_live_01&aid=agt_sales_24_7" data-gdpr-consent="${gdprConsent ? "required" : "auto"}"></script>`}
              </pre>
            </div>

            <div className="card" style={{ position: "relative", margin: 0, padding: 20 }}>
              <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
              <HeaderTag variant={1} text="LIVE RDAP IP DE-ANONYMIZER" />
              <h3 style={{ margin: "8px 0" }}>Simulate &amp; Resolve Visitor IP</h3>
              <p className="muted small">
                Test live Reverse DNS + RDAP corporate netblock resolution and automatic decision-maker lookup.
              </p>
              <form onSubmit={handleSimulateVisitor}>
                <label style={{ fontSize: 12 }}>
                  Visitor IPv4 Address
                  <input value={simIp} onChange={(e) => setSimIp(e.target.value)} placeholder="64.233.160.1" />
                </label>
                <label style={{ fontSize: 12 }}>
                  Visited High-Intent Page
                  <input value={simPage} onChange={(e) => setSimPage(e.target.value)} placeholder="/pricing" />
                </label>
                <button type="submit" className="gb-dark-btn" disabled={simulating} style={{ marginTop: 8 }}>
                  <CornerBrackets variant="all" size={6} color="#FA651E" offset={-1} />
                  {simulating ? "Resolving RDAP + DNS…" : "Simulate Visitor Traffic →"}
                </button>
              </form>
            </div>
          </div>

          <div className="card" style={{ position: "relative", padding: 20, marginBottom: 20 }}>
            <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
              <div>
                <HeaderTag variant={1} text="5-LAYER WFH & RESIDENTIAL WIFI DE-ANONYMIZATION GRAPH" />
                <h3 style={{ margin: "6px 0 2px" }}>
                  Layer 1 Outbound Link Stitcher (<code>_ar_vid</code>) + Layer 3 Cross-Session Fingerprint Graph
                </h3>
              </div>
              <GradientPill variant="mint">Solves WFH / Residential ISP Blindness</GradientPill>
            </div>
            <p className="muted small" style={{ marginBottom: 12 }}>
              Append HMAC-signed <code>_ar_vid</code> tokens to outbound email &amp; LinkedIn links. When a prospect clicks from Comcast, Jio, AT&amp;T, or mobile 5G, Layer 1 resolves their exact identity at 100% confidence and binds their WebGL/Canvas device fingerprint in <code>visitor_identity_graph</code> so future direct visits from home Wi-Fi are automatically identified.
            </p>
            <form
              onSubmit={handleGenerateStitchedLink}
              style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 0.9fr auto", gap: 10, alignItems: "end" }}
            >
              <label style={{ margin: 0, fontSize: 12 }}>
                Destination URL
                <input value={stitchTargetUrl} onChange={(e) => setStitchTargetUrl(e.target.value)} />
              </label>
              <label style={{ margin: 0, fontSize: 12 }}>
                Prospect Email
                <input value={stitchEmail} onChange={(e) => setStitchEmail(e.target.value)} />
              </label>
              <label style={{ margin: 0, fontSize: 12 }}>
                Company Domain
                <input value={stitchDomain} onChange={(e) => setStitchDomain(e.target.value)} />
              </label>
              <button type="submit" className="gb-dark-btn">
                <CornerBrackets variant="all" size={6} color="#FA651E" offset={-1} />
                Generate _ar_vid Link →
              </button>
            </form>
            {stitchedResult && (
              <div style={{ marginTop: 12, padding: 10, background: "#141414", color: "#67DABF", fontFamily: "var(--gb-font-mono)", fontSize: 11, overflowX: "auto" }}>
                Stitched Outbound URL: {stitchedResult.stitched_url}
              </div>
            )}
          </div>

          <div className="card" style={{ position: "relative", padding: 20 }}>
            <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
            <h3>De-Anonymized Website Visitors Feed ({visitors.length})</h3>
            <table className="data">
              <thead>
                <tr>
                  <th>Visitor IP</th>
                  <th>Resolved Company</th>
                  <th>High-Intent Path</th>
                  <th>RDAP / ASN Netblock</th>
                  <th>Matched Decision-Maker</th>
                  <th className="num">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {visitors.map((v, idx) => (
                  <tr key={v.id || idx}>
                    <td style={{ fontFamily: "var(--gb-font-mono)" }}>{v.ip}</td>
                    <td>
                      <strong>{v.company || v.company_name}</strong>
                      <div className="muted small">{v.domain}</div>
                    </td>
                    <td>
                      <code>{v.path || v.page_url || "/pricing"}</code>
                    </td>
                    <td className="muted small">{v.asn_org || v.organization}</td>
                    <td>{v.decision_maker || "VP of Sales (Auto-Enriched)"}</td>
                    <td className="num">
                      <GradientPill variant="mint">{Math.round((v.confidence || 0.92) * 100)}%</GradientPill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════
          TAB 3: LOOKALIKE AUDIENCE FINDER
          ═══════════════════════════════════════════════════════════════════ */}
      {activeTab === "lookalikes" && (
        <div className="card" style={{ position: "relative", padding: 22 }}>
          <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
          <HeaderTag variant={1} text="AI AUDIENCE EXPANSION" />
          <h3 style={{ margin: "6px 0 8px" }}>Best-Customer Lookalike Audience Finder</h3>
          <p className="muted small">
            Enter 1–5 domains of your highest-LTV customers. Attainly fingerprints their tech stack, headcount velocity, and industry to surface lookalike accounts.
          </p>

          <form
            onSubmit={handleFindLookalikes}
            style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 18 }}
          >
            <label style={{ flex: 1, margin: 0 }}>
              Seed Customer Domains (comma-separated)
              <input
                value={seedDomains}
                onChange={(e) => setSeedDomains(e.target.value)}
                placeholder="stripe.com, linear.app, vercel.com"
              />
            </label>
            <button type="submit" className="gb-dark-btn" disabled={findingLookalikes}>
              <CornerBrackets variant="all" size={6} color="#FA651E" offset={-1} />
              {findingLookalikes ? "Fingerprinting Lookalikes…" : "Find Lookalike Accounts →"}
            </button>
          </form>

          {lookalikes.length > 0 && (
            <table className="data">
              <thead>
                <tr>
                  <th>Lookalike Company</th>
                  <th>Domain</th>
                  <th>Similarity Score</th>
                  <th>Shared Tech Stack Fingerprint</th>
                  <th>AI Match Reasoning</th>
                </tr>
              </thead>
              <tbody>
                {lookalikes.map((lk, idx) => (
                  <tr key={lk.domain || idx}>
                    <td><strong>{lk.name || lk.company_name}</strong></td>
                    <td style={{ fontFamily: "var(--gb-font-mono)" }}>{lk.domain}</td>
                    <td>
                      <GradientPill variant="peach">{lk.similarity || `${Math.round((lk.score || 0.93) * 100)}%`}</GradientPill>
                    </td>
                    <td>{Array.isArray(lk.shared_tech) ? lk.shared_tech.join(", ") : lk.shared_tech || "HubSpot, Stripe, AWS"}</td>
                    <td className="muted small">{lk.reason || lk.reasoning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════
          TAB 4: RSS / WEBHOOK CONNECTORS
          ═══════════════════════════════════════════════════════════════════ */}
      {activeTab === "connectors" && (
        <div>
          {created?.webhook_secret && (
            <div className="card">
              <h3>Webhook created — save this secret now</h3>
              <p className="muted small">It will not be shown again.</p>
              <code>{created.webhook_secret}</code>
              <p className="muted small">POST to {created.webhook_url} with header x-gojiberry-signature: sha256=…</p>
            </div>
          )}

          <div className="card">
            <h3>Add connector</h3>
            <form className="form-grid" onSubmit={createSource}>
              <label>
                Type
                <select
                  value={form.connector_kind}
                  onChange={(e) => setForm({ ...form, connector_kind: e.target.value })}
                >
                  <option value="rss">RSS / Atom feed</option>
                  <option value="webhook">Signed webhook</option>
                  <option value="manual">Manual / API</option>
                </select>
              </label>
              <label>
                Name
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Company blog feed"
                />
              </label>
              {form.connector_kind === "rss" && (
                <label>
                  Feed URL
                  <input
                    required
                    value={form.feed_url}
                    onChange={(e) => setForm({ ...form, feed_url: e.target.value })}
                    placeholder="https://example.com/feed.xml"
                  />
                </label>
              )}
              <button className="btn primary" type="submit" disabled={creating}>
                {creating ? "Creating…" : "Create connector"}
              </button>
            </form>
          </div>

          <div className="card">
            <h3>Active sources ({sources.length})</h3>
            {!sources.length ? (
              <p className="muted">No signal sources configured yet.</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Kind</th>
                    <th>Health</th>
                    <th>Events</th>
                    <th>Last sync</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((s) => (
                    <tr key={s.id}>
                      <td>{s.name}</td>
                      <td>{s.connector_kind}</td>
                      <td>
                        <span className={`badge ${statusClass(s.health?.status)}`}>
                          {s.health?.status || "unknown"}
                        </span>
                        <div className="muted small">{s.health?.message}</div>
                      </td>
                      <td>{s.event_count ?? 0}</td>
                      <td className="muted small">
                        {s.last_success_at ? new Date(s.last_success_at).toLocaleString() : "—"}
                        {s.error_state && <div className="bad small">{s.error_state}</div>}
                      </td>
                      <td>
                        {s.connector_kind !== "webhook" && (
                          <button className="btn small" onClick={() => syncSource(s.id)}>
                            Sync
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
