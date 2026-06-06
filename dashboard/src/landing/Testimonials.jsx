import { motion } from "framer-motion";

/**
 * Two marquee rows of testimonial cards drifting in opposite directions —
 * the Wispr Flow "Flow love" wall.
 */
const QUOTES = [
  ["AutoReach paid for itself in the first week. We stopped buying burner domains entirely.", "Maya R.", "Founder, B2B SaaS"],
  ["The reply categorization is witchcraft. I wake up to booked calls, not a full inbox.", "Devin K.", "Head of Growth"],
  ["Finally an outbound tool that treats deliverability like infrastructure.", "Priya S.", "Agency Owner"],
  ["Out-of-office auto-reschedule alone saved my SDRs hours a week.", "Tom B.", "Sales Manager"],
  ["We run 40 client domains from one dashboard. Nothing leaks across workspaces.", "Lena M.", "Cold Email Agency"],
  ["Switched from three tools to AutoReach. Inbox placement jumped overnight.", "Arjun V.", "Demand Gen Lead"],
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
        {loop.map(([q, name, role], i) => (
          <div key={i} className="lp-tm-card">
            <p className="lp-tm-quote">“{q}”</p>
            <div className="lp-tm-who">
              <span className="lp-tm-name">{name}</span>
              <span className="lp-tm-role">{role}</span>
            </div>
          </div>
        ))}
      </motion.div>
    </div>
  );
}

export default function Testimonials() {
  return (
    <div className="lp-tm">
      <Row items={QUOTES.slice(0, 3)} duration={34} />
      <Row items={QUOTES.slice(3)} duration={40} reverse />
    </div>
  );
}
