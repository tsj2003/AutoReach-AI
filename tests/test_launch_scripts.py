"""Launch tooling: DNS health-check + demo seeder smoke tests."""

from __future__ import annotations

import subprocess
import sys
from urllib import error

import pytest
from fastapi.testclient import TestClient


# ── Task 3: DNS health-check ─────────────────────────────────────────────────


def test_dns_checker_detects_provider_and_classifies(monkeypatch):
    import scripts.verify_dns_health as dns_health

    # Stub the network calls so the test is hermetic + fast.
    def fake_txt(name, retries=2):
        if name == "example.com":
            return ["v=spf1 include:_spf.google.com ~all"]
        if name == "_dmarc.example.com":
            return ["v=DMARC1; p=reject; rua=mailto:dmarc@example.com"]
        return []

    def fake_mx(domain, retries=2):
        return ["1 aspmx.l.google.com"]

    monkeypatch.setattr(dns_health, "_query_txt", fake_txt)
    monkeypatch.setattr(dns_health, "_query_mx", fake_mx)

    result = dns_health.check_domain("example.com")
    assert result.spf_found is True
    assert result.dmarc_found is True
    assert result.mx_provider == "Google Workspace"
    assert result.required_passed is True


def test_dns_checker_flags_missing_spf(monkeypatch):
    import scripts.verify_dns_health as dns_health
    monkeypatch.setattr(dns_health, "_query_txt", lambda n, retries=2: [])
    monkeypatch.setattr(dns_health, "_query_mx", lambda d, retries=2: ["1 aspmx.l.google.com"])
    result = dns_health.check_domain("burner.com")
    assert result.spf_found is False
    assert result.required_passed is False  # missing SPF => not ready


def test_dns_checker_detects_microsoft(monkeypatch):
    import scripts.verify_dns_health as dns_health
    monkeypatch.setattr(dns_health, "_query_txt", lambda n, retries=2: ["v=spf1 -all"] if "_dmarc" not in n else [])
    monkeypatch.setattr(dns_health, "_query_mx", lambda d, retries=2: ["0 contoso.mail.protection.outlook.com"])
    result = dns_health.check_domain("contoso.com")
    assert result.mx_provider == "Microsoft 365"


# -- Live ops launch planner --------------------------------------------------


def test_live_ops_secret_generation_creates_valid_runtime_secrets():
    from cryptography.fernet import Fernet
    from scripts.live_ops_launch import generate_live_ops_secrets

    generated = generate_live_ops_secrets()

    assert set(generated) == {
        "AUTOREACH_JWT_SECRET",
        "AUTOREACH_SESSION_SECRET",
        "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY",
        "CALCOM_WEBHOOK_SECRET",
    }
    assert len(set(generated.values())) == len(generated)
    Fernet(generated["AUTOREACH_CREDENTIAL_ENCRYPTION_KEY"].encode("utf-8"))
    assert all("dev" not in value.lower() for value in generated.values())


def _ready_live_ops_env():
    return {
        "DATABASE_URL": "postgres://db",
        "REDIS_URL": "redis://redis",
        "AUTOREACH_JWT_SECRET": "x" * 40,
        "AUTOREACH_SESSION_SECRET": "y" * 40,
        "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY": "EFONWtQiHXh-5vpx9TVH0qCuVCkqUgJutdYjRM3J_iE=",
        "AUTOREACH_ENABLE_CONSOLE": "0",
        "AUTOREACH_RUNTIME_SMART_DISPATCH": "1",
        "AUTOREACH_WORKER_QUEUES": "engine,maintenance,standard-agents",
        "GEMINI_API_KEY": "gemini-secret",
        "GOOGLE_CLIENT_ID": "google-client",
        "GOOGLE_CLIENT_SECRET": "google-secret",
        "CALCOM_WEBHOOK_SECRET": "cal-secret",
        "AUTOREACH_SMOKE_PASSWORD": "smoke-password",
        "AUTOREACH_PHOENIX_ENDPOINT": "https://phoenix.example.com/v1/traces",
    }


