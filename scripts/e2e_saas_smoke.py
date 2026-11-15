#!/usr/bin/env python3
"""
End-to-end SaaS smoke test: exercises the full multi-tenant stack through
the REST API exactly as the React dashboard would.

Run: python3 scripts/e2e_saas_smoke.py
"""

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = "/tmp/autoreach_e2e.db"
pathlib.Path(DB).unlink(missing_ok=True)

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost/autoreach")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AUTOREACH_JWT_SECRET", "x" * 40)
os.environ.setdefault("AUTOREACH_SESSION_SECRET", "y" * 40)
os.environ.setdefault("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", "EFONWtQiHXh-5vpx9TVH0qCuVCkqUgJutdYjRM3J_iE=")
os.environ.setdefault("AUTOREACH_ENABLE_CONSOLE", "0")
os.environ.setdefault("AUTOREACH_RUNTIME_SMART_DISPATCH", "1")
os.environ.setdefault("AUTOREACH_WORKER_QUEUES", "engine,maintenance,standard-agents")
os.environ.setdefault("GEMINI_API_KEY", "smoke-gemini")
os.environ.setdefault("GOOGLE_CLIENT_ID", "smoke-google-client")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "smoke-google-secret")
os.environ.setdefault("CALCOM_WEBHOOK_SECRET", "smoke-calcom-secret")
os.environ.setdefault("AUTOREACH_PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")

from cockpit import create_app  # noqa: E402
from cockpit.services.preflight import DeliverabilityPreflight, PreflightResult  # noqa: E402
from engine.dispatch.provider import SMTPProvider  # noqa: E402
from engine.auth.mailbox_models import Mailbox  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


async def _smoke_send_email(self, *, mailbox_id, payload):
    return True


SMTPProvider.send_email = _smoke_send_email

app = create_app(db_url=f"sqlite:///{DB}")
c = TestClient(app, raise_server_exceptions=True)


async def _smoke_safe_preflight(self, domain):
    return PreflightResult(is_safe_to_send=True, failure_reasons=[])


DeliverabilityPreflight.verify_domain = _smoke_safe_preflight


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
tenant_id = r.json()["tenant_id"]

# 2. Me
r = c.get("/api/auth/me", headers=h)
step("auth/me returns tenant", r.json().get("tenant_name") == "Acme Inc")

# 3. Billing plan
r = c.get("/api/billing/plan", headers=h)
step("billing plan = pro trial", r.json()["plan"] == "pro")

# 4. Create campaign
r = c.post("/api/campaigns", json={
    "customer_name": "Outbound Q3", "offer": "AI sales infra. $500/meeting.",
    "icp_description": "B2B founders", "booking_url": "https://cal.com/me",
    "client_cure": "Turns fresh funding triggers into qualified founder meetings.",
    "allowed_signal_types": ["funding_round"],
    "price_per_outcome_cents": 50000, "monthly_budget_cents": 200000,
    "hitl_threshold": 2,
}, headers=h)
step("campaign created", r.status_code == 201)
cid = r.json()["id"]

# 5. Operations readiness
r = c.get("/api/operations/readiness", headers=h)
step("production readiness endpoint green for required checks", r.status_code == 200 and r.json()["is_production_ready"])

# 6. Launch checklist starts blocked until DNS/signal/mailbox are configured.
r = c.get(f"/api/operations/campaigns/{cid}/launch-checklist", headers=h)
blocked = r.status_code == 200 and not r.json()["is_launch_ready"]
step("launch checklist blocks incomplete campaign", blocked)

# Make this smoke campaign pilot-ready using the same public preflight endpoint
# and mailbox primitive the real onboarding/OAuth flows populate.
r = c.post(
    f"/api/operations/campaigns/{cid}/deliverability-preflight",
    json={"domain": "acme.com"},
    headers=h,
)
step("campaign preflight stamps DNS readiness", r.status_code == 200 and r.json()["is_safe_to_send"])
app.state.store.save_mailbox(
    Mailbox(
        id="mbx_smoke",
        tenant_id=tenant_id,
        email_address="founder@acme.com",
        status="active",
    )
)
r = c.post(f"/api/operations/campaigns/{cid}/activate", headers=h)
step("launch checklist activates ready campaign", r.status_code == 200 and r.json()["is_launch_ready"])

