import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext.jsx";
import { clearTokens } from "../api/client.js";
import SocialAuth from "../components/SocialAuth.jsx";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    clearTokens();
  }, []);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await login(email.trim(), password);
      nav("/");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function fillDemo() {
    setEmail("demo@autoreach.ai");
    setPassword("DemoPass123!");
    setErr("");
  }

  return (
    <div className="auth">
      <div className="auth-blob auth-blob-1" aria-hidden />
      <div className="auth-blob auth-blob-2" aria-hidden />

      <motion.div
        className="auth-card"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      >
        <Link to="/landing" className="auth-brand">
          <img src="/app/brand/attainlly-logo.png" alt="Attainlly" />
        </Link>
        <h1 className="auth-title">Welcome back</h1>
        <p className="auth-sub">Sign in to your account</p>

        {err && <div className="auth-error">{err}</div>}

        <form onSubmit={submit} className="auth-form">
          <label className="auth-label">
            Email
            <input
              type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com" required autoFocus
            />
          </label>

          <label className="auth-label">
            Password
            <div className="auth-pw">
              <input
                type={showPw ? "text" : "password"}
                value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••" required
              />
              <button type="button" className="auth-pw-toggle" onClick={() => setShowPw((s) => !s)}
                      aria-label={showPw ? "Hide password" : "Show password"}>
                {showPw ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          <button className="auth-btn" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <button className="auth-demo" onClick={fillDemo} type="button">
          ✨ Use demo account
        </button>

        <SocialAuth onError={setErr} />

        <p className="auth-foot">
          No account? <Link to="/signup">Create one</Link>
        </p>
        <div className="auth-tag">
          <img src="/app/brand/attainlly-icon.png" alt="" aria-hidden />
          <span>Attainlly · deliverability-first outbound</span>
        </div>
      </motion.div>
    </div>
  );
}
