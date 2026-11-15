import React from "react";
import { Link } from "react-router-dom";

/** Official Attainly lockup: coral/orange 3D rising-arrow mark + wordmark. */
const ATTAINLY_LOGO_SRC = "/app/brand/attainly-logo.png";

function AttainlyLogoImage({ height = 24, alt = "Attainly", className = "", style = {} }) {
  return (
    <img
      src={ATTAINLY_LOGO_SRC}
      alt={alt}
      height={height}
      className={className}
      draggable={false}
      style={{
        height,
        width: "auto",
        maxWidth: "100%",
        objectFit: "contain",
        display: "block",
        ...style,
      }}
    />
  );
}

/**
 * Official Attainly lockup (rising-arrow + wordmark). Used as the compact mark
 * in Venn, hubs, and cards — never the cube or a Gojiberry shield.
 */
export function AttainlyMark({ size = 24, style = {} }) {
  return (
    <span className="gb-logo-mark" style={{ display: "inline-flex", flexShrink: 0, ...style }}>
      <AttainlyLogoImage height={size} alt="" className="gb-logo-mark-img" />
    </span>
  );
}

/**
 * Official Attainly lockup. The PNG already includes the "Attainly" wordmark,
 * so extra text is not rendered (props kept for call-site compatibility).
 */
export function AttainlyLogo({ size = 24, showText = true, text = "Attainly", subText = "", style = {} }) {
  void showText;
  void text;
  void subText;
  return (
    <span className="gb-logo-wrap" style={{ display: "inline-flex", alignItems: "center", ...style }}>
      <AttainlyLogoImage height={size} alt="Attainly" />
    </span>
  );
}

export const GojiberryLogo = AttainlyLogo;

/**
 * <CornerBrackets /> — 7×7px L-bracket SVGs (`┌ ┐ └ ┘`)
 * Placed in all 4 corners (`variant="all"`) or 2 diagonal corners (`top-left` & `bottom-right` for `variant="diagonal"`).
 */
export function CornerBrackets({
  variant = "all",
  size = 7,
  color = "#0A0A0A",
  offset = -1,
  strokeWidth = 1.25,
}) {
  const base = {
    position: "absolute",
    width: size,
    height: size,
    pointerEvents: "none",
    zIndex: 3,
  };

  return (
    <>
      {/* Top-Left ┌ */}
      <svg
        style={{ ...base, top: offset, left: offset }}
        viewBox="0 0 7 7"
        fill="none"
        aria-hidden="true"
      >
        <path d="M0.6 7V0.6H7" stroke={color} strokeWidth={strokeWidth} />
      </svg>

      {variant === "all" && (
        <>
          {/* Top-Right ┐ */}
          <svg
            style={{ ...base, top: offset, right: offset }}
            viewBox="0 0 7 7"
            fill="none"
            aria-hidden="true"
          >
            <path d="M0 0.6H6.4V7" stroke={color} strokeWidth={strokeWidth} />
          </svg>

          {/* Bottom-Left └ */}
          <svg
            style={{ ...base, bottom: offset, left: offset }}
            viewBox="0 0 7 7"
            fill="none"
            aria-hidden="true"
          >
            <path d="M0.6 0V6.4H7" stroke={color} strokeWidth={strokeWidth} />
          </svg>
        </>
      )}

      {/* Bottom-Right ┘ */}
      <svg
        style={{ ...base, bottom: offset, right: offset }}
        viewBox="0 0 7 7"
        fill="none"
        aria-hidden="true"
      >
        <path d="M0 6.4H6.4V0" stroke={color} strokeWidth={strokeWidth} />
      </svg>
    </>
  );
}

/**
 * <CornerCrosshairs /> — 10×10px `+` SVGs for Venn diagram & technical labels.
 */
export function CornerCrosshairs({ size = 10, color = "#0A0A0A", offset = -5, variant = "all" }) {
  const half = size / 2;
  const Cross = ({ style }) => (
    <svg
      style={{
        position: "absolute",
        width: size,
        height: size,
        pointerEvents: "none",
        zIndex: 3,
        ...style,
      }}
      viewBox={`0 0 ${size} ${size}`}
      fill="none"
      aria-hidden="true"
    >
      <line x1={half} y1="1" x2={half} y2={size - 1} stroke={color} strokeWidth="1.1" />
      <line x1="1" y1={half} x2={size - 1} y2={half} stroke={color} strokeWidth="1.1" />
    </svg>
  );

  return (
    <>
      <Cross style={{ top: offset, left: offset }} />
      {variant === "all" && (
        <>
          <Cross style={{ top: offset, right: offset }} />
          <Cross style={{ bottom: offset, left: offset }} />
        </>
      )}
      <Cross style={{ bottom: offset, right: offset }} />
    </>
  );
}

/**
 * <SectionSeparator /> — Full-width 1px #EAEAEA line with centered 9×9px #0A0A0A `+` icon.
 */
export function SectionSeparator({ style = {} }) {
  return (
    <div className="gb-section-separator" style={style} role="separator">
      <div className="gb-section-separator-line" />
      <span className="gb-section-separator-plus" aria-hidden="true">
        <svg width="9" height="9" viewBox="0 0 9 9" fill="none">
          <path d="M4.5 0.5V8.5M0.5 4.5H8.5" stroke="#0A0A0A" strokeWidth="1.25" />
        </svg>
      </span>
      <div className="gb-section-separator-line" />
    </div>
  );
}

