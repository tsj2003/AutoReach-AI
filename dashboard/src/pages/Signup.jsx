import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext.jsx";
import SocialAuth from "../components/SocialAuth.jsx";

export default function Signup() {
  const { signup } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ company_name: "", full_name: "", email: "", password: "" });
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function upd(k) {
    return (e) => setForm({ ...form, [k]: e.target.value });
  }

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await signup(form.email.trim(), form.password, form.full_name, form.company_name);
      nav("/");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const pwTooShort = form.password.length > 0 && form.password.length < 8;

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
        <h1 className="auth-title">Create your account</h1>
        <p className="auth-sub">Start your 14-day free trial</p>

        {err && <div className="auth-error">{err}</div>}

        <form onSubmit={submit} className="auth-form">
          <label className="auth-label">
            Company name
            <input value={form.company_name} onChange={upd("company_name")} placeholder="Acme Inc" />
          </label>
          <label className="auth-label">
            Full name
            <input value={form.full_name} onChange={upd("full_name")} placeholder="Alex Founder" />
          </label>
          <label className="auth-label">
            Email
            <input type="email" value={form.email} onChange={upd("email")} placeholder="you@company.com" required />
          </label>
          <label className="auth-label">
            Password
            <div className="auth-pw">
              <input
                type={showPw ? "text" : "password"}
                value={form.password} onChange={upd("password")}
                placeholder="At least 8 characters" required minLength={8}
              />
              <button type="button" className="auth-pw-toggle" onClick={() => setShowPw((s) => !s)}>
                {showPw ? "Hide" : "Show"}
              </button>
            </div>
            {pwTooShort && <span className="auth-hint">Password must be at least 8 characters</span>}
          </label>

          <button className="auth-btn" disabled={busy || pwTooShort}>
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>

        <SocialAuth onError={setErr} />

        <p className="auth-foot">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
        <div className="auth-tag">
          <img src="/app/brand/attainlly-icon.png" alt="" aria-hidden />
          <span>Attainlly · deliverability-first outbound</span>
        </div>
      </motion.div>
    </div>
  );
}
