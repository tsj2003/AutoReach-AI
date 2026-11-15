import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../contexts/AuthContext.jsx";

const GSI_SRC = "https://accounts.google.com/gsi/client";

/**
 * Renders Google + Microsoft sign-in buttons, GetResponse-style.
 *
 * Google is fully wired through Google Identity Services when the server
 * reports a configured client ID (GET /api/auth/social-config). If Google
 * isn't configured, the whole block hides so we never show a dead button.
 *
 * Microsoft is shown as "coming soon" (disabled) for visual parity — we don't
 * fake a flow that doesn't exist.
 */
export default function SocialAuth({ onError }) {
  const { googleLogin } = useAuth();
  const nav = useNavigate();
  const btnRef = useRef(null);
  const [config, setConfig] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .get("/api/auth/social-config")
      .then((c) => alive && setConfig(c))
      .catch(() => alive && setConfig({ google_enabled: false }));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!config?.google_enabled || !config.google_client_id) return;

    function render() {
      if (!window.google || !btnRef.current) return;
      window.google.accounts.id.initialize({
        client_id: config.google_client_id,
        callback: async (resp) => {
          setBusy(true);
          try {
            await googleLogin(resp.credential);
            nav("/");
          } catch (e) {
            onError?.(e.message || "Google sign-in failed");
          } finally {
            setBusy(false);
          }
        },
      });
      window.google.accounts.id.renderButton(btnRef.current, {
        theme: "outline",
        size: "large",
        width: 320,
        text: "continue_with",
        shape: "pill",
      });
    }

    if (window.google) {
      render();
      return;
    }
    let script = document.querySelector(`script[src="${GSI_SRC}"]`);
    if (!script) {
      script = document.createElement("script");
      script.src = GSI_SRC;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
    script.addEventListener("load", render);
    return () => script.removeEventListener("load", render);
  }, [config, googleLogin, nav, onError]);

  if (!config?.google_enabled) return null;

  return (
    <div className="social-auth">
      <div className="social-divider"><span>or continue with</span></div>
      <div className="social-btns">
        <div ref={btnRef} className={busy ? "social-google busy" : "social-google"} />
        <button type="button" className="social-btn social-ms" disabled title="Coming soon">
          <span className="social-ms-mark" aria-hidden>
            <span /><span /><span /><span />
          </span>
          Microsoft <em>soon</em>
        </button>
      </div>
    </div>
  );
}