/**
 * <PulseDot /> — 12×12px black circle with 4×4px white center and 2s expanding #D86B23 radar ring.
 */
export function PulseDot({ size = 12, color = "#D86B23", style = {} }) {
  const inner = Math.max(3, Math.round(size / 3));
  return (
    <span
      className="gb-pulse-dot"
      style={{
        width: size,
        height: size,
        "--gb-pulse-color": color,
        ...style,
      }}
      aria-hidden="true"
    >
      <span className="gb-pulse-ring" />
      <span
        className="gb-pulse-core"
        style={{ width: size, height: size }}
      >
        <span
          className="gb-pulse-center"
          style={{ width: inner, height: inner }}
        />
      </span>
    </span>
  );
}

/**
 * <HeaderTag />
 * - Variant 1 (`1/4`–`4/4`, `01`–`03`): `rgba(255, 70, 46, 0.10)` pill with `#FA651E` text and `#FF462E` icon.
 * - Variant 3 (`PRO`, `CUSTOM`, `LEARNING`, `CONTROL`, `REPLIES`, `LEAD GENERATION`, `OUTREACH`):
 *   `10×10px` pulsing dot + 2 diagonal L-brackets.
 */
export function HeaderTag({ variant = 1, text, children, icon = "chain", style = {} }) {
  const label = text || children;
  if (Number(variant) === 3 || variant === "bracket") {
    return (
      <span className="gb-header-tag-v3" style={style}>
        <CornerBrackets variant="diagonal" size={7} color="#0A0A0A" offset={-1} />
        <PulseDot size={10} color="#D86B23" />
        <span className="gb-header-tag-v3-text">{label}</span>
      </span>
    );
  }

  return (
    <span className="gb-header-tag-v1" style={style}>
      <svg
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
        aria-hidden="true"
        style={{ flexShrink: 0 }}
      >
        {icon === "arrow" ? (
          <path
            d="M2.5 9.5L9.5 2.5M9.5 2.5H4M9.5 2.5V8"
            stroke="#FF462E"
            strokeWidth="1.35"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : (
          <>
            <path
              d="M4.8 7.2L7.2 4.8M3.5 5.2L2.4 6.3C1.6 7.1 1.6 8.4 2.4 9.2C3.2 10 4.5 10 5.3 9.2L6.4 8.1M5.6 3.9L6.7 2.8C7.5 2 8.8 2 9.6 2.8C10.4 3.6 10.4 4.9 9.6 5.7L8.5 6.8"
              stroke="#FF462E"
              strokeWidth="1.2"
              strokeLinecap="round"
            />
          </>
        )}
      </svg>
      <span>{label}</span>
    </span>
  );
}

/**
 * <GradientPill /> — DM Mono 12px, border-radius: 127px
 * - yellow: linear-gradient(180deg, rgb(255, 234, 0) 0%, rgb(255, 251, 201) 100%)
 * - peach: linear-gradient(180deg, rgb(255, 194, 153) 0%, rgb(255, 175, 153) 100%)
 * - mint: linear-gradient(180deg, rgb(214, 255, 245) 0%, rgb(103, 218, 191) 100%)
 */
export function GradientPill({ variant = "yellow", children, style = {}, onClick }) {
  const v = ["yellow", "peach", "mint"].includes(variant) ? variant : "yellow";
  return (
    <span
      className={`gb-gradient-pill gb-gradient-pill-${v}`}
      style={{ cursor: onClick ? "pointer" : "default", ...style }}
      onClick={onClick}
    >
      {children}
    </span>
  );
}

/**
 * <CoralExpandButton />
 * height: 54px (or 40px when size="sm"), #EAEAEA surface, 4 corner 7×7 L-brackets,
 * left 38×38px #FA5C5C coral square with white arrow that smoothly expands across
 * the entire button on hover and flips text to white.
 */
export function CoralExpandButton({
  children,
  to,
  href,
  onClick,
  size = "md",
  type = "button",
  disabled = false,
  style = {},
  className = "",
}) {
  const isSmall = size === "sm";
  const content = (
    <>
      <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />
      <span className="gb-coral-btn-expander" aria-hidden="true">
        <span className="gb-coral-btn-icon">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M2.5 7H11.5M11.5 7L7.5 3M11.5 7L7.5 11"
              stroke="#FFFFFF"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </span>
      <span className="gb-coral-btn-label">{children}</span>
    </>
  );

  const classes = `gb-coral-expand-btn ${isSmall ? "gb-coral-expand-btn-sm" : ""} ${className}`.trim();

  if (to) {
    return (
      <Link to={to} className={classes} style={style} onClick={onClick}>
        {content}
      </Link>
    );
  }
  if (href) {
    return (
      <a href={href} className={classes} style={style} onClick={onClick}>
        {content}
      </a>
    );
  }
  return (
    <button
      type={type}
      className={classes}
      onClick={onClick}
      disabled={disabled}
      style={style}
    >
      {content}
    </button>
  );
}

/**
 * <BracketBox /> — Architectural container with hairline border and corner L-brackets.
 */
export function BracketBox({
  children,
  variant = "all",
  className = "",
  style = {},
  as: Tag = "div",
  onClick,
}) {
  return (
    <Tag
      className={`gb-bracket-box ${className}`.trim()}
      style={{ position: "relative", ...style }}
      onClick={onClick}
    >
      <CornerBrackets variant={variant} size={7} color="#0A0A0A" offset={-1} />
      {children}
    </Tag>
  );
}
