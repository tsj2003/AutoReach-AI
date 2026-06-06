import { Link } from "react-router-dom";

// High-converting landing page (Running Lean: instant-clarity UVP → unique value
// → single CTA → transparent pricing). Warm cream / charcoal / lavender, responsive.
export default function Landing() {
  return (
    <div className="lp">
      {/* Nav */}
      <header className="lp-nav">
        <div className="lp-brand">AutoReach</div>
        <nav className="lp-nav-links">
          <a href="#how">How it works</a>
          <a href="#pricing">Pricing</a>
          <Link to="/login" className="lp-link-muted">Sign in</Link>
          <Link to="/signup" className="lp-btn lp-btn-sm">Start free trial</Link>
        </nav>
      </header>

      {/* Hero — Instant Clarity Headline (UVP) */}
      <section className="lp-hero">
        <div className="lp-eyebrow">AI cold-email infrastructure</div>
        <h1 className="lp-headline">
          Scale Your Outbound<br />Without Burning Your Domains.
        </h1>
        <p className="lp-subhead">
          AutoReach runs your cold email on autopilot with three things generic tools
          don't have: <strong>AI reply categorization</strong> that books meetings while
          you sleep, <strong>dynamic ESP matching</strong> that lands Gmail-to-Gmail for
          higher inbox placement, and <strong>automatic mailbox rotation</strong> that
          protects your sender reputation before a domain ever gets flagged.
        </p>
        <div className="lp-cta-row">
          <Link to="/signup" className="lp-btn lp-btn-lg">Start Free Trial →</Link>
          <a href="#how" className="lp-btn lp-btn-ghost lp-btn-lg">See how it works</a>
        </div>
        <div className="lp-trust">No credit card required · 14-day free trial · Cancel anytime</div>
      </section>

      {/* Value props */}
      <section id="how" className="lp-values">
        <ValueCard
          title="AI Reply Categorization"
          body="Every reply is read and tagged — Interested, Objection, Out-of-Office, Referral, Not-interested, Do-not-contact. Interested replies get an instant calendar draft. OOO replies auto-reschedule to the return date. You wake up to booked meetings, not a full inbox."
        />
        <ValueCard
          title="Dynamic ESP Matching"
          body="We read each prospect's MX records and route the send through a matching mailbox — Gmail-to-Gmail, Outlook-to-Outlook. Intra-network mail is trusted more, so more of your emails land in the primary inbox instead of Promotions or Spam."
        />
        <ValueCard
          title="Automatic Mailbox Rotation"
          body="Built-in warmup ramps and live health monitoring. The moment a mailbox's bounce rate spikes, we pause it and rotate in a healthy reserve — automatically — so one bad day never torches your whole domain."
        />
      </section>

      {/* Pricing — transparent flat fee */}
      <section id="pricing" className="lp-pricing">
        <h2 className="lp-section-title">Simple, flat pricing</h2>
        <p className="lp-section-sub">One plan. No per-seat games. No per-inbox tax.</p>

        <div className="lp-price-card">
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
        </div>
      </section>

      {/* Closing CTA */}
      <section className="lp-final">
        <h2>Your domains are an asset. Stop gambling with them.</h2>
        <Link to="/signup" className="lp-btn lp-btn-lg">Start Free Trial →</Link>
      </section>

      <footer className="lp-footer">
        <span>© {new Date().getFullYear()} AutoReach</span>
        <span className="lp-footer-links">
          <Link to="/login">Sign in</Link>
          <a href="#pricing">Pricing</a>
        </span>
      </footer>
    </div>
  );
}

function ValueCard({ title, body }) {
  return (
    <div className="lp-value-card">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}