def test_live_ops_plan_fails_closed_when_required_env_missing():
    from scripts.live_ops_launch import build_live_ops_plan

    plan = build_live_ops_plan(
        env={},
        base_url="https://app.example.com",
        domain="example.com",
        smoke_email="smoke@example.com",
    )

    assert plan.is_ready is False
    assert "DATABASE_URL" in plan.missing_required
    assert "CALCOM_WEBHOOK_SECRET" in plan.missing_required
    assert "AUTOREACH_WORKER_QUEUES" in plan.missing_required
    assert "AUTOREACH_PUBLIC_BASE_URL" not in plan.missing_required


def test_live_ops_plan_builds_external_system_urls_and_commands_without_leaking_secrets():
    from scripts.live_ops_launch import build_live_ops_plan, render_plan

    env = _ready_live_ops_env()
    plan = build_live_ops_plan(
        env=env,
        base_url="https://app.example.com/",
        domain="example.com",
        smoke_email="smoke@example.com",
    )
    output = render_plan(plan)

    assert plan.is_ready is True
    assert plan.google_redirect_uri == "https://app.example.com/api/mailboxes/connect/callback"
    assert plan.calcom_webhook_url == "https://app.example.com/webhooks/calcom/booking"
    assert plan.dns_preflight_command == "python3 scripts/verify_dns_health.py example.com --json"
    assert "--exercise-scoped-booking-webhook" in plan.production_smoke_command
    assert '"$CALCOM_WEBHOOK_SECRET"' in plan.production_smoke_command
    assert "tenant_id plus engagement_id or campaign_id" in output
    assert "google-secret" not in output
    assert "cal-secret" not in output
    assert "smoke-password" not in output


# ── Task 4: demo seeder ──────────────────────────────────────────────────────


def test_seed_demo_tenant_populates_everything(tmp_path):
    from scripts.seed_demo_tenant import seed

    db_url = f"sqlite:///{tmp_path / 'seed.db'}"
    result = seed(db_url)

    assert result["mailboxes"] == 3
    assert len(result["campaigns"]) == 2
    assert result["leads"] == 50
    assert result["replies"] == 15
    assert result["access_token"]


def test_seeded_tenant_is_reachable_via_api(tmp_path):
    """The seeded data must be fully usable through the real API the SPA calls."""
    from scripts.seed_demo_tenant import seed, DEMO_EMAIL, DEMO_PASSWORD
    from cockpit import create_app

    db_url = f"sqlite:///{tmp_path / 'seed_api.db'}"
    seed(db_url)

    app = create_app(db_url=db_url)
    c = TestClient(app, raise_server_exceptions=True)

    # Login with seeded credentials.
    r = c.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # Campaigns visible.
    camps = c.get("/api/campaigns", headers=h).json()
    assert len(camps) == 2
    cid = camps[0]["id"]

    # Cursor pagination works on the seeded leads.
    page = c.get(f"/api/contacts?campaign_id={cid}&limit=5", headers=h).json()
    assert len(page["data"]) == 5
    assert page["has_more"] is True

    # Inbox has classified replies; Others folder has orphans.
    inbox = c.get(f"/api/inbox?campaign_id={cid}", headers=h).json()
    assert len(inbox) > 0
    others = c.get("/api/inbox/others", headers=h).json()
    assert len(others) == 2

    # Mailboxes seeded.
    mb = c.get("/api/mailboxes", headers=h).json()
    assert len(mb) == 3


def test_seeded_inbox_covers_multiple_categories(tmp_path):
    from scripts.seed_demo_tenant import seed, DEMO_EMAIL, DEMO_PASSWORD
    from cockpit import create_app

    db_url = f"sqlite:///{tmp_path / 'seed_cat.db'}"
    seed(db_url)
    app = create_app(db_url=db_url)
    c = TestClient(app, raise_server_exceptions=True)
    r = c.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    seen = set()
    for camp in c.get("/api/campaigns", headers=h).json():
        for reply in c.get(f"/api/inbox?campaign_id={camp['id']}", headers=h).json():
            seen.add(reply["classification"])
    # Should span the human-actionable categories (auto is filtered as a non-reply).
    for expected in ("interested", "objection", "not_interested", "out_of_office", "referral", "do_not_contact"):
        assert expected in seen, f"missing category {expected} in seeded inbox"


