// Minimal fetch wrapper with JWT injection + auto-refresh on 401.

const ACCESS_KEY = "autoreach_access_token";
const REFRESH_KEY = "autoreach_refresh_token";

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY);
}
export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}
export function setTokens({ access_token, refresh_token }) {
  if (access_token) localStorage.setItem(ACCESS_KEY, access_token);
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function getTenantId() {
  const token = getAccessToken();
  if (!token) return "";
  try {
    const [, payload] = token.split(".");
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    const decoded = JSON.parse(window.atob(padded));
    return decoded.tenant_id || "";
  } catch (_) {
    return "";
  }
}

async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  const res = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return false;
  const data = await res.json();
  setTokens(data);
  return true;
}

function agentDebugLog(location, message, data, hypothesisId) {
  // #region agent log
  fetch("http://127.0.0.1:7688/ingest/968f745b-4f83-4399-8b43-fe5af1c0f06e", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "6c4129" },
    body: JSON.stringify({
      sessionId: "6c4129",
      runId: "post-fix",
      hypothesisId,
      location,
      message,
      data,
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion
}

function debugHypothesisForPath(path) {
  if (path.includes("discover-people")) return "E";
  if (path.includes("approve-job")) return "D";
  if (path.includes("/mailboxes")) return "A";
  return "A";
}

function shouldDebugPath(path) {
  return (
    path.includes("/mailboxes") ||
    path.includes("approve-job") ||
    path.includes("discover-people")
  );
}

function sanitizeDebugBody(path, body) {
  if (!body || typeof body !== "object") return { type: typeof body };
  if (Array.isArray(body) && path.includes("/mailboxes")) {
    return body.map((m) => ({
      id: m.id,
      status: m.status,
      last_error: String(m.last_error || "").slice(0, 160),
      emails_sent_today: m.emails_sent_today,
      max_emails_per_day: m.max_emails_per_day,
      has_refresh_token: m.has_refresh_token,
      has_access_token: m.has_access_token,
    }));
  }
  if (path.includes("approve-job")) {
    return {
      ok: body.ok,
      sent: body.sent,
      state: body.state,
      error: body.error,
      mailbox_id: body.mailbox_id,
      debug: body.debug,
    };
  }
  if (path.includes("discover-people")) {
    const discovery = body.people_discovery || body.discovery?.people_discovery || body.discovery || {};
    return {
      keys: Object.keys(body),
      status: discovery.status,
      count: discovery.count || body.added || body.count,
      message: String(discovery.message || body.message || "").slice(0, 160),
    };
  }
  if (path.includes("connect/start")) {
    return { has_authorization_url: Boolean(body.authorization_url || body.auth_url) };
  }
  return { keys: Object.keys(body) };
}

export async function apiFetch(path, options = {}, retry = true) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  const token = getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401 && retry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return apiFetch(path, options, false);
    clearTokens();
    window.location.href = "/app/login";
    throw new Error("Session expired");
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
      if (shouldDebugPath(path)) {
        agentDebugLog("client.js:apiFetch", "api error", { path, status: res.status, detail: String(detail).slice(0, 180) }, debugHypothesisForPath(path));
      }
    } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  if (res.status === 204) return null;
  const data = await res.json();
  if (shouldDebugPath(path)) {
    agentDebugLog("client.js:apiFetch", "api ok", { path, status: res.status, body: sanitizeDebugBody(path, data) }, debugHypothesisForPath(path));
  }
  return data;
}

// Convenience helpers
export const api = {
  get: (p, options = {}) => apiFetch(p, options),
  post: (p, body) => apiFetch(p, { method: "POST", body: JSON.stringify(body) }),
  patch: (p, body) => apiFetch(p, { method: "PATCH", body: JSON.stringify(body) }),
  del: (p) => apiFetch(p, { method: "DELETE" }),
  upload: (p, formData) => apiFetch(p, { method: "POST", body: formData }),
};
