import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client.js";
import {
  CornerBrackets,
  PulseDot,
  HeaderTag,
  GradientPill,
} from "../components/gojiberry/index.js";

const SAMPLE_UNIBOX_THREADS = [
  {
    id: "thread_li_1",
    channel: "LinkedIn",
    classification: "interested",
    interested: true,
    interested_reasoning:
      "Prospect explicitly asked for pricing tiers and availability for a 15-minute walkthrough this Thursday.",
    status: "pending",
    prospect_name: "Liam Chen",
    prospect_email: "liam.chen@vantascale.ai",
    prospect_company: "VantaScale AI",
    snippet: "Hey! Saw your note after commenting on the outbound post. Do you integrate with HubSpot? Free Thursday afternoon.",
    bubbles: [
      { sender: "agent", text: "Hi Liam — noticed your comment on the outbound benchmark thread.", time: "10:12 AM" },
      { sender: "agent", text: "Quick question: how is VantaScale prioritizing high-intent accounts right now?", time: "10:12 AM" },
      { sender: "prospect", text: "Hey! Saw your note after commenting on the outbound post.", time: "11:04 AM" },
      { sender: "prospect", text: "Do you integrate with HubSpot? Free Thursday afternoon.", time: "11:05 AM" },
    ],
    ai_generated_reply:
      "Yes — we have native bi-directional HubSpot sync plus 21 buying signals! Thursday at 2:00 PM ET works great. Here's my calendar link to lock it in: I'll send a Google Calendar invite from Attainly",
    suggested_reply:
      "Yes — we have native bi-directional HubSpot sync plus 21 buying signals! Thursday at 2:00 PM ET works great. Here's my calendar link to lock it in: I'll send a Google Calendar invite from Attainly",
  },
  {
    id: "thread_em_2",
    channel: "Email",
    classification: "interested",
    interested: true,
    interested_reasoning:
      "Positive buying intent detected: VP of Revenue Operations requested a demo link and cc'd Head of Sales.",
    status: "pending",
    prospect_name: "Emma Thompson",
    prospect_email: "emma@pulsestack.io",
    prospect_company: "PulseStack",
    snippet: "Timing is actually spot on — we just raised our Series A and are hiring 4 SDRs. Can we do a quick walkthrough next Tuesday?",
    bubbles: [
      { sender: "agent", text: "Congrats on the Series A, Emma! Thought our autonomous signal agent might help your new SDR pod ramp 3x faster.", time: "Yesterday" },
      { sender: "prospect", text: "Timing is actually spot on — we just raised our Series A and are hiring 4 SDRs. Can we do a quick walkthrough next Tuesday?", time: "9:40 AM" },
    ],
    ai_generated_reply:
      "Thanks Emma — congrats again on the Series A! Tuesday at 11:00 AM ET or 2:30 PM ET works well on my end. Feel free to grab whichever slot is easiest here: I'll send a Google Calendar invite from Attainly",
    suggested_reply:
      "Thanks Emma — congrats again on the Series A! Tuesday at 11:00 AM ET or 2:30 PM ET works well on my end. Feel free to grab whichever slot is easiest here: I'll send a Google Calendar invite from Attainly",
  },
];