def test_e2e_saas_smoke_script_runs():
    result = subprocess.run(
        [sys.executable, "scripts/e2e_saas_smoke.py"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "All E2E steps passed" in result.stdout


class _FakeHTTPResponse:
    def __init__(self, payload, *, is_json=True, status=200):
        self._payload = payload
        self._is_json = is_json
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        import json

        if self._is_json:
            return json.dumps(self._payload).encode("utf-8")
        return str(self._payload).encode("utf-8")

    def close(self):
        return None

    def getcode(self):
        return self.status


def _production_smoke_config():
    from scripts.production_smoke import SmokeConfig

    return SmokeConfig(
        base_url="https://example.test",
        email="smoke@example.com",
        password="Password1!",
        company="Smoke Co",
        secret_denylist=("super-secret",),
    )


def _production_smoke_config_with_calcom_secret(*, exercise_scoped_booking_webhook=False):
    from scripts.production_smoke import SmokeConfig

    return SmokeConfig(
        base_url="https://example.test",
        email="smoke@example.com",
        password="Password1!",
        company="Smoke Co",
        secret_denylist=("super-secret",),
        calcom_webhook_secret="cal-secret",
        exercise_scoped_booking_webhook=exercise_scoped_booking_webhook,
    )


def test_production_smoke_success_path():
    from scripts.production_smoke import run_smoke

    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.get_method(), req.full_url))
        if req.full_url.endswith("/healthz"):
            return _FakeHTTPResponse({"ok": True})
        if req.full_url.endswith("/readyz"):
            return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})
        if req.full_url.endswith("/readyz?deep=true"):
            return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})
        if req.full_url.endswith((
            "/engagements",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/oauth/google/start",
            "/oauth/status",
        )):
            return _FakeHTTPResponse({"detail": "Not Found"}, status=404)
        if req.full_url.endswith("/api/operations/readiness"):
            return _FakeHTTPResponse({"detail": "Not authenticated"}, status=401)
        if req.full_url.endswith("/webhooks/calcom/booking"):
            return _FakeHTTPResponse({"detail": "Invalid webhook signature"}, status=401)
        if req.full_url.endswith("/api/auth/signup"):
            return _FakeHTTPResponse({"access_token": "token-123"})
        if req.full_url.endswith("/api/auth/me"):
            return _FakeHTTPResponse({"email": "smoke@example.com"})
        if req.full_url.endswith("/api/operations/readiness?deep=true"):
            return _FakeHTTPResponse({
                "is_production_ready": True,
                "missing_required": [],
                "checks": [
                    {"key": "database_connectivity", "status": "PASS"},
                    {"key": "redis_connectivity", "status": "PASS"},
                    {"key": "celery_worker_queues", "status": "PASS"},
                ],
            })
        if req.full_url.endswith("/app/"):
            return _FakeHTTPResponse('<div id="root"></div>', is_json=False)
        raise AssertionError(f"unexpected URL {req.full_url}")

    steps = run_smoke(_production_smoke_config(), urlopen=fake_urlopen)

    assert "deep readyz ok" in steps
    assert "operations deep readiness ok" in steps
    assert "unsigned booking webhook rejected" in steps
    assert ("POST", "https://example.test/api/auth/signup") in calls
    assert ("POST", "https://example.test/webhooks/calcom/booking") in calls


def test_production_smoke_falls_back_to_login_when_user_exists():
    from scripts.production_smoke import run_smoke

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if req.full_url.endswith("/api/auth/signup"):
            raise error.HTTPError(req.full_url, 409, "Conflict", hdrs=None, fp=_FakeHTTPResponse({"detail": "exists"}))
        if req.full_url.endswith("/api/auth/login"):
            return _FakeHTTPResponse({"access_token": "token-123"})
        if req.full_url.endswith("/api/auth/me"):
            return _FakeHTTPResponse({"email": "smoke@example.com"})
        if req.full_url.endswith("/api/operations/readiness?deep=true"):
            return _FakeHTTPResponse({
                "is_production_ready": True,
                "missing_required": [],
                "checks": [
                    {"key": "database_connectivity", "status": "PASS"},
                    {"key": "redis_connectivity", "status": "PASS"},
                    {"key": "celery_worker_queues", "status": "PASS"},
                ],
            })
        if req.full_url.endswith("/app/"):
            return _FakeHTTPResponse('<div id="root"></div>', is_json=False)
        if req.full_url.endswith((
            "/engagements",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/oauth/google/start",
            "/oauth/status",
        )):
            return _FakeHTTPResponse({"detail": "Not Found"}, status=404)
        if req.full_url.endswith("/api/operations/readiness"):
            return _FakeHTTPResponse({"detail": "Not authenticated"}, status=401)
        if req.full_url.endswith("/webhooks/calcom/booking"):
            return _FakeHTTPResponse({"detail": "Invalid webhook signature"}, status=401)
        return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})

    run_smoke(_production_smoke_config(), urlopen=fake_urlopen)

    assert "https://example.test/api/auth/login" in calls


