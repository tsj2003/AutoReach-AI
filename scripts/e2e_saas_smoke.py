#!/usr/bin/env python3
"""
End-to-end SaaS smoke test: exercises the full multi-tenant stack through
the REST API exactly as the React dashboard would.

Run: .venv/bin/python scripts/e2e_saas_smoke.py
"""

import pathlib
import sys

DB = "/tmp/autoreach_e2e.db"
pathlib.Path(DB).unlink(missing_ok=True)

from cockpit import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

app = create_app(db_url=f"sqlite:///{DB}")
c = TestClient(app, raise_server_exceptions=True)


def step(label, ok):
    mark = "✅" if ok else "❌"
    print(f"  {mark} {label}")
    if not ok:
        sys.exit(1)


print("\n=== AutoReach SaaS E2E smoke ===\n")

# 1. Signup
r = c.post("/api/auth/signup", json={
    "email": "founder@acme.com", "password": "Password1!",
    "full_name": "Alice", "company_name": "Acme Inc",
})
step("signup returns JWT", r.status_code == 200 and r.json().get("access_token"))
h = {"Authorization": f"Bearer {r.json()['access_token']}"}

# 2. Me
r = c.get("/api/auth/me", headers=h)
step("auth/me returns tenant", r.json().get("tenant_name") == "Acme Inc")

# 3. Billing plan
r = c.get("/api/billing/plan", headers=h)
step("billing plan = free", r.json()["plan"] == "free")

# 4. Create campaign
r = c.post("/api/campaigns", json={
    "customer_name": "Outbound Q3", "offer": "AI sales infra. $500/meeting.",
    "icp_description": "B2B founders", "booking_url": "https://cal.com/me",
    "price_per_outcome_cents": 50000, "hitl_threshold": 2,
}, headers=h)
step("campaign created", r.status_code == 201)
cid = r.json()["id"]

# 5. Free plan blocks 2nd campaign
r2 = c.post("/api/campaigns", json={"customer_name": "X", "offer": "O", "icp_description": "I"}, headers=h)
step("free plan blocks 2nd campaign (403)", r2.status_code == 403)

# 6. Upload contacts
csv_bytes = b"email,name,company\na@x.com,Alice,Acme\nb@y.com,Bob,Beta\nc@z.com,Carol,Cygnus\n"
r = c.post("/api/contacts/upload", params={"campaign_id": cid},
           files={"file": ("p.csv", csv_bytes, "text/csv")}, headers=h)
step("CSV upload loaded 3", r.json()["loaded"] == 3)

# 7. Cursor pagination
r = c.get("/api/contacts", params={"campaign_id": cid, "limit": 2}, headers=h)
step("contacts page 1 = 2 + has_more", len(r.json()["data"]) == 2 and r.json()["has_more"])
cursor = r.json()["next_cursor"]
r = c.get("/api/contacts", params={"campaign_id": cid, "limit": 2, "cursor": cursor}, headers=h)
step("contacts page 2 = 1, no more", len(r.json()["data"]) == 1 and not r.json()["has_more"])

# 8. Tick (jobs → awaiting approval, hitl_threshold=2)
r = c.post(f"/api/campaigns/{cid}/tick", headers=h)
step("tick ran", r.json()["ok"])
r = c.get(f"/api/campaigns/{cid}", headers=h)
step("jobs awaiting approval", len(r.json()["jobs_awaiting_approval"]) >= 1)

# 9. Approve a job, drain → email sent (console adapter)
job_id = r.json()["jobs_awaiting_approval"][0]["id"]
r = c.post(f"/api/campaigns/{cid}/approve-job/{job_id}", headers=h)
step("job approved", r.json()["ok"])
c.post(f"/api/campaigns/{cid}/drain", headers=h)

# 10. Record a reply (simulating inbound) + inbox
prospect = list(app.state.ops.list_prospects(cid))[0]
app.state.ops.record_reply(engagement_id=cid, prospect_id=prospect.id,
                           snippet="interested, send a link", classification="interested",
                           suggested_reply="Book here: https://cal.com/me")
r = c.get("/api/inbox", params={"campaign_id": cid}, headers=h)
step("inbox shows reply", len(r.json()) == 1 and r.json()[0]["classification"] == "interested")

# 11. Book + qualify a meeting
r = c.post("/api/meetings", json={
    "campaign_id": cid, "prospect_id": prospect.id,
    "scheduled_for": "2026-07-01T15:00:00+00:00",
}, headers=h)
step("meeting booked", r.status_code == 201)
mid = r.json()["id"]
r = c.post(f"/api/meetings/{mid}/status", json={"status": "qualified"}, headers=h)
step("meeting qualified", r.json()["ok"])

# 12. Analytics reflects revenue ($500 = 1 qualified × 50000c)
r = c.get("/api/analytics/dashboard", headers=h)
totals = r.json()["totals"]
step("analytics revenue = $500", totals["total_revenue_cents"] == 50000)
step("analytics qualified = 1", totals["total_qualified"] == 1)

# 13. Tenant isolation
r = c.post("/api/auth/signup", json={"email": "intruder@evil.com", "password": "Password1!"})
h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
r = c.get(f"/api/campaigns/{cid}", headers=h2)
step("tenant isolation: intruder gets 404", r.status_code == 404)

# 14. SPA served
r = c.get("/app/")
step("React SPA served at /app/", r.status_code == 200 and 'id="root"' in r.text)

print("\n✨ All E2E steps passed — the SaaS stack works end to end.\n")
pathlib.Path(DB).unlink(missing_ok=True)