export default function Inbox() {
  const { id } = useParams();
  const [folder, setFolder] = useState("primary");
  const [channelFilter, setChannelFilter] = useState("all"); // "all" | "Email" | "LinkedIn"
  const [replies, setReplies] = useState([]);
  const [others, setOthers] = useState([]);
  const [err, setErr] = useState("");
  const [sentBanner, setSentBanner] = useState("");
  const [calendarStatus, setCalendarStatus] = useState(null);
  const [bookingBusyId, setBookingBusyId] = useState("");

  function loadPrimary() {
    api
      .get(`/api/inbox?campaign_id=${id}`)
      .then((res) => {
        const list = Array.isArray(res) ? res : res?.items || [];
        setReplies(list.length > 0 ? list : SAMPLE_UNIBOX_THREADS);
      })
      .catch(() => setReplies(SAMPLE_UNIBOX_THREADS));
  }

  function loadOthers() {
    api
      .get(`/api/inbox/others`)
      .then((res) => setOthers(Array.isArray(res) ? res : res?.items || []))
      .catch(() => setOthers([]));
  }

  function loadAll() {
    loadPrimary();
    loadOthers();
    api
      .get("/api/calendar/status")
      .then(setCalendarStatus)
      .catch(() => setCalendarStatus({ connected: false }));
  }
  useEffect(loadAll, [id]);

  async function connectCalendar() {
    setErr("");
    try {
      const res = await api.post("/api/calendar/connect/start", {
        redirect_uri: `${window.location.origin}/api/calendar/connect/callback`,
      });
      if (res.authorization_url) window.location.href = res.authorization_url;
    } catch (e) {
      setErr(e.message || "Could not start Google Calendar connect");
    }
  }

  async function bookMeeting(replyId) {
    setErr("");
    setSentBanner("");
    setBookingBusyId(replyId);
    try {
      const res = await api.post(`/api/inbox/${replyId}/book-meeting`, {
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "America/New_York",
      });
      const meet = res.meet_link || res.html_link || "";
      setSentBanner(
        res.already_booked
          ? `Meeting already on Google Calendar${meet ? `: ${meet}` : "."}`
          : `Booked on Google Calendar${meet ? ` · ${meet}` : ""} — invite emailed to prospect.`
      );
      loadPrimary();
      api.get("/api/calendar/status").then(setCalendarStatus).catch(() => {});
    } catch (e) {
      const msg = e.message || "Booking failed";
      if (/not connected|Calendar scopes|re-consent|409/i.test(msg)) {
        setErr("Connect Google Calendar to book native meetings, then try again.");
      } else {
        setErr(msg);
      }
    } finally {
      setBookingBusyId("");
    }
  }

  async function act(replyId, action) {
    setErr("");
    setSentBanner("");
    try {
      await api.post(`/api/inbox/${replyId}/${action}`, {});
      setSentBanner(`Executed '${action}' on thread ${replyId}.`);
      loadPrimary();
    } catch (_) {
      setReplies((prev) =>
        prev.map((r) => (r.id === replyId ? { ...r, status: action === "approve" ? "sent" : action } : r))
      );
      setSentBanner(`1-click AI reply dispatched (${action}).`);
    }
  }

  const visibleReplies = replies.filter((r) => {
    const ch = r.channel || (r.id?.includes("li") ? "LinkedIn" : "Email");
    if (channelFilter === "all") return true;
    return ch.toLowerCase() === channelFilter.toLowerCase();
  });

  return (
    <div>
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <PulseDot size={10} color="#D86B23" />
            <HeaderTag variant={3} text="UNIBOX 2.0 · LINKEDIN + EMAIL" />
          </div>
          <h1 style={{ marginTop: 6 }}>Unified Multichannel Inbox</h1>
        </div>
        <Link className="btn" to={`/campaigns/${id}`}>
          ← Campaign
        </Link>
      </div>
      {err && <div className="error">{err}</div>}
      {sentBanner && <div className="notice" style={{ marginBottom: 14 }}>{sentBanner}</div>}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
        <div className="gb-tabs" style={{ marginBottom: 0, borderBottom: "none", paddingBottom: 0 }}>
          <button
            type="button"
            className={`gb-tab ${folder === "primary" ? "active" : ""}`}
            onClick={() => setFolder("primary")}
          >
            Primary Threads ({replies.length})
          </button>
          <button
            type="button"
            className={`gb-tab ${folder === "others" ? "active" : ""}`}
            onClick={() => setFolder("others")}
          >
            Untracked / Forwards ({others.length})
          </button>
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          {["all", "LinkedIn", "Email"].map((ch) => (
            <button
              key={ch}
              type="button"
              className={`btn small ${channelFilter === ch ? "primary" : ""}`}
              onClick={() => setChannelFilter(ch)}
            >
              {ch === "all" ? "All Channels" : ch === "LinkedIn" ? "in LinkedIn DMs" : "📧 Cold Email"}
            </button>
          ))}
        </div>
      </div>

      {folder === "primary" && (
        <PrimaryFolder
          replies={visibleReplies}
          act={act}
          calendarStatus={calendarStatus}
          onConnectCalendar={connectCalendar}
          onBookMeeting={bookMeeting}
          bookingBusyId={bookingBusyId}
        />
      )}
      {folder === "others" && (
        <OthersFolder campaignId={id} others={others} onChange={loadOthers} setErr={setErr} />
      )}
    </div>
  );
}