def test_production_smoke_optionally_probes_signed_webhook():
    from scripts.production_smoke import run_smoke

    webhook_calls = []

    def fake_urlopen(req, timeout):
        if req.full_url.endswith("/webhooks/calcom/booking"):
            signature = req.headers.get("X-cal-signature-256")
            webhook_calls.append(signature)
            if signature:
                return _FakeHTTPResponse({"ok": True, "matched": False}, status=200)
            return _FakeHTTPResponse({"detail": "Invalid webhook signature"}, status=401)
        if req.full_url.endswith("/api/auth/signup"):
            return _FakeHTTPResponse({"access_token": "token-123"})
        if req.full_url.endswith("/api/auth/me"):
            return _FakeHTTPResponse({"email": "smoke@example.com"})
        if req.full_url.endswith("/api/operations/readiness?deep=true"):
            return _FakeHTTPResponse({
                "is_production_ready": True,
                "missing_required": [],
                "checks": [
                    {"key": "database_connectivity", "status": "PASS"},
                    {"key": "redis_connectivity", "status": "PASS"},
                    {"key": "celery_worker_queues", "status": "PASS"},
                ],
            })
        if req.full_url.endswith("/app/"):
            return _FakeHTTPResponse('<div id="root"></div>', is_json=False)
        if req.full_url.endswith((
            "/engagements",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/oauth/google/start",
            "/oauth/status",
        )):
            return _FakeHTTPResponse({"detail": "Not Found"}, status=404)
        if req.full_url.endswith("/api/operations/readiness"):
            return _FakeHTTPResponse({"detail": "Not authenticated"}, status=401)
        return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})

    steps = run_smoke(_production_smoke_config_with_calcom_secret(), urlopen=fake_urlopen)

    assert "signed booking webhook accepted" in steps
    assert webhook_calls[0] is None
    assert webhook_calls[1].startswith("sha256=")


def test_production_smoke_can_exercise_scoped_booking_webhook():
    from scripts.production_smoke import run_smoke

    contact_status = {"p-smoke": "new"}
    deleted_campaigns = []

    def fake_urlopen(req, timeout):
        if req.full_url.endswith("/webhooks/calcom/booking"):
            signature = req.headers.get("X-cal-signature-256")
            if not signature:
                return _FakeHTTPResponse({"detail": "Invalid webhook signature"}, status=401)
            raw_body = req.data.decode("utf-8")
            if "Scoped Booking Smoke Probe" in raw_body:
                contact_status["p-smoke"] = "booked"
                return _FakeHTTPResponse({"ok": True, "matched": True}, status=200)
            return _FakeHTTPResponse({"ok": True, "matched": False}, status=200)
        if req.full_url.endswith("/api/auth/signup"):
            return _FakeHTTPResponse({"access_token": "token-123"})
        if req.full_url.endswith("/api/auth/me"):
            return _FakeHTTPResponse({"email": "smoke@example.com", "tenant_id": "t-smoke"})
        if req.full_url.endswith("/api/campaigns") and req.get_method() == "POST":
            return _FakeHTTPResponse({"id": "cmp-smoke"})
        if req.full_url.endswith("/api/contacts") and req.get_method() == "POST":
            return _FakeHTTPResponse({"id": "p-smoke", "status": "new"})
        if req.full_url.endswith("/api/contacts/p-smoke"):
            return _FakeHTTPResponse({"id": "p-smoke", "status": contact_status["p-smoke"]})
        if req.full_url.endswith("/api/campaigns/cmp-smoke") and req.get_method() == "DELETE":
            deleted_campaigns.append("cmp-smoke")
            return _FakeHTTPResponse("", is_json=False, status=204)
        if req.full_url.endswith("/api/operations/readiness?deep=true"):
            return _FakeHTTPResponse({
                "is_production_ready": True,
                "missing_required": [],
                "checks": [
                    {"key": "database_connectivity", "status": "PASS"},
                    {"key": "redis_connectivity", "status": "PASS"},
                    {"key": "celery_worker_queues", "status": "PASS"},
                ],
            })
        if req.full_url.endswith("/app/"):
            return _FakeHTTPResponse('<div id="root"></div>', is_json=False)
        if req.full_url.endswith((
            "/engagements",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/oauth/google/start",
            "/oauth/status",
        )):
            return _FakeHTTPResponse({"detail": "Not Found"}, status=404)
        if req.full_url.endswith("/api/operations/readiness"):
            return _FakeHTTPResponse({"detail": "Not authenticated"}, status=401)
        return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})

    steps = run_smoke(
        _production_smoke_config_with_calcom_secret(exercise_scoped_booking_webhook=True),
        urlopen=fake_urlopen,
    )

    assert "signed booking webhook accepted" in steps
    assert "scoped booking webhook booked contact" in steps
    assert contact_status["p-smoke"] == "booked"
    assert deleted_campaigns == ["cmp-smoke"]


