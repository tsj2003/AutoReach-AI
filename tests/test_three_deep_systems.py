from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from cockpit import create_app
from engine.dispatch.linkedin_provider import (
    LinkedInProvider,
    build_voyager_headers,
    extract_activity_urn,
    extract_public_id,
    split_linkedin_messages_into_conversation,
    strip_jsessionid_quotes,
)
from engine.services.apollo_spider_engine import (
    ApolloSpiderEngine,
    extract_osint_phones_for_domain,
    normalize_phone_e164,
    parse_linkedin_dork_snippet,
)
from engine.services.visitor_deanonymizer_engine import (
    VisitorIdentityGraph,
    compute_behavioral_intent_score,
    compute_browser_fingerprint_hash,
    decode_outbound_visitor_token,
    encode_outbound_visitor_token,
    generate_stitched_outbound_url,
    resolve_5_layer_visitor_identity,
)
from engine.storage.sqlite import SqliteStore


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_SIGNALS_ENABLED", "1")
    monkeypatch.setenv("AUTOREACH_ENRICHMENT_ENABLED", "1")
    monkeypatch.setenv("AUTOREACH_LEARNING_ENABLED", "1")
    db_url = f"sqlite:///{tmp_path / 'three_systems_test.db'}"
    app = create_app(db_url=db_url)
    return TestClient(app), app.state.store


def _register_and_headers(client: TestClient) -> dict[str, str]:
    email = f"founder-{uuid.uuid4().hex[:6]}@autoreach.io"
    r = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": "TestPassword123!",
            "company_name": "AutoReach Deep Systems",
        },
    )
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_system_1_linkedin_voyager_protocol_and_api(app_client):
    client, store = app_client
    headers = _register_and_headers(client)

    # 1. Verify authentic Voyager REST.li 2.0.0 header construction
    assert strip_jsessionid_quotes('"ajax:891273918273"') == "ajax:891273918273"
    v_headers = build_voyager_headers("li_at_secret_cookie", '"ajax:891273918273"')
    assert v_headers["x-restli-protocol-version"] == "2.0.0"
    assert v_headers["csrf-token"] == "ajax:891273918273"
    assert 'li_at=li_at_secret_cookie; JSESSIONID="ajax:891273918273"' in v_headers["Cookie"]

    # 2. Verify URL / URN parsers & multi-bubble message splitter
    assert extract_public_id("https://www.linkedin.com/in/karri-saarinen/") == "karri-saarinen"
    assert (
        extract_activity_urn("https://www.linkedin.com/feed/update/urn:li:activity:7192837192837192837/")
        == "urn:li:activity:7192837192837192837"
    )
    bubbles = split_linkedin_messages_into_conversation("Hey Karri!\n\nLoved Linear's new Asks release.\n\nOpen to a quick chat?")
    assert len(bubbles) == 3

    # 3. Connect LinkedIn seat (Fernet-encrypted cookies in linkedin_seats table)
    r_conn = client.post(
        "/api/linkedin/connect",
        headers=headers,
        json={
            "li_at": "AQEDAR_live_voyager_token_123456",
            "jsession_id": '"ajax:5544332211"',
            "seat_name": "Founder Seat",
        },
    )
    assert r_conn.status_code == 200, r_conn.text
    seat_data = r_conn.json()
    seat_id = seat_data["seat_id"]
    assert seat_data["has_encrypted_cookie"] is True

    r_seats = client.get("/api/linkedin/seats", headers=headers)
    assert r_seats.status_code == 200
    assert r_seats.json()["count"] == 1
    assert r_seats.json()["seats"][0]["id"] == seat_id

    # 4. Execute all 5 LinkedIn multichannel actions via /api/linkedin/execute-action
    for step_type in ("visitProfile", "likePosts", "invitation", "invitationNote", "message"):
        r_act = client.post(
            "/api/linkedin/execute-action",
            headers=headers,
            json={
                "seat_id": seat_id,
                "step_type": step_type,
                "profile_url": "https://www.linkedin.com/in/Guillermo-Rauch",
                "message": "Hi Guillermo!\n\nSaw Vercel's AI SDK launch — congrats!",
                "split_into_conversation": True,
            },
        )
        assert r_act.status_code == 200, r_act.text
        assert r_act.json()["ok"] is True

    # 5. Scrape post engagers and persist buying signals
    r_eng = client.post(
        "/api/linkedin/scrape-post-engagers",
        headers=headers,
        json={
            "seat_id": seat_id,
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:7192837192837192837/",
            "signal_type": "COMPETITOR_ENGAGEMENT",
            "persist_signals": True,
        },
    )
    assert r_eng.status_code == 200, r_eng.text
    eng_data = r_eng.json()
    assert eng_data["count"] >= 2
    assert eng_data["persisted_signals"] >= 2

    # 6. Sync LinkedIn inbox into Unibox 2.0
    r_sync = client.post(
        "/api/linkedin/sync-inbox",
        headers=headers,
        json={"seat_id": seat_id, "count": 10},
    )
    assert r_sync.status_code == 200, r_sync.text
    assert r_sync.json()["ok"] is True


