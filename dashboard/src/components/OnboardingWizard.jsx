import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api/client.js";

/**
 * First-run onboarding, inspired by GetResponse's "What are your goals?" modal.
 *
 * Step 1 — pick a goal (pre-fills a sensible starter campaign).
 * Step 2 — confirm the offer + ICP (editable).
 * Step 3 — we create the campaign through the real /api/campaigns endpoint and
 *          hand control back to the dashboard.
 *
 * "Skip for now" lets people explore an empty dashboard without being trapped.
 */
const GOALS = [
  {
    key: "book_meetings",
    icon: "📅",
    title: "Book sales meetings",
    desc: "Cold outreach that lands calls on the calendar.",
    offer: "A 20-minute intro call to show how we can help your team.",
    icp: "Founders and revenue leaders at B2B software companies, 10–200 employees.",
  },
  {
    key: "fill_pipeline",
    icon: "📈",
    title: "Fill my pipeline",
    desc: "High-volume prospecting across many inboxes.",
    offer: "A short walkthrough of how we drive qualified pipeline on autopilot.",
    icp: "Heads of Growth and Demand Gen at mid-market B2B companies.",
  },
  {
    key: "recruit",
    icon: "🧲",
    title: "Reach candidates",
    desc: "Personalized recruiting outreach at scale.",
    offer: "A quick chat about a role that fits your background.",
    icp: "Senior engineers and product managers open to new opportunities.",
  },
  {
    key: "agency",
    icon: "🏢",
    title: "Run client campaigns",
    desc: "Manage outbound for multiple clients safely.",
    offer: "A demo of how we protect deliverability for every client domain.",
    icp: "Agency owners and SDR leaders running outbound for clients.",
  },
];

export default function OnboardingWizard({ onComplete, onSkip }) {
  const [step, setStep] = useState(0);
  const [goal, setGoal] = useState(null);
  const [name, setName] = useState("");
  const [offer, setOffer] = useState("");
  const [icp, setIcp] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function pickGoal(g) {
    setGoal(g);
    setName(`${g.title} campaign`);
    setOffer(g.offer);
    setIcp(g.icp);
    setStep(1);
  }

  async function createCampaign() {
    setErr("");
    setBusy(true);
    try {
      const created = await api.post("/api/campaigns", {
        customer_name: name.trim() || "My first campaign",
        offer: offer.trim(),
        icp_description: icp.trim(),
        monthly_meeting_target: 10,
      });
      onComplete?.(created);
    } catch (e) {
      setErr(e.message || "Could not create the campaign");
      setBusy(false);
    }
  }

  return (
    <div className="ob-overlay">
      <motion.div
        className="ob-modal"
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="ob-progress">
          {[0, 1].map((s) => (
            <span key={s} className={`ob-pip ${step >= s ? "on" : ""}`} />
          ))}
        </div>

        <AnimatePresence mode="wait">
          {step === 0 && (
            <motion.div
              key="goal"
              initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}
              transition={{ duration: 0.25 }}
            >
              <h2 className="ob-title">What do you want to achieve?</h2>
              <p className="ob-sub">We'll set up a starter campaign tuned for your goal. You can change everything later.</p>
              <div className="ob-goals">
                {GOALS.map((g) => (
                  <button key={g.key} className="ob-goal" onClick={() => pickGoal(g)}>
                    <span className="ob-goal-icon">{g.icon}</span>
                    <span className="ob-goal-title">{g.title}</span>
                    <span className="ob-goal-desc">{g.desc}</span>
                  </button>
                ))}
              </div>
              <button className="ob-skip" onClick={onSkip}>Skip for now</button>
            </motion.div>
          )}

          {step === 1 && (
            <motion.div
              key="confirm"
              initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}
              transition={{ duration: 0.25 }}
            >
              <h2 className="ob-title">{goal?.icon} Let's tune your campaign</h2>
              <p className="ob-sub">These are starting points — edit anything that doesn't fit.</p>

              {err && <div className="auth-error">{err}</div>}

              <label className="auth-label">
                Campaign name
                <input value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="auth-label">
                Your offer
                <textarea value={offer} onChange={(e) => setOffer(e.target.value)} rows={2} />
              </label>
              <label className="auth-label">
                Who you're targeting (ICP)
                <textarea value={icp} onChange={(e) => setIcp(e.target.value)} rows={2} />
              </label>

              <div className="ob-actions">
                <button className="btn" onClick={() => setStep(0)} disabled={busy}>Back</button>
                <button className="btn primary" onClick={createCampaign} disabled={busy}>
                  {busy ? "Creating…" : "Create my campaign →"}
                </button>
              </div>
              <button className="ob-skip" onClick={onSkip} disabled={busy}>Skip for now</button>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
