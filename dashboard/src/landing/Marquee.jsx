import { motion } from "framer-motion";

/**
 * Infinite horizontal logo/word marquee — the Wispr Flow "used by professionals" strip.
 */
export default function Marquee({ items, duration = 26 }) {
  const loop = [...items, ...items];
  return (
    <div className="lp-marquee" aria-hidden>
      <motion.div
        className="lp-marquee-track"
        animate={{ x: ["0%", "-50%"] }}
        transition={{ duration, ease: "linear", repeat: Infinity }}
      >
        {loop.map((it, i) => (
          <span key={i} className="lp-marquee-item">{it}</span>
        ))}
      </motion.div>
    </div>
  );
}
