"""Tests for the 4 self-contained engines, Azure OpenAI wiring, and Gojiberry parity APIs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app


@pytest.fixture
def gb_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_SIGNALS_ENABLED", "1")
    monkeypatch.setenv("AUTOREACH_ENRICHMENT_ENABLED", "1")
    monkeypatch.setenv("AUTOREACH_LEARNING_ENABLED", "1")
    app = create_app(db_url=f"sqlite:///{tmp_path / 'gojiberry_test.db'}")
    return TestClient(app)


def _auth_headers(client: TestClient, email: str = "founder@gojiberry-test.io") -> dict[str, str]:
    res = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "Password123!", "company_name": "Gojiberry Test Co"},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_email_finder_engine_permutations_and_finder():
    from engine.services.email_finder_engine import (
        _infer_pattern_from_known_emails,
        find_and_verify_email,
        generate_email_permutations,
    )

    perms = generate_email_permutations("Sarah Chen", "linear.app")
    assert len(perms) >= 10
    first_email = perms[0][0] if isinstance(perms[0], tuple) else perms[0]["email"]
    first_pat = perms[0][1] if isinstance(perms[0], tuple) else perms[0]["pattern"]
    assert first_email == "sarah.chen@linear.app"
    assert first_pat == "{first}.{last}"

    pattern = _infer_pattern_from_known_emails(["john.doe@linear.app", "jane.roe@linear.app"], "linear.app")
    assert pattern == "{first}.{last}"

    res = find_and_verify_email(
        full_name="Sarah Chen",
        company_domain="linear.app",
        enable_osint=False,
        enable_smtp_probe=False,
    )
    assert res.best_email == "sarah.chen@linear.app"
    assert len(res.alternate_emails) >= 2
    assert res.mail_profile is not None
    assert res.mail_profile.provider == res.mail_profile.mail_provider


def test_company_intel_engine_55_plus_tech_signatures():
    from engine.services.company_intel_engine import (
        _TECH_SIGNATURES,
        fingerprint_technologies_from_artifacts,
    )

    assert len(_TECH_SIGNATURES) >= 55
    sample_html = """
    <html>
      <head>
        <script src="https://js.stripe.com/v3/"></script>
        <script src="https://js.hs-scripts.com/12345.js"></script>
        <script src="https://cdn.segment.com/analytics.js"></script>
        <script src="https://widget.intercom.io/widget/abc"></script>
      </head>
      <body>
        <a href="https://boards.greenhouse.io/acme">Careers</a>
      </body>
    </html>
    """
    techs = fingerprint_technologies_from_artifacts(
        html_blobs=[sample_html],
        headers={"server": "cloudflare", "x-powered-by": "Next.js"},
        txt_records=["v=spf1 include:_spf.google.com ~all"],
    )
    tech_list = techs[0] if isinstance(techs, tuple) else techs
    names = {t["name"] for t in tech_list}
    assert "Stripe" in names
    assert "HubSpot" in names
    assert "Segment" in names
    assert "Intercom" in names
    assert "Cloudflare" in names


def test_visitor_deanonymizer_engine_rdap_and_hostname():
    from engine.services.visitor_deanonymizer_engine import (
        _extract_root_domain_from_hostname,
        _parse_rdap_vcard,
        deanonymize_visitor_ip,
    )

    assert _extract_root_domain_from_hostname("vpn-gw-1.corp.stripe.com") == "stripe.com"
    rdap_sample = {
        "name": "STRIPE-NET",
        "entities": [
            {
                "roles": ["registrant"],
                "vcardArray": [
                    "vcard",
                    [
                        ["fn", {}, "text", "Stripe, Inc."],
                        ["adr", {"label": "San Francisco, CA"}, "text", ["", "", "", "San Francisco", "CA", "", "US"]],
                        ["email", {}, "text", "noc@stripe.com"],
                    ],
                ],
            }
        ],
    }
    parsed = _parse_rdap_vcard(rdap_sample)
    orgs = parsed["org_name"] if isinstance(parsed, dict) else parsed[0]
    assert ("Stripe, Inc." in orgs if isinstance(orgs, list) else orgs == "Stripe, Inc.")

    # Private IP should gracefully return is_corporate=False without network calls
    priv = deanonymize_visitor_ip("127.0.0.1")
    assert priv.is_corporate is False


def test_buying_signal_engine_classification():
    from engine.services.buying_signal_engine import _classify_headline_signal

    sig_type, pts = _classify_headline_signal("Acme raises $45M Series B led by Sequoia", "funding")
    assert sig_type == "RECENT_FUNDING_EVENT"
    assert pts == 3

    sig_type2, pts2 = _classify_headline_signal("Acme appoints new Chief Revenue Officer", "leadership")
    assert sig_type2 == "NEW_DECISION_MAKER"
    assert pts2 == 3


def test_azure_openai_client_wiring(monkeypatch):
    from engine.llm.factory import build_llm_client
    from engine.llm.openai_client import OpenAIClient

    monkeypatch.setenv("AZURE_API_KEY", "test-azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://tarandeepjuneja11-9093-resource.cognitiveservices.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

    client = build_llm_client()
    assert isinstance(client, OpenAIClient)
    assert client.has_api_key is True
    assert client.is_azure is True
    assert "openai/deployments/gpt-4o-mini/chat/completions" in client._chat_completions_url()


def test_gojiberry_full_api_flow(gb_client: TestClient):
    headers = _auth_headers(gb_client)

    # 1. Onboarding analyze-website & prompt templates
    r_pt = gb_client.get("/api/campaigns/prompt-templates", headers=headers)
    assert r_pt.status_code == 200
    assert r_pt.json()["count"] == 18

    # 2. Create & patch campaign with Gojiberry agent config
    r_wb = gb_client.post(
        "/api/onboarding/analyze-website",
        headers=headers,
        json={"url": "https://linear.app"},
    )
    assert r_wb.status_code == 200
    wb_data = r_wb.json()
    assert "company_summary" in wb_data
    assert "value_proposition" in wb_data
    assert "pain_points" in wb_data
    assert "target_job_titles" in wb_data
    assert "recommended_signals" in wb_data
    assert len(wb_data["multichannel_sequence"]) >= 5

    r_camp = gb_client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "Acme RevOps",
            "offer": "We automate intent-driven outbound",
            "icp_description": "VP Sales at B2B SaaS",
            "subject_template": "Quick thought for {first_name}",
            "body_template": "Hi {first_name}, saw {company} is scaling.",
            "reply_mode": "autopilot",
            "message_mode": "ai",
            "tone": "direct",
            "goal": "book_meeting",
            "agent_type": "lookalike",
            "min_lead_score": 2,
            "skip_invitation_after_days": 5,
            "split_linkedin_messages": True,
            "sequence": [{"step": 1, "channel": "linkedin", "template_id": "signal-hook"}],
            "signal_variables": [{"type": "RECENT_FUNDING_EVENT", "keywords": ["Series A"]}],
        },
    )
    assert r_camp.status_code == 201, r_camp.text
    camp = r_camp.json()
    campaign_id = camp["id"]
    assert camp["reply_mode"] == "autopilot"
    assert camp["agent_type"] == "lookalike"
    assert camp["split_linkedin_messages"] is True
    assert camp["subject_template"] == "Quick thought for {first_name}"
    assert len(camp["sequence"]) == 1

    r_patch_settings = gb_client.patch(
        f"/api/campaigns/{campaign_id}/settings",
        headers=headers,
        json={"reply_mode": "hitl", "tone": "professional"},
    )
    assert r_patch_settings.status_code == 200
    assert r_patch_settings.json()["reply_mode"] == "hitl"
    assert r_patch_settings.json()["tone"] == "professional"

    # 3. Signals catalog (21 Gojiberry signals + 10 reject reasons) & lookalikes
    r_cat = gb_client.get("/api/signals/catalog", headers=headers)
    assert r_cat.status_code == 200
    cat_data = r_cat.json()
    assert cat_data["gojiberry_count"] == 21
    assert len(cat_data["reject_reasons"]) == 10

    r_look = gb_client.post(
        "/api/signals/lookalikes",
        headers=headers,
        json={"seed_domains": ["stripe.com"], "limit": 5},
    )
    assert r_look.status_code == 200
    assert r_look.json()["count"] >= 1

    # 4. Contacts + attach buying signal + dual-axis scoring + reject reason
    r_con = gb_client.post(
        "/api/contacts",
        headers=headers,
        json={
            "campaign_id": campaign_id,
            "email": "vp.sales@linear.app",
            "full_name": "Alex Rivera",
            "company": "linear.app",
            "title": "VP of Sales",
        },
    )
    assert r_con.status_code == 201
    pid = r_con.json()["id"]
    assert r_con.json()["scoring"] in (1, 2, 3)

    r_sig = gb_client.post(
        f"/api/contacts/{pid}/signals",
        headers=headers,
        json={
            "signal_type": "RECENT_FUNDING_EVENT",
            "title": "Raised $35M Series B",
            "intent_keyword": "Series B",
            "lead_score": 88,
        },
    )
    assert r_sig.status_code == 200
    sig_contact = r_sig.json()
    assert sig_contact["scoring"] == 3
    assert sig_contact["intent_scoring"] == 3
    assert sig_contact["total_scoring"] == 6

    r_rej = gb_client.post(
        f"/api/contacts/{pid}/reject",
        headers=headers,
        json={"reason": "company_competitor", "fit": "bad_fit", "notes": "Direct competitor"},
    )
    assert r_rej.status_code == 200
    assert r_rej.json()["fit"] == "bad_fit"
    assert r_rej.json()["reject_reason"] == "company_competitor"

    # 5. 15-provider Waterfall Enrichment + Phone + Batch
    r_prov = gb_client.get("/api/enrichment/providers", headers=headers)
    assert r_prov.status_code == 200
    assert r_prov.json()["total_registered"] == 15

    r_enr = gb_client.post(
        f"/api/enrichment/prospect/{pid}",
        headers=headers,
        json={"required_fields": ["email"]},
    )
    assert r_enr.status_code == 200
    assert r_enr.json()["fields"]["email"] == "vp.sales@linear.app"

    r_ph = gb_client.post(f"/api/enrichment/prospect/{pid}/phone", headers=headers, json={"country_code": "+1"})
    assert r_ph.status_code == 200
    assert r_ph.json()["phone"].startswith("+1-")
    assert r_ph.json()["phone_2"].startswith("+1-")

    # 6. Website Visitor De-Anonymization Pixel
    r_js = gb_client.get("/api/visitors/wv.js")
    assert r_js.status_code == 200
    assert "GojiberryVisitors" in r_js.text

    r_sim = gb_client.post(
        "/api/visitors/simulate",
        headers=headers,
        json={"domain": "stripe.com", "page_url": "https://attainly.io/pricing", "campaign_id": campaign_id},
    )
    assert r_sim.status_code == 200
    r_feed = gb_client.get("/api/visitors/feed", headers=headers)
    assert r_feed.status_code == 200
    assert r_feed.json()["total"] >= 1

    # 7. B2B Directory
    r_ind = gb_client.get("/api/directory/industries", headers=headers)
    assert r_ind.status_code == 200
    # Honest contract: the directory is EMPTY until real discovery/reveal populates it.
    # No hardcoded famous-exec rows are served as a live database.
    r_leads = gb_client.post("/api/directory/leads/search", headers=headers, json={"title": "VP"})
    assert r_leads.status_code == 200
    assert r_leads.json()["total"] == 0
    assert r_leads.json()["items"] == []
    # Unknown lead_id must 404 (no seed row to fall back to).
    r_rev_missing = gb_client.post(
        "/api/directory/leads/reveal",
        headers=headers,
        json={"lead_id": "lead_does_not_exist", "reveal_email": True},
    )
    assert r_rev_missing.status_code == 404
    # Reveal a specific person by real name + domain (offline permutation path).
    r_rev = gb_client.post(
        "/api/directory/leads/reveal",
        headers=headers,
        json={
            "first_name": "Sarah",
            "last_name": "Chen",
            "domain": "linear.app",
            "reveal_email": True,
            "extract_phone": False,
        },
    )
    assert r_rev.status_code == 200
    assert "@linear.app" in (r_rev.json()["lead"]["email"] or "")

    # 8. CRM & 29-Tool MCP Catalog
    r_mcp = gb_client.get("/api/crm/mcp-catalog", headers=headers)
    assert r_mcp.status_code == 200
    assert r_mcp.json()["total_tools"] == 29

    r_crm_cfg = gb_client.post(
        "/api/crm/config",
        headers=headers,
        json={
            "hubspot_api_key": "pat-na1-test",
            "attio_api_key": "attio_tok_test",
            "webhook_url": "https://hooks.example.com/gojiberry",
            "webhook_secret": "gb_whsec_test123",
        },
    )
    assert r_crm_cfg.status_code == 200
    assert r_crm_cfg.json()["integrations"]["hubspot"]["enabled"] is True
    assert r_crm_cfg.json()["integrations"]["attio"]["enabled"] is True

    r_crm_test = gb_client.post(
        "/api/crm/test",
        headers=headers,
        json={"provider": "webhook", "secret": "gb_whsec_test123"},
    )
    assert r_crm_test.status_code == 200
    assert r_crm_test.json()["headers"]["x-gojiberry-signature"].startswith("sha256=")
    assert r_crm_test.json()["headers"]["x-autoreach-signature"].startswith("sha256=")
    assert "x-gojiberry-timestamp" in r_crm_test.json()["headers"]

    # 9. 5 Free AI Lead-Magnet Tools
    assert gb_client.post(
        "/api/free-tools/sales-nav-filters",
        json={"offer": "RevOps automation", "target_role": "VP of Sales", "industry": "SaaS"},
    ).status_code == 200
    assert gb_client.post(
        "/api/free-tools/icp-generator",
        json={"company_name": "Attainly", "product_description": "Intent-driven outbound"},
    ).status_code == 200
    assert gb_client.post(
        "/api/free-tools/subject-lines",
        json={"offer": "Intent outbound", "signal_type": "RECENT_FUNDING_EVENT"},
    ).status_code == 200
    assert gb_client.post(
        "/api/free-tools/persona-generator",
        json={"job_title": "CRO", "industry": "B2B SaaS"},
    ).status_code == 200
    assert gb_client.post(
        "/api/free-tools/message-analyser",
        json={"subject": "Quick question", "body": "Hi Sarah, saw your Series B announcement — congrats!"},
    ).status_code == 200
