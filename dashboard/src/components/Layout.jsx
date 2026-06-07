import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";

export default function Layout() {
  const { user, logout } = useAuth();
  const loc = useLocation();
  const nav = [
    { to: "/", label: "Dashboard" },
    { to: "/campaigns", label: "Campaigns" },
    { to: "/billing", label: "Billing" },
  ];
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <img src="/app/brand/attainlly-logo.png" alt="Attainlly" />
        </div>
        <nav>
          {nav.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className={loc.pathname === n.to ? "active" : ""}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="muted small">{user?.email}</div>
          <div className="muted small">{user?.tenant_name} · {user?.plan}</div>
          <button className="btn small" onClick={logout}>
            Sign out
          </button>
          <div className="sidebar-tag">
            <img src="/app/brand/attainlly-icon.png" alt="" aria-hidden />
            <span>Attainlly</span>
          </div>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