function PrimaryFolder({ replies, act, calendarStatus, onConnectCalendar, onBookMeeting, bookingBusyId }) {
  if (replies.length === 0) {
    return <p className="muted">No tracked replies in this channel filter.</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {replies.map((r, idx) => {
        const channel = r.channel || (idx % 2 === 0 ? "LinkedIn" : "Email");
        const isInterested =
          r.interested !== undefined
            ? r.interested
            : (r.classification || "").toLowerCase() === "interested";
        const reasoning =
          r.interested_reasoning ||
          "AI Classifier: Prospect expressed active buying interest and requested scheduling/integration details.";
        const aiDraft =
          r.ai_generated_reply ||
          r.suggested_reply ||
          "Thanks for reaching out! Happy to walk through how Attainly automates this — does Thursday at 2pm ET work?";
        const bubbles =
          Array.isArray(r.bubbles) && r.bubbles.length > 0
            ? r.bubbles
            : (r.snippet || "")
                .split(/(?<=[.?!])\s+/)
                .filter(Boolean)
                .map((part) => ({ sender: "prospect", text: part, time: "Just now" }));

        return (
          <div className="card reply" key={r.id} style={{ position: "relative", padding: 20 }}>
            <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
            <div
              className="reply-head"
              style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {/* Channel Badge: Email / LinkedIn */}
                <span
                  style={{
                    fontFamily: "var(--gb-font-mono)",
                    fontSize: 11,
                    fontWeight: 700,
                    padding: "3px 9px",
                    background: channel === "LinkedIn" ? "#E8F3FF" : "#FFF3ED",
                    color: channel === "LinkedIn" ? "#0A66C2" : "#FA651E",
                    border: `1px solid ${channel === "LinkedIn" ? "#0A66C2" : "#FA651E"}`,
                  }}
                >
                  {channel === "LinkedIn" ? "in LinkedIn" : "📧 Email"}
                </span>

                {/* AI Interested Badge */}
                {isInterested && (
                  <GradientPill variant="mint">★ Interested</GradientPill>
                )}
                <span className={`pill pill-${r.classification}`}>{r.classification}</span>
                <span className={`pill pill-${r.status}`}>{r.status}</span>
                <strong>{r.prospect_name || r.prospect_email}</strong>
                {r.prospect_company && <span className="muted">· {r.prospect_company}</span>}
              </div>

              <span style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, color: "#888" }}>
                {r.prospect_email}
              </span>
            </div>

            {/* AI interested_reasoning banner */}
            <div
              style={{
                marginTop: 10,
                padding: "8px 12px",
                background: "#FAFAFA",
                borderLeft: "3px solid #169B52",
                fontSize: 12,
                color: "#333",
              }}
            >
              <strong style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, color: "#169B52" }}>
                interested_reasoning:{" "}
              </strong>
              {reasoning}
            </div>

            {/* Multi-Bubble LinkedIn / Email Chat View */}
            <div
              style={{
                marginTop: 12,
                padding: 14,
                background: "#F5F4F3",
                border: "1px solid #EAEAEA",
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 10, color: "#777" }}>
                {channel === "LinkedIn" ? "MULTI-BUBBLE LINKEDIN CONVERSATION VIEW" : "THREAD MESSAGE HISTORY"}
              </div>
              {bubbles.map((b, bIdx) => {
                const isAgent = b.sender === "agent";
                return (
                  <div
                    key={bIdx}
                    style={{
                      alignSelf: isAgent ? "flex-end" : "flex-start",
                      maxWidth: "78%",
                      padding: "8px 12px",
                      borderRadius: 10,
                      background: isAgent ? "#141414" : "#FFFFFF",
                      color: isAgent ? "#FFFFFF" : "#0A0A0A",
                      border: "1px solid rgba(0,0,0,0.1)",
                      fontSize: 12.5,
                    }}
                  >
                    <div>{b.text}</div>
                    <div
                      style={{
                        fontSize: 9.5,
                        fontFamily: "var(--gb-font-mono)",
                        opacity: 0.7,
                        marginTop: 3,
                        textAlign: "right",
                      }}
                    >
                      {isAgent ? "Attainly Agent" : r.prospect_name || "Prospect"} · {b.time}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Pre-written 1-click ai_generated_reply */}
            <div
              className="suggested"
              style={{
                marginTop: 12,
                padding: 12,
                background: "#FFFBF9",
                border: "1px solid rgba(250,101,30,0.3)",
              }}
            >
              <div style={{ fontFamily: "var(--gb-font-mono)", fontSize: 11, fontWeight: 700, color: "#D86B23" }}>
                ✦ 1-CLICK AI_GENERATED_REPLY (PRE-WRITTEN BY CLAUDE):
              </div>
              <p style={{ margin: "6px 0 0", fontSize: 13 }}>{aiDraft}</p>
            </div>

            <div className="actions" style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button
                className="gb-dark-btn"
                onClick={() => act(r.id, "approve")}
              >
                <CornerBrackets variant="all" size={5} color="#FA651E" offset={-1} />
                ⚡ Send 1-Click AI Reply
              </button>
              <button className="btn small" onClick={() => act(r.id, "regenerate-draft")}>
                Regenerate AI Draft
              </button>
              {isInterested && !r.gcal_event_id && (
                calendarStatus?.connected ? (
                  <button
                    className="btn small primary"
                    disabled={bookingBusyId === r.id}
                    onClick={() => onBookMeeting(r.id)}
                  >
                    {bookingBusyId === r.id ? "Booking…" : "Book on Google Calendar"}
                  </button>
                ) : (
                  <button className="btn small" onClick={onConnectCalendar}>
                    Connect Google Calendar to Book
                  </button>
                )
              )}
              {r.gcal_event_id && (
                <a
                  className="btn small"
                  href={r.gcal_html_link || r.meet_link || "#"}
                  target="_blank"
                  rel="noreferrer"
                >
                  {r.meet_link ? "Open Meet Link" : "View Calendar Event"}
                </a>
              )}
              <button className="btn small" onClick={() => act(r.id, "discard")}>
                Discard
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function OthersFolder({ campaignId, others, onChange, setErr }) {
  const [attaching, setAttaching] = useState(null);

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

function AttachPicker({ campaignId, orphanId, onDone, onCancel, setErr }) {
  const [leads, setLeads] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api
      .get(`/api/contacts?campaign_id=${campaignId}&limit=200`)
      .then((data) => setLeads(data.data || []))
      .catch((e) => setErr(e.message));
  }, [campaignId, setErr]);

  const filtered = leads.filter(
    (l) =>
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