def test_system_2_apollo_spider_and_osint_phones(app_client):
    client, store = app_client
    headers = _register_and_headers(client)

    # 1. Verify LinkedIn dork snippet parser
    parsed = parse_linkedin_dork_snippet(
        url="https://www.linkedin.com/in/elena-rodriguez-vp",
        title_text="Elena Rodriguez - VP of Revenue Operations - Figma | LinkedIn",
        snippet_text="San Francisco Bay Area · Elena Rodriguez · VP of Revenue Operations at Figma.",
        company_domain_hint="figma.com",
    )
    assert parsed is not None
    assert parsed["full_name"] == "Elena Rodriguez"
    assert "VP of Revenue Operations" in parsed["title"]
    assert parsed["company_domain"] == "figma.com"
    assert parsed["seniority"] == "VP"
    assert parsed["department"] in ("Sales & Revenue", "RevOps")

    # 2. Verify E.164 normalization & multi-source OSINT phone extraction
    assert normalize_phone_e164("(415) 890-4321", "+1") == "+14158904321"

    def mock_fetcher(url: str, timeout: float = 6.0, **kwargs) -> str:
        if "contact" in url:
            return """
            <html>
              <script type="application/ld+json">
                {"@context": "https://schema.org", "@type": "Organization",
                 "contactPoint": [{"@type": "ContactPoint", "telephone": "+1 (415) 777-8899", "contactType": "sales"}]}
              </script>
              <a href="tel:+1-415-777-1234">Call Direct Sales</a>
            </html>
            """
        if "rdap.org" in url:
            return '{"vcardArray": ["vcard", [["tel", {}, "uri", "tel:+1-650-555-0199"]]]}'
        if "sec.gov" in url:
            return '{"hits": {"hits": [{"_source": {"file_description": "Registrant telephone: (212) 555-0144"}}]}}'
        return ""

    phones = extract_osint_phones_for_domain(
        "acme-enterprise.io",
        company_name="Acme Enterprise",
        default_country_code="+1",
        http_fetcher=mock_fetcher,
    )
    e164_set = {p.e164 for p in phones}
    assert "+14157778899" in e164_set
    assert "+14157771234" in e164_set
    assert "+16505550199" in e164_set
    assert "+12125550144" in e164_set

    # 3. Run /api/directory/spider/run, /api/directory/leads/search, and /api/directory/phones/osint
    r_spider = client.post(
        "/api/directory/spider/run",
        headers=headers,
        json={
            "company_domain": "linear.app",
            "company_name": "Linear",
            "job_title": "VP",
            "limit": 5,
            "live_crawl": False,
        },
    )
    assert r_spider.status_code == 200, r_spider.text
    assert r_spider.json()["discovered_count"] >= 1
    assert r_spider.json()["index_stats"]["indexed_leads"] >= 8

    r_search = client.post(
        "/api/directory/leads/search",
        headers=headers,
        json={"title": "VP", "verify_smtp": True},
    )
    assert r_search.status_code == 200
    assert r_search.json()["total"] >= 1
    first_lead = r_search.json()["leads"][0]
    assert first_lead["phone"].startswith("+1")

    r_osint = client.post(
        "/api/directory/phones/osint",
        headers=headers,
        json={"domain": "stripe.com", "company_name": "Stripe", "live_crawl": False},
    )
    assert r_osint.status_code == 200
    assert r_osint.json()["primary_phone"].startswith("+1")