# 7. Upload contacts
csv_bytes = b"email,name,company\na@x.com,Alice,Acme\nb@y.com,Bob,Beta\nc@z.com,Carol,Cygnus\n"
r = c.post("/api/contacts/upload", params={"campaign_id": cid},
           files={"file": ("p.csv", csv_bytes, "text/csv")}, headers=h)
step("CSV upload loaded 3", r.json()["loaded"] == 3)

# 8. Cursor pagination
r = c.get("/api/contacts", params={"campaign_id": cid, "limit": 2}, headers=h)
step("contacts page 1 = 2 + has_more", len(r.json()["data"]) == 2 and r.json()["has_more"])
cursor = r.json()["next_cursor"]
r = c.get("/api/contacts", params={"campaign_id": cid, "limit": 2, "cursor": cursor}, headers=h)
step("contacts page 2 = 1, no more", len(r.json()["data"]) == 1 and not r.json()["has_more"])

# 9. Tick (jobs → awaiting approval, hitl_threshold=2)
r = c.post(f"/api/campaigns/{cid}/tick", headers=h)
step("tick ran", r.json()["ok"])
r = c.get(f"/api/campaigns/{cid}", headers=h)
step("jobs awaiting approval", len(r.json()["jobs_awaiting_approval"]) >= 1)

# 10. Approve a job, drain → smart-routed email send (provider stubbed)
job_id = r.json()["jobs_awaiting_approval"][0]["id"]
r = c.post(f"/api/campaigns/{cid}/approve-job/{job_id}", headers=h)
step("job approved", r.json()["ok"])
c.post(f"/api/campaigns/{cid}/drain", headers=h)

# 11. Record a reply (simulating inbound) + inbox
prospect = list(app.state.ops.list_prospects(cid))[0]
app.state.ops.record_reply(engagement_id=cid, prospect_id=prospect.id,
                           snippet="interested, send a link", classification="interested",
                           suggested_reply="Book here: https://cal.com/me")
r = c.get("/api/inbox", params={"campaign_id": cid}, headers=h)
step("inbox shows reply", len(r.json()) == 1 and r.json()[0]["classification"] == "interested")

# 12. Book + qualify a meeting
r = c.post("/api/meetings", json={
    "campaign_id": cid, "prospect_id": prospect.id,
    "scheduled_for": "2026-07-01T15:00:00+00:00",
}, headers=h)
step("meeting booked", r.status_code == 201)
mid = r.json()["id"]
r = c.post(f"/api/meetings/{mid}/status", json={"status": "qualified"}, headers=h)
step("meeting qualified", r.json()["ok"])

# 13. Analytics reflects revenue ($500 = 1 qualified × 50000c)
r = c.get("/api/analytics/dashboard", headers=h)
totals = r.json()["totals"]
step("analytics revenue = $500", totals["total_revenue_cents"] == 50000)
step("analytics qualified = 1", totals["total_qualified"] == 1)

# 14. Mission control + proof package
r = c.get("/api/operations/mission-control", headers=h)
mission = r.json()
step("mission control sees campaign and booked meeting", mission["campaign_count"] >= 1 and mission["booked_meeting_count"] >= 1)
r = c.get(f"/api/operations/campaigns/{cid}/proof-package", headers=h)
proof = r.json()
step("proof package has ROI and outcome", proof["economics"]["revenue_cents"] == 50000 and proof["outcomes"])

# 15. Tenant isolation
r = c.post("/api/auth/signup", json={"email": "intruder@evil.com", "password": "Password1!"})
h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
r = c.get(f"/api/campaigns/{cid}", headers=h2)
step("tenant isolation: intruder gets 404", r.status_code == 404)

# 16. SPA served
r = c.get("/app/")
step("React SPA served at /app/", r.status_code == 200 and 'id="root"' in r.text)

print("\n✨ All E2E steps passed — the SaaS stack works end to end.\n")
pathlib.Path(DB).unlink(missing_ok=True)
