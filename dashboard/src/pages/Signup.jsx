import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext.jsx";
import SocialAuth from "../components/SocialAuth.jsx";
import BackingBadges from "../components/BackingBadges.jsx";
import {
  AttainlyLogo,
  CornerBrackets,
  PulseDot,
  HeaderTag,
} from "../components/gojiberry/index.js";

export default function Signup() {
  const { signup } = useAuth();
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const [form, setForm] = useState({ company_name: "", full_name: "", email: "", password: "" });
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const onboardingWebsite =
    searchParams.get("onboarding_website") ||
    localStorage.getItem("onboarding_website") ||
    sessionStorage.getItem("onboarding_website") ||
    "";

  useEffect(() => {
    const qSite = searchParams.get("onboarding_website");
    if (qSite) {
      try {
        localStorage.setItem("onboarding_website", qSite);
        sessionStorage.setItem("onboarding_website", qSite);
      } catch (_) {}
    }
  }, [searchParams]);

  function upd(k) {
    return (e) => setForm({ ...form, [k]: e.target.value });
  }

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await signup(form.email.trim(), form.password, form.full_name, form.company_name);
      nav(onboardingWebsite ? `/campaigns?onboarding_website=${encodeURIComponent(onboardingWebsite)}` : "/");
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
        style={{ position: "relative" }}
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      >
        <CornerBrackets variant="all" size={7} color="#0A0A0A" offset={-1} />

        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <PulseDot size={8} color="#D86B23" />
          <HeaderTag variant={3} text="START FREE · ATTAINLY" />
        </div>

        <Link to="/landing" className="auth-brand" style={{ textDecoration: "none" }}>
          <AttainlyLogo size={28} text="Attainly" subText="AI" />
        </Link>

        <h1 className="auth-title">Launch your AI sales agent</h1>
        <p className="auth-sub">
          {onboardingWebsite
            ? `We'll analyze ${onboardingWebsite} and draft your ICP, signal matrix, and first email for review.`
            : "Signal-gated prospecting, approved outbound, and reply classification in one cockpit."}
        </p>

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
            Work Email
            <input type="email" value={form.email} onChange={upd("email")} placeholder="you@company.com" required />
          </label>
          <label className="auth-label">
            Password
            <div className="auth-pw">
              <input
                type={showPw ? "text" : "password"}
                value={form.password}
                onChange={upd("password")}
                placeholder="At least 8 characters"
                required
                minLength={8}
              />
              <button type="button" className="auth-pw-toggle" onClick={() => setShowPw((s) => !s)}>
                {showPw ? "Hide" : "Show"}
              </button>
            </div>
            {pwTooShort && <span className="auth-hint">Password must be at least 8 characters</span>}
          </label>

          <button className="auth-btn" disabled={busy || pwTooShort}>
            {busy ? "Creating…" : "Start 7-day Pro trial →"}
          </button>
          <p className="auth-trust">No credit card required · Cancel anytime · Tenant-isolated</p>
        </form>

        <SocialAuth onError={setErr} />

        <p className="auth-foot">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>

        <BackingBadges compact />
      </motion.div>
    </div>
  );
}