def test_system_3_five_layer_visitor_identity_graph(app_client):
    client, store = app_client
    headers = _register_and_headers(client)

    # Create a campaign + prospect so Layer 1 outbound token stitching can resolve the exact prospect
    r_camp = client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "AutoReach AI",
            "offer": "Autonomous outbound engine",
            "icp_description": "VP Sales at B2B SaaS",
            "subject_template": "Hi {first_name}",
            "body_template": "Check out our pricing",
        },
    )
    assert r_camp.status_code == 201
    campaign_id = r_camp.json()["id"]

    r_con = client.post(
        "/api/contacts",
        headers=headers,
        json={
            "campaign_id": campaign_id,
            "email": "christina.cacioppo@vanta.com",
            "full_name": "Christina Cacioppo",
            "company": "vanta.com",
            "title": "CEO",
        },
    )
    assert r_con.status_code == 201
    prospect_id = r_con.json()["id"]

    # Layer 1: Generate a stitched outbound URL with HMAC-signed _ar_vid
    r_stitch = client.post(
        "/api/visitors/stitch-link",
        headers=headers,
        json={
            "target_url": "https://autoreach.ai/pricing",
            "prospect_id": prospect_id,
            "email": "christina.cacioppo@vanta.com",
            "company_domain": "vanta.com",
            "campaign_id": campaign_id,
        },
    )
    assert r_stitch.status_code == 200, r_stitch.text
    stitch_data = r_stitch.json()
    ar_vid = stitch_data["_ar_vid"]
    assert "_ar_vid=" in stitch_data["stitched_url"]

    # Prospect clicks the link from a residential Comcast WFH IP (73.162.88.14)
    device_payload = {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36",
        "screen_resolution": "3456x2234x30",
        "timezone": "America/Los_Angeles",
        "language": "en-US",
        "webgl_renderer": "ANGLE (Apple, Apple M3 Max, OpenGL 4.1)",
        "canvas_hash": "c_vanta_ceo_m3max",
        "platform": "MacIntel",
    }
    r_beacon_l1 = client.post(
        "/api/visitors/beacon",
        json={
            "url": stitch_data["stitched_url"],
            "page_url": "/pricing",
            "ip_override": "73.162.88.14",
            "ar_vid": ar_vid,
            "cookie_visitor_id": "ar_cookie_christina_1",
            "time_on_page_seconds": 95,
            "scroll_depth_pct": 85,
            "cta_clicks": 2,
            **device_payload,
        },
    )
    assert r_beacon_l1.status_code == 200, r_beacon_l1.text
    b1 = r_beacon_l1.json()
    assert b1["identified"] is True
    assert b1["resolution_layer"] == 1
    assert b1["resolution_method"] == "layer1_outbound_click_token"
    assert b1["confidence"] == 1.0
    assert b1["domain"] == "vanta.com"
    assert b1["prospect"]["email"] == "christina.cacioppo@vanta.com"

    # Layer 3: Next day, the same device visits /demo from a mobile hotspot IP (172.56.42.99)
    # WITHOUT any _ar_vid token or email! Should resolve via Layer 3 device fingerprint / cookie!
    r_beacon_l3 = client.post(
        "/api/visitors/beacon",
        json={
            "url": "https://autoreach.ai/demo",
            "page_url": "/demo",
            "ip_override": "172.56.42.99",
            "cookie_visitor_id": "ar_cookie_christina_1",
            "time_on_page_seconds": 140,
            "scroll_depth_pct": 90,
            "cta_clicks": 3,
            **device_payload,
        },
    )
    assert r_beacon_l3.status_code == 200, r_beacon_l3.text
    b3 = r_beacon_l3.json()
    assert b3["identified"] is True
    assert b3["resolution_layer"] == 3
    assert b3["domain"] == "vanta.com"
    assert b3["confidence"] >= 0.92
    assert b3["high_intent_alert"] is True
    assert b3["warmth_score"] >= 70

    # Layer 2: Form / Cal.com email capture from a brand-new visitor on residential Wi-Fi
    r_beacon_l2 = client.post(
        "/api/visitors/beacon",
        json={
            "url": "https://autoreach.ai/book-demo",
            "page_url": "/book-demo",
            "ip_override": "98.210.14.55",
            "email": "olivier.pomel@datadoghq.com",
            "cookie_visitor_id": "ar_cookie_olivier_2",
            "time_on_page_seconds": 65,
            "scroll_depth_pct": 75,
        },
    )
    assert r_beacon_l2.status_code == 200, r_beacon_l2.text
    b2 = r_beacon_l2.json()
    assert b2["identified"] is True
    assert b2["resolution_layer"] == 2
    assert b2["resolution_method"] == "layer2_form_email_stitch"
    assert b2["domain"] == "datadoghq.com"
    assert b2["confidence"] == 0.98

    # Check /api/visitors/identity-graph and /api/visitors/feed
    r_graph = client.get("/api/visitors/identity-graph", headers=headers)
    assert r_graph.status_code == 200
    assert r_graph.json()["stats"]["known_identities"] >= 2

    r_feed = client.get("/api/visitors/feed", headers=headers)
    assert r_feed.status_code == 200
    assert r_feed.json()["total"] >= 2
    assert r_feed.json()["stats"]["layer_breakdown"]["layer_1_outbound_token"] >= 1
    assert r_feed.json()["stats"]["layer_breakdown"]["layer_2_form_email"] >= 1
    assert r_feed.json()["stats"]["layer_breakdown"]["layer_3_fingerprint_graph"] >= 1
