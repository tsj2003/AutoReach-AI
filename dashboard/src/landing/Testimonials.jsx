import { motion } from "framer-motion";

/**
 * Honest pre-launch value wall.
 *
 * We have no customers yet, so we do NOT show fabricated testimonials (that
 * would be an FTC violation and would torch trust). Instead we surface real,
 * verifiable product capabilities as a drifting card wall in the same visual
 * style. Swap this for genuine quotes once we have consenting users.
 */
const VALUE_CARDS = [
  ["No burner-domain tax", "Connect unlimited Gmail & Outlook mailboxes on a flat plan — no per-inbox fees."],
  ["Replies read & acted on", "Seven AI categories: Interested, Objection, OOO, Referral, Not-interested, Do-not-contact, Auto."],
  ["Deliverability as infrastructure", "Dynamic ESP matching routes Gmail-to-Gmail and Outlook-to-Outlook for primary-inbox placement."],
  ["Auto-rotation on health drops", "When a mailbox's bounce rate spikes, we pause it and rotate in a warmed reserve automatically."],
  ["OOO that reschedules itself", "Out-of-office replies are parsed for the return date and the follow-up is moved accordingly."],
  ["Built for 100k+ leads", "Cursor pagination keeps the dashboard fast whether you're on page 1 or page 1,000."],
];

function Row({ items, duration, reverse }) {
  const loop = [...items, ...items];
  return (
    <div className="lp-tm-row">
      <motion.div
        className="lp-tm-track"
        animate={{ x: reverse ? ["-50%", "0%"] : ["0%", "-50%"] }}
        transition={{ duration, ease: "linear", repeat: Infinity }}
      >
        {loop.map(([title, body], i) => (
          <div key={i} className="lp-tm-card">
            <p className="lp-tm-vtitle">{title}</p>
            <p className="lp-tm-quote">{body}</p>
          </div>
        ))}
      </motion.div>
    </div>
  );
}

export default function Testimonials() {
  return (
    <div className="lp-tm">
      <Row items={VALUE_CARDS.slice(0, 3)} duration={34} />
      <Row items={VALUE_CARDS.slice(3)} duration={40} reverse />
    </div>
  );
}
