import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

// A live, looping demo of the AI reply-categorization engine.
// Replies stream in and get "classified" with an animated tag + action.
const STREAM = [
  { from: "alex@northwind.com", text: "This looks great — send me some times for a call.", cat: "interested", action: "📅 Calendar link drafted & sent" },
  { from: "priya@vertexlabs.io", text: "I'm out of office until July 15.", cat: "out_of_office", action: "⏸ Follow-up rescheduled to Jul 15" },
  { from: "sam@cobalt.dev", text: "Talk to our CTO — mark@cobalt.dev", cat: "referral", action: "🔗 New lead created from referral" },
  { from: "casey@stratus.com", text: "Remove me from your list.", cat: "do_not_contact", action: "🚫 Unsubscribed + blocklisted" },
  { from: "morgan@lumen.io", text: "How's this different from Smartlead?", cat: "objection", action: "✍️ Objection-handler drafted for review" },
  { from: "noah@halcyon.app", text: "Not a fit right now, thanks.", cat: "not_interested", action: "🛑 Sequence stopped" },
];

const CAT_LABEL = {
  interested: "Interested",
  out_of_office: "Out of office",
  referral: "Referral",
  do_not_contact: "Do not contact",
  objection: "Objection",
  not_interested: "Not interested",
};

export default function InboxDemo() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((x) => (x + 1) % STREAM.length), 2600);
    return () => clearInterval(t);
  }, []);
  const item = STREAM[i];

  return (
    <div className="lp-demo">
      <div className="lp-demo-bar">
        <span className="lp-dot lp-dot-r" /><span className="lp-dot lp-dot-y" /><span className="lp-dot lp-dot-g" />
        <span className="lp-demo-title">Unibox — AI triage</span>
      </div>
      <div className="lp-demo-body">
        <AnimatePresence mode="wait">
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -18 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="lp-demo-reply"
          >
            <div className="lp-demo-from">{item.from}</div>
            <div className="lp-demo-text">“{item.text}”</div>
            <motion.div
              className={`lp-tag lp-tag-${item.cat}`}
              initial={{ scale: 0.7, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.35, type: "spring", stiffness: 320, damping: 18 }}
            >
              {CAT_LABEL[item.cat]}
            </motion.div>
            <motion.div
              className="lp-demo-action"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.6, duration: 0.4 }}
            >
              {item.action}
            </motion.div>
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="lp-demo-foot">
        {STREAM.map((_, idx) => (
          <span key={idx} className={`lp-demo-pip ${idx === i ? "on" : ""}`} />
        ))}
      </div>
    </div>
  );
}
