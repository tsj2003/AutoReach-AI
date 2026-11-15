const DEFAULT_API =
  "https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io";

function normalizeBase(url) {
  return String(url || DEFAULT_API).trim().replace(/\/+$/, "") || DEFAULT_API;
}

async function readLinkedInCookies() {
  const liAt = await chrome.cookies.get({
    url: "https://www.linkedin.com/",
    name: "li_at",
  });
  const jsession = await chrome.cookies.get({
    url: "https://www.linkedin.com/",
    name: "JSESSIONID",
  });
  return {
    li_at: liAt?.value || "",
    jsession_id: jsession?.value || "",
  };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.type !== "CONNECT") {
    return undefined;
  }
  (async () => {
    const apiBase = normalizeBase(msg.apiBase);
    const token = String(msg.token || "").trim();
    if (!token) {
      sendResponse({ ok: false, error: "Paste the pairing token from Attainly Integrations." });
      return;
    }
    const cookies = await readLinkedInCookies();
    if (!cookies.li_at) {
      sendResponse({
        ok: false,
        error:
          "No LinkedIn li_at cookie in this Chrome profile. Open linkedin.com, sign in, then click Connect again.",
      });
      return;
    }
    const res = await fetch(`${apiBase}/api/linkedin/connect-by-token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token,
        li_at: cookies.li_at,
        jsession_id: cookies.jsession_id,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail || data.error || data.message || `HTTP ${res.status}`;
      sendResponse({
        ok: false,
        error: typeof detail === "string" ? detail : JSON.stringify(detail),
      });
      return;
    }
    sendResponse({
      ok: true,
      seat: data.seat,
      account_name: data.seat?.account_name || data.voyager_session?.full_name,
    });
  })().catch((err) => {
    sendResponse({ ok: false, error: err?.message || String(err) });
  });
  return true;
});
