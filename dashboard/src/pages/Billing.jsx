import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useAuth } from "../contexts/AuthContext.jsx";

const RZP_SRC = "https://checkout.razorpay.com/v1/checkout.js";

function loadRazorpay() {
  return new Promise((resolve) => {
    if (window.Razorpay) return resolve(true);
    const s = document.createElement("script");
    s.src = RZP_SRC;
    s.onload = () => resolve(true);
    s.onerror = () => resolve(false);
    document.body.appendChild(s);
  });
}

function fmtAmount(amount, currency) {
  const major = (amount || 0) / 100;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(major);
  } catch (_) {
    return `${currency} ${major.toLocaleString()}`;
  }
}

export default function Billing() {
  const { user, refreshUser } = useAuth();
  const [config, setConfig] = useState(null);
  const [data, setData] = useState(null);
  const [usage, setUsage] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([
      api.get("/api/billing/config").catch(() => ({ enabled: false })),
      api.get("/api/billing/plans").catch(() => null),
      api.get("/api/billing/usage").catch(() => null),
    ]).then(([cfg, plans, use]) => {
      setConfig(cfg);
      setData(plans);
      setUsage(use);
    });
  }, []);

  async function buy(planId) {
    setErr("");
    setMsg("");
    setBusy(planId);
    try {
      const ok = await loadRazorpay();
      if (!ok) throw new Error("Could not load the payment library. Check your connection.");

      const order = await api.post("/api/billing/order", { plan: planId });

      await new Promise((resolve, reject) => {
        const rzp = new window.Razorpay({
          key: order.key_id,
          amount: order.amount,
          currency: order.currency,
          name: "Attainlly",
          description: `${order.plan_name} plan`,
          order_id: order.order_id,
          prefill: { email: user?.email || "" },
          theme: { color: "#7c6bff" },
          handler: async (resp) => {
            try {
              await api.post("/api/billing/verify", {
                razorpay_order_id: resp.razorpay_order_id,
                razorpay_payment_id: resp.razorpay_payment_id,
                razorpay_signature: resp.razorpay_signature,
              });
              await refreshUser();
              const fresh = await api.get("/api/billing/usage").catch(() => null);
              if (fresh) setUsage(fresh);
              setMsg(`You're now on the ${order.plan_name} plan. 🎉`);
              resolve();
            } catch (e) {
              reject(e);
            }
          },
          modal: { ondismiss: () => reject(new Error("Payment cancelled")) },
        });
        rzp.on("payment.failed", (r) =>
          reject(new Error(r?.error?.description || "Payment failed"))
        );
        rzp.open();
      });
    } catch (e) {
      if (e.message !== "Payment cancelled") setErr(e.message);
    } finally {
      setBusy("");
    }
  }

  if (!config) return <div className="muted">Loading…</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Billing &amp; plan</h1>
          <p className="muted">You're on the <strong>{user?.plan}</strong> plan.</p>
        </div>
      </div>

      {msg && <div className="notice">{msg}</div>}
      {err && <div className="error">{err}</div>}

      {usage && (
        <div className="stat-grid">
          <div className="stat-card">
            <div className="stat-value">{usage.usage.campaigns}/{usage.usage.campaigns_limit}</div>
            <div className="stat-label">Campaigns used</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{usage.usage.leads_total}/{usage.usage.leads_limit}</div>
            <div className="stat-label">Leads used</div>
          </div>
        </div>
      )}

      {!config.enabled && (
        <div className="card">
          <h3>Payments not configured</h3>
          <p className="muted">
            Razorpay isn't set up on this server yet. Add <code>RAZORPAY_KEY_ID</code> and{" "}
            <code>RAZORPAY_KEY_SECRET</code> to enable upgrades.
          </p>
        </div>
      )}

      {config.enabled && data && (
        <div className="plan-grid">
          {data.plans.map((p) => {
            const current = data.current_plan === p.id;
            return (
              <div key={p.id} className={`plan-card ${current ? "current" : ""}`}>
                <div className="plan-name">{p.name}</div>
                <div className="plan-price">
                  {fmtAmount(p.amount, data.currency)}
                  <span className="plan-per">/mo</span>
                </div>
                <div className="plan-blurb">{p.blurb}</div>
                <button
                  className="btn primary plan-btn"
                  disabled={current || busy === p.id}
                  onClick={() => buy(p.id)}
                >
                  {current ? "Current plan" : busy === p.id ? "Opening…" : `Upgrade to ${p.name}`}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
