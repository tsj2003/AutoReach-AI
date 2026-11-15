import { Link } from "react-router-dom";

/** Honest placeholder for features kept on backup/full-product-surface only. */
export default function ComingSoon({ title = "Not in customer-core" }) {
  return (
    <div className="card" style={{ maxWidth: 560, margin: "48px auto", padding: 28 }}>
      <h1 style={{ fontSize: 22, marginBottom: 8 }}>{title}</h1>
      <p className="muted" style={{ lineHeight: 1.5 }}>
        This surface lives on the <code>backup/full-product-surface</code> branch for later.
        The customer-core pilot focuses on campaigns, contacts, Gmail mailboxes, approvals, and inbox.
      </p>
      <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
        <Link className="btn primary" to="/campaigns">
          Go to Campaigns
        </Link>
        <Link className="btn" to="/operations/mailboxes">
          Mailboxes
        </Link>
      </div>
    </div>
  );
}
