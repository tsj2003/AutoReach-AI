const DEFAULT_API =
  "https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io";

const tokenEl = document.getElementById("token");
const apiEl = document.getElementById("apiBase");
const btn = document.getElementById("connect");
const statusEl = document.getElementById("status");

function setStatus(text, kind) {
  statusEl.textContent = text || "";
  statusEl.className = `status ${kind || ""}`;
}

chrome.storage.local.get(["apiBase", "token"], (saved) => {
  apiEl.value = saved.apiBase || DEFAULT_API;
  tokenEl.value = saved.token || "";
});

btn.addEventListener("click", async () => {
  const token = tokenEl.value.trim();
  const apiBase = (apiEl.value || DEFAULT_API).trim();
  chrome.storage.local.set({ apiBase, token });
  if (!token) {
    setStatus("Paste the pairing token from Attainly Integrations.", "err");
    return;
  }
  btn.disabled = true;
  setStatus("Reading LinkedIn cookies and pairing…");
  try {
    const res = await chrome.runtime.sendMessage({ type: "CONNECT", token, apiBase });
    if (!res?.ok) {
      setStatus(res?.error || "Connect failed.", "err");
      return;
    }
    const name = res.account_name || res.seat?.account_name || "LinkedIn seat";
    setStatus(`Connected ${name}. You can close this popup.`, "ok");
  } catch (err) {
    setStatus(err?.message || String(err), "err");
  } finally {
    btn.disabled = false;
  }
});
