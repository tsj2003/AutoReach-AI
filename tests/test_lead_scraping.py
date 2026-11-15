"""Firecrawl client + scrape-to-leads + the /leads/scrape endpoint."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app
from engine.integrations.firecrawl_client import FirecrawlClient
from engine.services.lead_scraper import ScrapedLead, scrape_leads_from_source


def _resp(obj):
    raw = json.dumps(obj).encode("utf-8")

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _R(raw)


# ── FirecrawlClient ────────────────────────────────────────────────────────
def test_firecrawl_no_key_returns_empty():
    assert FirecrawlClient(api_key="").scrape_markdown("https://x.com") == ""


def test_firecrawl_scrape_returns_markdown():
    c = FirecrawlClient(api_key="fc-test")
    with patch("urllib.request.urlopen", return_value=_resp({"data": {"markdown": "# Acme\nWe sell widgets."}})):
        md = c.scrape_markdown("https://acme.com")
    assert "Acme" in md


def test_firecrawl_failure_returns_empty():
    c = FirecrawlClient(api_key="fc-test")
    with patch("urllib.request.urlopen", side_effect=OSError("down")):
        assert c.scrape_markdown("https://acme.com") == ""


# ── scrape_leads_from_source ───────────────────────────────────────────────
class _FakeFirecrawl:
    has_api_key = True

    def __init__(self, md):
        self._md = md

    def scrape_markdown(self, url, **kw):
        return self._md


class _FakeLLM:
    def __init__(self, leads):
        self._leads = leads

    def generate_json(self, *, prompt, **kw):
        from engine.llm.gemini import GeminiResult
        return GeminiResult(data={"leads": self._leads}, raw_text="{}", model="gpt-4o-mini")


def test_scrape_leads_extracts_candidates():
    leads = scrape_leads_from_source(
        "https://directory.example/list",
        icp="B2B SaaS founders",
        firecrawl=_FakeFirecrawl("# Companies\nAcme, Beta Inc"),
        llm=_FakeLLM([
            {"company": "Acme", "company_domain": "acme.com", "full_name": "Jo", "title": "CEO", "email": "jo@acme.com"},
            {"company": "Beta Inc", "company_domain": "beta.com", "email": ""},
        ]),
    )
    assert len(leads) == 2
    assert leads[0].email == "jo@acme.com"
    assert leads[1].email == ""  # no email found — honest


def test_scrape_leads_empty_without_key():
    class _NoKey:
        has_api_key = False
        def scrape_markdown(self, *a, **k): return ""
    assert scrape_leads_from_source("https://x", icp="x", firecrawl=_NoKey(), llm=_FakeLLM([])) == []


# ── endpoint ───────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 's.db'}"), raise_server_exceptions=True)


def _auth(client):
    r = client.post("/api/auth/signup", json={"email": "s@x.co", "password": "Password1!", "company_name": "S"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_leads_scrape_endpoint_creates_prospects_and_flags_contactable(client):
    h = _auth(client)
    cid = client.post("/api/campaigns", json={
        "customer_name": "A", "offer": "o", "icp_description": "B2B founders",
    }, headers=h).json()["id"]

    fake_leads = [
        ScrapedLead(company="Acme", company_domain="acme.com", full_name="Jo", title="CEO", email="jo@acme.com"),
        ScrapedLead(company="Beta", company_domain="beta.com", email=""),
    ]
    with patch("engine.services.lead_scraper.scrape_leads_from_source", return_value=fake_leads):
        r = client.post(f"/api/campaigns/{cid}/leads/scrape",
                        json={"source_url": "https://directory.example/list"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_count"] == 2
    assert body["with_email"] == 1
    assert body["without_email"] == 1
    contactable = {p["company"]: p["contactable"] for p in body["prospects"]}
    assert contactable == {"Acme": True, "Beta": False}


def test_leads_scrape_requires_auth(client):
    r = client.post("/api/campaigns/x/leads/scrape", json={"source_url": "https://x"})
    assert r.status_code == 401