def test_production_smoke_fails_on_secret_leak():
    from scripts.production_smoke import SmokeFailure, run_smoke

    def fake_urlopen(req, timeout):
        if req.full_url.endswith("/healthz"):
            return _FakeHTTPResponse({"ok": True, "leak": "super-secret"})
        return _FakeHTTPResponse({"ok": True})

    with pytest.raises(SmokeFailure, match="leaked"):
        run_smoke(_production_smoke_config(), urlopen=fake_urlopen)


def test_production_smoke_fails_if_legacy_console_is_exposed():
    from scripts.production_smoke import SmokeFailure, run_smoke

    def fake_urlopen(req, timeout):
        if req.full_url.endswith("/healthz"):
            return _FakeHTTPResponse({"ok": True})
        if req.full_url.endswith("/readyz"):
            return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})
        if req.full_url.endswith("/readyz?deep=true"):
            return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})
        if req.full_url.endswith("/engagements"):
            return _FakeHTTPResponse("<html>legacy console</html>", is_json=False, status=200)
        return _FakeHTTPResponse({"detail": "Not Found"}, status=404)

    with pytest.raises(SmokeFailure, match="legacy console"):
        run_smoke(_production_smoke_config(), urlopen=fake_urlopen)


def test_production_smoke_fails_if_legacy_oauth_is_exposed():
    from scripts.production_smoke import SmokeFailure, run_smoke

    def fake_urlopen(req, timeout):
        if req.full_url.endswith("/healthz"):
            return _FakeHTTPResponse({"ok": True})
        if req.full_url.endswith("/readyz"):
            return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})
        if req.full_url.endswith("/readyz?deep=true"):
            return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})
        if req.full_url.endswith(("/engagements", "/docs", "/redoc", "/openapi.json", "/api/operations/readiness")):
            return _FakeHTTPResponse({"detail": "Not Found"}, status=404)
        if req.full_url.endswith("/oauth/google/start"):
            return _FakeHTTPResponse("<html>Google OAuth</html>", is_json=False, status=200)
        return _FakeHTTPResponse({"detail": "Not Found"}, status=404)

    with pytest.raises(SmokeFailure, match="legacy global OAuth start"):
        run_smoke(_production_smoke_config(), urlopen=fake_urlopen)


def test_production_smoke_fails_if_unsigned_webhook_is_accepted():
    from scripts.production_smoke import SmokeFailure, run_smoke

    def fake_urlopen(req, timeout):
        if req.full_url.endswith("/healthz"):
            return _FakeHTTPResponse({"ok": True})
        if req.full_url.endswith("/readyz"):
            return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})
        if req.full_url.endswith("/readyz?deep=true"):
            return _FakeHTTPResponse({"ok": True, "missing_required": [], "warning_count": 0})
        if req.full_url.endswith((
            "/engagements",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/operations/readiness",
            "/oauth/google/start",
            "/oauth/status",
        )):
            return _FakeHTTPResponse({"detail": "Not Found"}, status=404)
        if req.full_url.endswith("/webhooks/calcom/booking"):
            return _FakeHTTPResponse({"ok": True, "matched": False}, status=200)
        return _FakeHTTPResponse({"detail": "Not Found"}, status=404)

    with pytest.raises(SmokeFailure, match="unsigned booking webhook"):
        run_smoke(_production_smoke_config(), urlopen=fake_urlopen)
