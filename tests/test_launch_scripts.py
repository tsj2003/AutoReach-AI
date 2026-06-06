"""Launch tooling: DNS health-check + demo seeder smoke tests."""

from __future__ import annotations

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
