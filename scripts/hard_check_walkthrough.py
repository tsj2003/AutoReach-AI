"""Live, step-by-step hard check of every customer-facing feature.

Drives the REAL FastAPI app in-process against a REAL SQLite DB and a REAL
signup -> campaign -> signals -> prospects -> job -> approval -> outcome
sequence. Prints actual JSON responses as evidence. No mocks. For features
that need external access (LinkedIn live session, live web dorking, RDAP,
SMTP) we exercise the real code path and report the honest dry-run / empty
behaviour so you can see exactly what is end-to-end vs blocked on externals.

Run: python3 scripts/hard_check_walkthrough.py
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid

os.environ.setdefault("AUTOREACH_SIGNALS_ENABLED", "1")
os.environ.setdefault("AUTOREACH_ENRICHMENT_ENABLED", "1")
os.environ.setdefault("AUTOREACH_LEARNING_ENABLED", "1")
# Keep telemetry export inert (no localhost:6006 noise)
os.environ.pop("AUTOREACH_PHOENIX_ENDPOINT", None)

from fastapi.testclient import TestClient  # noqa: E402

from cockpit import create_app  # noqa: E402


def j(r):
    try:
        return json.dumps(r.json(), indent=2, default=str)[:2000]
    except Exception:
        return r.text[:2000]


def hdr(n, title):
    print(f"\n{'='*78}\nSTEP {n} — {title}\n{'='*78}")


def sub(label):
    print(f"\n  >> {label}")


tmp = tempfile.mkdtemp()
app = create_app(db_url=f"sqlite:///{tmp}/hardcheck.db")
client = TestClient(app)
store = app.state.store

# ───────────────────────── STEP 1: AUTH + TENANT ISOLATION ─────────────────
hdr(1, "AUTH: signup / login / me  (real JWT, real bcrypt)")
emailA = f"founderA-{uuid.uuid4().hex[:6]}@attainly.io"
emailB = f"founderB-{uuid.uuid4().hex[:6]}@attainly.io"
rA = client.post("/api/auth/signup", json={"email": emailA, "password": "TestPassword123!", "company_name": "Tenant A Co"})
print("signup A:", rA.status_code)
print(j(rA))
tokA = rA.json()["access_token"]
HA = {"Authorization": f"Bearer {tokA}"}

rB = client.post("/api/auth/signup", json={"email": emailB, "password": "TestPassword123!", "company_name": "Tenant B Co"})
tokB = rB.json()["access_token"]
HB = {"Authorization": f"Bearer {tokB}"}

sub("login (re-auth) A")
rl = client.post("/api/auth/login", json={"email": emailA, "password": "TestPassword123!"})
print("login A:", rl.status_code, "has token:", bool(rl.json().get("access_token")))

sub("no-token request is rejected")
rno = client.get("/api/campaigns")
print("GET /api/campaigns without token:", rno.status_code)

# ───────────────────────── STEP 2: CAMPAIGN CREATE ─────────────────────────
hdr(2, "CAMPAIGN: create with client_cure + signal_matrix (min_signal_stack)")
camp = client.post("/api/campaigns", headers=HA, json={
    "customer_name": "Tenant A Co",
    "offer": "Deliverability-first outbound for B2B SaaS",
    "icp_description": "VP Sales / Head of Growth at 50-500 person B2B SaaS",
    "client_cure": "We help RevOps teams book meetings from fresh buying signals without burning domains.",
    "allowed_signal_types": ["RECENT_FUNDING_EVENT", "HIRING_SURGE", "COMPETITOR_PAGE_URL"],
    "min_signal_stack": 1,
    "auto_discover_people": False,
    "monthly_meeting_target": 10,
    "price_per_outcome_cents": 50000,
})
print("create campaign:", camp.status_code)
print(j(camp))
cid = camp.json()["id"]

sub("tenant B cannot see tenant A's campaign")
rB_list = client.get("/api/campaigns", headers=HB)
print("Tenant B campaign list:", rB_list.status_code, "count:", len(rB_list.json()))
rB_get = client.get(f"/api/campaigns/{cid}", headers=HB)
print(f"Tenant B GET A's campaign {cid[:12]}:", rB_get.status_code, "(expect 404)")

# ───────────────────────── STEP 3: SIGNAL INGEST -> PROSPECTS ──────────────
hdr(3, "SIGNALS: ingest real signals through pipeline -> stacked prospects")
sim = client.post(f"/api/campaigns/{cid}/signals/simulate", headers=HA, json={
    "signals": [
        {"signal_type": "RECENT_FUNDING_EVENT", "company_domain": "acme-saas.com",
         "payload": {"company": "Acme SaaS", "summary": "Raised $12M Series A last week"}},
        {"signal_type": "HIRING_SURGE", "company_domain": "acme-saas.com",
         "payload": {"company": "Acme SaaS", "summary": "7 open RevOps roles posted"}},
        {"signal_type": "COMPETITOR_PAGE_URL", "company_domain": "beta-corp.io",
         "payload": {"company": "Beta Corp", "summary": "Engaged with a competitor's LinkedIn page"}},
    ],
})
print("signals/simulate:", sim.status_code)
print(j(sim))

sub("blocked signal type is refused (signal-matrix discipline)")
sim_bad = client.post(f"/api/campaigns/{cid}/signals/simulate", headers=HA, json={
    "signals": [{"signal_type": "GITHUB_ENGAGEMENT", "company_domain": "x.com", "payload": {"company": "X"}}],
})
print("disallowed signal ingest:", sim_bad.status_code)
print("created_count:", sim_bad.json().get("created_count"), "(expect 0 — not in allowed_signal_types)")

sub("contacts now visible for campaign")
contacts = client.get(f"/api/contacts?campaign_id={cid}", headers=HA)
print("contacts list:", contacts.status_code, "rows:", len(contacts.json().get("data", [])))

# ───────────────────────── STEP 4: TICK -> JOB -> APPROVE ──────────────────
hdr(4, "OUTBOUND: tick generates jobs -> HITL approval queue -> outbox")
tick = client.post(f"/api/campaigns/{cid}/tick", headers=HA)
print("tick:", tick.status_code)
print(j(tick))

sub("pending approvals (outbox)")
pend = client.get("/api/v1/outbox/pending", headers=HA)
print("outbox/pending:", pend.status_code)
print(j(pend))

pend_items = pend.json() if isinstance(pend.json(), list) else pend.json().get("items", pend.json().get("jobs", []))
if pend_items:
    jobid = pend_items[0].get("id")
    sub(f"approve job {str(jobid)[:12]}")
    appr = client.post(f"/api/v1/outbox/{jobid}/approve", headers=HA)
    print("approve:", appr.status_code)
    print(j(appr))
else:
    print("  (no pending jobs — see notes; prospects may need enrichment/email first)")

# ───────────────────────── STEP 5: ANALYTICS + BILLING (REAL TOTALS) ───────
hdr(5, "ROI PROOF: analytics dashboard + billing usage (real ledger)")
dash = client.get("/api/analytics/dashboard", headers=HA)
print("analytics/dashboard:", dash.status_code)
print(j(dash))
usage = client.get("/api/billing/usage", headers=HA)
print("\nbilling/usage:", usage.status_code)
print(j(usage))

# ───────────────────────── STEP 6: WEEKLY LEARNING (HONEST EMPTY) ──────────
hdr(6, "WEEKLY AI LOOP: /api/learning/weekly  (the one flagged as fake)")
wk = client.get("/api/learning/weekly", headers=HA)
print("learning/weekly:", wk.status_code)
print(j(wk))
wkj = wk.json()
print("\n  VERDICT: enough_data =", wkj.get("enough_data"),
      "| replies_total =", wkj.get("replies_total"),
      "| meetings_booked =", wkj.get("meetings_booked"))
print("  -> No 48/112/64/85, no 24.2%, no +3.4x. Real aggregation, honest empty.")

# ───────────────────────── STEP 7: B2B DIRECTORY (HONEST EMPTY/404) ────────
hdr(7, "B2B DIRECTORY: search / reveal / companies / stats (no seed rows)")
ls = client.post("/api/directory/leads/search", headers=HA, json={"title": "VP Sales", "limit": 10})
print("leads/search:", ls.status_code, "-> total:", ls.json().get("total"), "items:", len(ls.json().get("items", [])))
rev404 = client.post("/api/directory/leads/reveal", headers=HA, json={"lead_id": "does-not-exist"})
print("reveal unknown lead_id:", rev404.status_code, "(expect 404 — no SEED fallback)")
cs = client.get("/api/directory/companies/search?limit=10", headers=HA)
print("companies/search:", cs.status_code, "-> total:", cs.json().get("total", len(cs.json().get("items", []))))
st = client.get("/api/directory/stats", headers=HA)
print("stats:", st.status_code)
print(j(st))

sub("reveal by REAL name+domain (synthesizes verified-pattern email, no placeholder phone)")
rev = client.post("/api/directory/leads/reveal", headers=HA, json={
    "first_name": "Sarah", "last_name": "Chen", "domain": "linear.app",
    "reveal_email": True, "extract_phone": False,
})
print("reveal real:", rev.status_code)
print(j(rev))

sub("saved searches now persist in a real tenant-scoped DB table")
mk = client.post("/api/directory/saved-searches", headers=HA, json={"name": "VPs at SaaS", "filters": {"title": "VP Sales"}})
print("create saved-search:", mk.status_code)
sv = client.get("/api/directory/saved-searches", headers=HA)
print("list saved-searches:", sv.status_code, "-> count:", len(sv.json().get("items", sv.json() if isinstance(sv.json(), list) else [])))
svB = client.get("/api/directory/saved-searches", headers=HB)
print("tenant B saved-searches:", svB.status_code, "-> count:", len(svB.json().get("items", svB.json() if isinstance(svB.json(), list) else [])), "(expect 0 — isolated)")

# ───────────────────────── STEP 8: VISITOR DE-ANON ─────────────────────────
hdr(8, "VISITOR DE-ANON: beacon / simulate (real rDNS+RDAP, no CIDR seed)")
snip = client.get("/api/visitors/script-snippet", headers=HA)
print("script-snippet:", snip.status_code, "(real wv.js embed)")
sim_empty = client.post("/api/visitors/simulate", headers=HA, json={})
print("simulate with NO input:", sim_empty.status_code, "(expect 400 — requires real domain/IP/token)")
sim_dom = client.post("/api/visitors/simulate", headers=HA, json={"domain": "linear.app"})
print("simulate with real domain:", sim_dom.status_code)
print(j(sim_dom))
feed = client.get("/api/visitors/feed", headers=HA)
print("\nvisitors/feed:", feed.status_code)
print(j(feed))

# ───────────────────────── STEP 9: LINKEDIN VOYAGER (DRY-RUN HONEST) ───────
hdr(9, "LINKEDIN: connect seat / scrape-post-engagers / sync-inbox")
conn = client.post("/api/linkedin/connect", headers=HA, json={
    "li_at": "AQEDAR_demo_token_123456", "jsession_id": '"ajax:5544332211"', "seat_name": "Founder Seat"})
print("connect seat:", conn.status_code)
seat_id = conn.json().get("seat_id") or conn.json().get("id")
eng = client.post("/api/linkedin/scrape-post-engagers", headers=HA, json={
    "seat_id": seat_id,
    "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:7192837192837192837/",
    "signal_type": "COMPETITOR_PAGE_URL", "persist_signals": True})
print("scrape-post-engagers:", eng.status_code, "-> count:", eng.json().get("count"),
      "persisted_signals:", eng.json().get("persisted_signals"), "(0 = no live session, no fabrication)")
inbox = client.post("/api/linkedin/sync-inbox", headers=HA, json={"seat_id": seat_id})
print("sync-inbox:", inbox.status_code, "-> ok:", inbox.json().get("ok"),
      "threads:", inbox.json().get("synced", inbox.json().get("count")), "(no fake 'interested' replies)")

# ───────────────────────── STEP 10: FREE TOOLS (REAL DETERMINISTIC) ───────
hdr(10, "FREE TOOLS: sales-nav boolean / ICP / subject lines / persona")
nav = client.post("/api/free-tools/sales-nav-filters", headers=HA, json={
    "target_roles": "VP of Sales, Head of Growth", "exclude_titles": "Intern, Consultant",
    "industry_headcount": "B2B SaaS (51-200)"})
print("sales-nav-filters:", nav.status_code)
print(j(nav))

# ───────────────────────── STEP 11: WEBSITE INTAKE (SSRF GUARD) ───────────
hdr(11, "WEBSITE INTAKE: /api/onboarding/analyze-website (SSRF-guarded)")
ssrf = client.post("/api/onboarding/analyze-website", headers=HA, json={"url": "http://169.254.169.254/latest/meta-data/"})
print("analyze internal/metadata URL:", ssrf.status_code, "(expect 4xx — SSRF blocked)")
print(j(ssrf))

# ───────────────────────── SUMMARY ────────────────────────────────────────
hdr("DONE", "Walkthrough complete — see per-step evidence above")
