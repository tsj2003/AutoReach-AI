import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useScroll, useTransform } from "framer-motion";
import Reveal from "../landing/Reveal.jsx";
import InboxDemo from "../landing/InboxDemo.jsx";
import Marquee from "../landing/Marquee.jsx";
import Personas from "../landing/Personas.jsx";
import Testimonials from "../landing/Testimonials.jsx";

const ROTATING = [
  "without burning your domains.",
  "without babysitting your inbox.",
  "without tanking deliverability.",
  "while you sleep.",
];

export default function Landing() {
  const { scrollYProgress } = useScroll();
  const blobY = useTransform(scrollYProgress, [0, 1], [0, -180]);
  const [phrase, setPhrase] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setPhrase((p) => (p + 1) % ROTATING.length), 2800);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="lp">
      {/* animated gradient blobs */}
      <motion.div className="lp-blob lp-blob-1" style={{ y: blobY }} aria-hidden />
      <motion.div className="lp-blob lp-blob-2" aria-hidden />

      {/* Nav */}
      <motion.header
        className="lp-nav"
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <div className="lp-brand">AutoReach</div>
        <nav className="lp-nav-links">
          <a href="#how">How it works</a>
          <a href="#engine">The engine</a>
          <a href="#pricing">Pricing</a>
          <Link to="/login" className="lp-link-muted">Sign in</Link>
          <Link to="/signup" className="lp-btn lp-btn-sm">Start free</Link>
        </nav>
      </motion.header>

      {/* ───────── Hero ───────── */}
      <section className="lp-hero">
        <motion.div
          className="lp-eyebrow"
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.6 }}
        >
          AI cold-email infrastructure
        </motion.div>

        <h1 className="lp-headline">
          <motion.span
            initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.18, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            style={{ display: "block" }}
          >
            Scale your outbound
          </motion.span>
          <span className="lp-rotate-wrap">
            <motion.span
              key={phrase}
              className="lp-rotate"
              initial={{ opacity: 0, y: 22 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -22 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            >
              {ROTATING[phrase]}
            </motion.span>
          </span>
        </h1>

        <motion.p
          className="lp-subhead"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          transition={{ delay: 0.5, duration: 0.7 }}
        >
          The engine reads every reply, routes each send through a matching mailbox,
          and rotates out any inbox before it gets flagged. You bring the offer.
          AutoReach protects the domains and books the meetings.
        </motion.p>

        <motion.div
          className="lp-cta-row"
          initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.62, duration: 0.6 }}
        >
          <Link to="/signup" className="lp-btn lp-btn-lg">Start Free Trial →</Link>
          <a href="#engine" className="lp-btn lp-btn-ghost lp-btn-lg">Watch the engine</a>
        </motion.div>
        <motion.div
          className="lp-trust"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 }}
        >
          No credit card · 14-day trial · Cancel anytime
        </motion.div>

        {/* floating live demo */}
        <motion.div
          className="lp-hero-demo"
          initial={{ opacity: 0, y: 40, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ delay: 0.7, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        >
          <InboxDemo />
        </motion.div>
      </section>

      {/* ───────── Logos / social proof marquee ───────── */}
      <Reveal className="lp-strip">
        <span>Works with the inboxes and tools you already run</span>
      </Reveal>
      <Marquee items={["Gmail", "Outlook", "Cal.com", "Gemini", "Postgres", "Microsoft 365", "Google Workspace", "Redis", "Celery"]} />

      {/* ───────── How it works — 3 modular feature blocks ───────── */}
      <section id="how" className="lp-features">
        <Reveal><h2 className="lp-section-title">Three things generic tools don't have</h2></Reveal>

        <FeatureRow
          index="01"
          title="AI reply categorization"
          body="Every reply is read and tagged — Interested, Objection, Out-of-Office, Referral, Not-interested, Do-not-contact. Interested replies get an instant calendar draft. OOO auto-reschedules to the return date. You wake up to booked meetings, not a full inbox."
          chips={["Interested → calendar", "OOO → reschedule", "Referral → new lead", "DNC → blocklist"]}
        />
        <FeatureRow
          index="02"
          flip
          title="Dynamic ESP matching"
          body="We read each prospect's MX records and route the send through a matching mailbox — Gmail-to-Gmail, Outlook-to-Outlook. Intra-network mail is trusted more, so more of your email lands in Primary instead of Promotions."
          chips={["Gmail → Gmail", "Outlook → Outlook", "+ inbox placement"]}
        />
        <FeatureRow
          index="03"
          title="Automatic mailbox rotation"
          body="Built-in warmup ramps and live health monitoring. The moment a mailbox's bounce rate spikes, we pause it and rotate in a healthy reserve — automatically — so one bad day never torches your whole domain."
          chips={["Warmup ramps", "Bounce-rate guard", "Auto-rotate reserve"]}
        />
      </section>

      {/* ───────── The engine (animated stat band) ───────── */}
      <section id="engine" className="lp-engine">
        <Reveal><h2 className="lp-section-title lp-on-dark">Built like infrastructure, not a wrapper</h2></Reveal>
        <div className="lp-stats">
          {[
            ["7", "AI reply categories"],
            ["∞", "Connected inboxes"],
            ["100k+", "Leads per campaign"],
            ["3-step", "Smart follow-ups"],
          ].map(([n, l], idx) => (
            <Reveal key={l} delay={idx * 0.08}>
              <div className="lp-stat">
                <div className="lp-stat-n">{n}</div>
                <div className="lp-stat-l">{l}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ───────── Made for the way you work (persona switcher) ───────── */}
      <section className="lp-work">
        <Reveal><h2 className="lp-section-title">Made for the way you work</h2></Reveal>
        <Reveal delay={0.1}><p className="lp-section-sub">Select one to see AutoReach in action.</p></Reveal>
        <Reveal delay={0.15}><Personas /></Reveal>
      </section>

      {/* ───────── Testimonials wall ───────── */}
      <section className="lp-love">
        <Reveal><h2 className="lp-section-title">Operators love AutoReach</h2></Reveal>
        <Reveal delay={0.1}><Testimonials /></Reveal>
      </section>

      {/* ───────── Pricing ───────── */}
      <section id="pricing" className="lp-pricing">
        <Reveal><h2 className="lp-section-title">Simple, flat pricing</h2></Reveal>
        <Reveal delay={0.1}><p className="lp-section-sub">One plan. No per-seat games. No per-inbox tax.</p></Reveal>

        <Reveal delay={0.15}>
          <motion.div className="lp-price-card" whileHover={{ y: -6 }} transition={{ type: "spring", stiffness: 300, damping: 20 }}>
            <div className="lp-price-tag">
              <span className="lp-price-amount">$97</span>
              <span className="lp-price-period">/month</span>
            </div>
            <div className="lp-price-headline">Unlimited Inboxes</div>
            <ul className="lp-price-features">
              <li>Connect unlimited Gmail &amp; Outlook mailboxes</li>
              <li>AI reply categorization &amp; auto-drafting</li>
              <li>Dynamic ESP matching for inbox placement</li>
              <li>Automatic warmup &amp; health-based rotation</li>
              <li>Multi-step sequences with smart follow-ups</li>
              <li>Unified inbox with Attach-Lead for forwarded replies</li>
              <li>Unlimited leads · cursor-fast at any scale</li>
            </ul>
            <Link to="/signup" className="lp-btn lp-btn-lg lp-btn-block">Start Free Trial</Link>
            <div className="lp-price-note">14 days free, then $97/mo. Cancel anytime.</div>
          </motion.div>
        </Reveal>
      </section>

      {/* ───────── Final CTA ───────── */}
      <section className="lp-final">
        <Reveal><h2>Your domains are an asset.<br/>Stop gambling with them.</h2></Reveal>
        <Reveal delay={0.12}>
          <Link to="/signup" className="lp-btn lp-btn-lg">Start Free Trial →</Link>
        </Reveal>
      </section>

      <footer className="lp-footer">
        <span>© {new Date().getFullYear()} AutoReach</span>
        <span className="lp-footer-links">
          <Link to="/login">Sign in</Link>
          <a href="#pricing">Pricing</a>
          <a href="#engine">The engine</a>
        </span>
      </footer>
    </div>
  );
}

function FeatureRow({ index, title, body, chips, flip }) {
  return (
    <Reveal>
      <div className={`lp-feature ${flip ? "flip" : ""}`}>
        <div className="lp-feature-copy">
          <div className="lp-feature-index">{index}</div>
          <h3>{title}</h3>
          <p>{body}</p>
        </div>
        <div className="lp-feature-visual">
          {chips.map((ch, i) => (
            <motion.div
              key={ch}
              className="lp-chip"
              initial={{ opacity: 0, scale: 0.8 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, type: "spring", stiffness: 280, damping: 18 }}
            >
              {ch}
            </motion.div>
          ))}
        </div>
      </div>
    </Reveal>
  );
}
