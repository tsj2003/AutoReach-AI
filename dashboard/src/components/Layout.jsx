import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { AttainlyLogo, CornerBrackets } from "./gojiberry/index.js";

export default function Layout() {
  const { user, logout } = useAuth();
  const loc = useLocation();
  // Customer-core nav only — Integrations/MCP/Playbooks/Signals live on backup/full-product-surface.
  const nav = [
    { to: "/", label: "Dashboard", num: "01" },
    { to: "/campaigns", label: "Campaigns", num: "02" },
    { to: "/operations/mailboxes", label: "Mailboxes", num: "03" },
    { to: "/operations/linkedin", label: "LinkedIn", num: "04" },
    { to: "/operations", label: "Operations", num: "05" },
    { to: "/billing", label: "Billing", num: "06" },
  ];
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand" style={{ paddingBottom: 14, borderBottom: "1px solid #EAEAEA", marginBottom: 12 }}>
          <Link to="/landing" style={{ textDecoration: "none" }}>
            <AttainlyLogo size={24} text="Attainly" subText="AI" />
          </Link>
        </div>
        <nav>
          {nav.map((n) => {
            const isActive =
              n.to === "/"
                ? loc.pathname === "/"
                : loc.pathname === n.to || loc.pathname.startsWith(`${n.to}/`);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={isActive ? "active" : ""}
              >
                <span>{n.label}</span>
                <span className="sidebar-nav-num">{n.num}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-foot" style={{ position: "relative" }}>
          <div className="muted small">{user?.email}</div>
          <div className="muted small">
            {user?.tenant_name} · {user?.plan}
          </div>
          <button className="btn small" onClick={logout}>
            Sign out
          </button>
          <div className="sidebar-tag">
            <AttainlyLogo size={16} text="Attainly" />
          </div>
        </div>
      </aside>
      <main className="main">
        {user?.trial_active && (
          <div className="trial-banner" style={{ position: "relative" }}>
            <CornerBrackets variant="diagonal" size={6} color="#0A0A0A" offset={-1} />
            <span>
              ✨ You're on a free Pro trial — {user.trial_days_left} day
              {user.trial_days_left === 1 ? "" : "s"} left.
            </span>
            <Link to="/billing" className="btn small primary">
              Choose a plan
            </Link>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  );
}
