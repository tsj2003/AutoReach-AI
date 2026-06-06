import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

/**
 * "Made for the way you work" — persona tab switcher with an animated
 * preview panel, mirroring the Wispr Flow segment.
 */
const PERSONAS = [
  {
    key: "Founders",
    headline: "Book meetings while you build",
    body: "Run outbound on autopilot. The engine drafts replies to interested prospects and slots calls straight onto your calendar.",
    metric: "12 hrs/wk",
    metricLabel: "saved on inbox triage",
  },
  {
    key: "Agencies",
    headline: "One dashboard, every client domain",
    body: "Isolate each client in its own workspace with dedicated mailboxes, warmup, and rotation. No cross-contamination, ever.",
    metric: "40+",
    metricLabel: "client domains protected",
  },
  {
    key: "Sales teams",
    headline: "Hit primary inbox, not promotions",
    body: "Dynamic ESP matching routes Gmail-to-Gmail and Outlook-to-Outlook so reps land where buyers actually read.",
    metric: "2.3x",
    metricLabel: "more positive replies",
  },
  {
    key: "Recruiters",
    headline: "Reach candidates at scale, personally",
    body: "Multi-step sequences with per-lead variables feel one-to-one. Out-of-office replies auto-reschedule to the return date.",
    metric: "100k+",
    metricLabel: "candidates per campaign",
  },
];

export default function Personas() {
  const [active, setActive] = useState(0);
  const p = PERSONAS[active];
  return (
    <div className="lp-personas">
      <div className="lp-persona-tabs">
        {PERSONAS.map((it, i) => (
          <button
            key={it.key}
            className={`lp-persona-tab ${i === active ? "on" : ""}`}
            onClick={() => setActive(i)}
          >
            {it.key}
          </button>
        ))}
      </div>

      <div className="lp-persona-stage">
        <AnimatePresence mode="wait">
          <motion.div
            key={p.key}
            className="lp-persona-card"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -18 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="lp-persona-copy">
              <h3>{p.headline}</h3>
              <p>{p.body}</p>
            </div>
            <div className="lp-persona-metric">
              <div className="lp-persona-metric-n">{p.metric}</div>
              <div className="lp-persona-metric-l">{p.metricLabel}</div>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
