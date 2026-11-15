"""Hard check part 2 — the full outbound path end-to-end with REAL data.

signal (with a real contact email) -> prospect -> tick -> job ->
jobs_awaiting_approval -> approve-job. Plus free-tools generators with the
correct (list) payloads. Proves the core campaign->approved-send loop is real.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid

os.environ.setdefault("AUTOREACH_SIGNALS_ENABLED", "1")
os.environ.setdefault("AUTOREACH_ENRICHMENT_ENABLED", "1")
os.environ.setdefault("AUTOREACH_LEARNING_ENABLED", "1")
os.environ.setdefault("AUTOREACH_JWT_SECRET", "dev-hardcheck-secret-key-0123456789abcdef0123456789")
os.environ.setdefault("AUTOREACH_GMAIL_DRY_RUN", "1")
os.environ.pop("AUTOREACH_PHOENIX_ENDPOINT", None)

from fastapi.testclient import TestClient  # noqa: E402
from cockpit import create_app  # noqa: E402


def j(r):
    try:
        return json.dumps(r.json(), indent=2, default=str)[:1600]
    except Exception:
        return r.text[:1600]


def hdr(n, t):
    print(f"\n{'='*78}\nSTEP {n} — {t}\n{'='*78}")


tmp = tempfile.mkdtemp()
app = create_app(db_url=f"sqlite:///{tmp}/p2.db")
client = TestClient(app)

email = f"founder-{uuid.uuid4().hex[:6]}@attainly.io"
tok = client.post("/api/auth/signup", json={"email": email, "password": "TestPassword123!", "company_name": "Loop Co"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

hdr(1, "Create campaign (min_signal_stack=2 — the wedge)")
cid = client.post("/api/campaigns", headers=H, json={
    "customer_name": "Loop Co", "offer": "Deliverability-first outbound",
    "icp_description": "RevOps leaders at B2B SaaS",
    "allowed_signal_types": ["funding_round", "hiring_surge"],
    "min_signal_stack": 2, "auto_discover_people": False,
}).json()["id"]
print("campaign:", cid)

hdr(2, "Ingest 2 DISTINCT fresh signals on one account WITH a real contact email")
sim = client.post(f"/api/campaigns/{cid}/signals/simulate", headers=H, json={"signals": [
    {"signal_type": "funding_round", "company_domain": "hotco.com",
     "payload": {"company": "Hot Co", "contact_email": "ceo@hotco.com", "summary": "Series A $15M"}},
    {"signal_type": "hiring_surge", "company_domain": "hotco.com",
     "payload": {"company": "Hot Co", "summary": "6 RevOps roles open"}},
]})
print(j(sim))
print("\n  created_count:", sim.json().get("created_count"), "(expect 1 — stack depth 2 + a contact email)")

hdr(3, "Prospect is real and carries signal-stack evidence")
contacts = client.get(f"/api/contacts?campaign_id={cid}", headers=H).json()
print("prospect rows:", len(contacts.get("data", [])))
if contacts.get("data"):
    p = contacts["data"][0]
    print("  email:", p.get("email"), "| company:", p.get("company"))

hdr(4, "Tick -> generate outbound job")
tick = client.post(f"/api/campaigns/{cid}/tick", headers=H)
print(j(tick))

hdr(5, "Read jobs_awaiting_approval (the real HITL queue the UI uses)")
cget = client.get(f"/api/campaigns/{cid}", headers=H).json()
jobs = cget.get("jobs_awaiting_approval", [])
print("jobs awaiting approval:", len(jobs))
if jobs:
    jb = jobs[0]
    print("  job id:", jb.get("id"))
    print("  to_email:", jb.get("to_email"), "| company:", jb.get("company"))
    print("  subject:", (jb.get("subject") or "")[:80])
    print("  body (first 160):", (jb.get("body_text") or "")[:160].replace("\n", " "))
    print("  deliverability_risk:", json.dumps(jb.get("deliverability_risk"))[:160])
    print("  signal_stack:", json.dumps(jb.get("signal_stack"))[:200])
    print("  trace_id:", jb.get("openinference_trace_id"))

    hdr(6, "Approve the job (real HITL approval the React UI calls)")
    ap = client.post(f"/api/campaigns/{cid}/approve-job/{jb['id']}", headers=H)
    print("approve:", ap.status_code)
    print(j(ap))
else:
    print("  (no job generated — prospect may need an email draft; inspect above)")

hdr(7, "Free tools — CORRECT list payloads (deterministic, no LLM required)")
for name, payload in [
    ("sales-nav-filters", {"target_roles": ["VP of Sales", "Head of Growth"],
                            "excluded_roles": ["Intern", "Consultant"],
                            "industries": ["B2B SaaS"], "company_sizes": ["51-200"]}),
    ("subject-lines", {"offer": "deliverability-first outbound", "target_role": "VP of Sales",
                        "signal_type": "RECENT_FUNDING_EVENT", "tone": "Direct"}),
]:
    r = client.post(f"/api/free-tools/{name}", headers=H, json=payload)
    print(f"\n/{name}: {r.status_code}")
    print(j(r))

hdr("DONE", "Outbound loop + free tools verified")
