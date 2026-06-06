import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";

export default function Signup() {
  const { signup } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ email: "", password: "", full_name: "", company_name: "" });
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
      await signup(form.email, form.password, form.full_name, form.company_name);
      nav("/");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <h1>Create your account</h1>
        {err && <div className="error">{err}</div>}
        <label>
          Company name
          <input value={form.company_name} onChange={upd("company_name")} />
        </label>
        <label>
          Full name
          <input value={form.full_name} onChange={upd("full_name")} />
        </label>
        <label>
          Email
          <input type="email" value={form.email} onChange={upd("email")} required />
        </label>
        <label>
          Password (min 8 chars)
          <input type="password" value={form.password} onChange={upd("password")} required />
        </label>
        <button className="btn primary" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
        <p className="muted small">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
