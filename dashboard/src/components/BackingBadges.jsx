import { CornerBrackets } from "./gojiberry/index.js";

/** Microsoft for Startups + YC Startup School Bengaluru micro-badges */
export default function BackingBadges({ compact = false }) {
  return (
    <div
      className="auth-badges"
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        gap: compact ? 8 : 10,
        marginTop: compact ? 14 : 0,
        marginBottom: compact ? 0 : 18,
      }}
    >
      <div className="gb-yc-pill" style={{ marginBottom: 0, fontSize: compact ? 11 : undefined }}>
        <CornerBrackets variant="all" size={6} color="#0A0A0A" offset={-1} />
        <svg width="12" height="12" viewBox="0 0 21 21" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
          <rect x="1" y="1" width="9" height="9" fill="#F25022" />
          <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
          <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
          <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
        </svg>
        <span>
          Backed by <strong style={{ color: "#0A0A0A" }}>Microsoft for Startups</strong>
        </span>
      </div>
      <div className="gb-yc-pill" style={{ marginBottom: 0, fontSize: compact ? 11 : undefined }}>
        <CornerBrackets variant="all" size={6} color="#0A0A0A" offset={-1} />
        <span className="gb-yc-box">Y</span>
        <span>
          <strong style={{ color: "#FA651E" }}>YC Startup School</strong> Bengaluru
        </span>
      </div>
    </div>
  );
}
