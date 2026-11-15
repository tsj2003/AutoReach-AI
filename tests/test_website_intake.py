"""Website → campaign config intake (the 3-minute setup).

Tests are fixture-HTML only: rich marketing page, thin login wall, empty body.
No brand-specific branches (no Amazon/Barkat conditionals).
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from cockpit.main import app
from engine.auth.jwt_handler import sign_jwt
from engine.llm.gemini import GeminiResult
from engine.llm.website_intake import (
    WebsiteIntake,
    analyze_website,
    fetch_website_text,
    is_safe_fetch_url,
)
from engine.services.website_analyzer import (
    audience_to_role_types,
    classify_site,
    collect_website_evidence,
    infer_icp_from_evidence,
    sanitize_llm_icp,
)

client = TestClient(app)

RICH_HTML = """
<html lang="en">
  <head>
    <title>InvoiceFlow — GST invoicing for independent shops</title>
    <meta name="description" content="InvoiceFlow helps independent retailers send GST invoices and collect unpaid bills without a full accounting suite." />
    <meta property="og:site_name" content="InvoiceFlow" />
    <script type="application/ld+json">
      {"@type":"SoftwareApplication","name":"InvoiceFlow","applicationCategory":"BusinessApplication",
       "description":"Invoicing software for independent retailers."}
    </script>
  </head>
  <body>
    <h1>Invoicing software for independent shops</h1>
    <p>Create GST invoices, track unpaid bills, and get paid faster. Built for shop owners who do not want a full ERP.</p>
  </body>
</html>
"""

THIN_LOGIN_HTML = """
<html>
  <head><title>Portal</title></head>
  <body>
    <h1>Sign in</h1>
    <form><label>Password</label><input type="password" name="password" /></form>
    <p>Log in to continue.</p>
  </body>
</html>
"""

MARKETPLACE_HTML = """
<html lang="en">
  <head>
    <title>ShopWorld — Online marketplace</title>
    <meta name="description" content="ShopWorld is an online marketplace with millions of products across electronics, fashion, and home." />
  </head>
  <body>
    <h1>Online shopping for electronics, fashion, and home</h1>
    <p>We help you shop from thousands of sellers. Great prices, fast delivery.</p>
  </body>
</html>
"""

B2B_SALES_HTML = """
<html lang="en">
  <head>
    <title>Outboundly — AI outbound for sales teams</title>
    <meta name="description" content="Outboundly helps sales teams reach the right buyers with ICP-matched LinkedIn signals." />
  </head>
  <body>
    <h1>AI outbound software for sales teams</h1>
    <p>Built for sales teams who want more qualified meetings. Unlike Lemlist, we start from buying signals.</p>
  </body>
</html>
"""


def _auth():
    return {"Authorization": "Bearer " + sign_jwt(
        user_id="u", tenant_id="t", email="e@x.co", role="owner", plan="pro")}


def _no_llm():
    class _NoKey:
        has_api_key = False

        def generate_json(self, **kw):  # pragma: no cover
            raise AssertionError("should not be called without a key")

    return _NoKey()


# ── SSRF guard ────────────────────────────────────────────────────────────
def test_ssrf_guard_blocks_internal_and_nonhttp():
    assert not is_safe_fetch_url("http://localhost/")
    assert not is_safe_fetch_url("http://127.0.0.1/")
    assert not is_safe_fetch_url("http://169.254.169.254/latest/meta-data/")
    assert not is_safe_fetch_url("file:///etc/passwd")
    assert not is_safe_fetch_url("http://10.0.0.5/")


def test_fetch_returns_empty_for_unsafe_url():
    assert fetch_website_text("http://127.0.0.1/") == ""


# ── richness + extractive ICP ─────────────────────────────────────────────
def test_role_types_come_from_audience_language_not_saas_pack():
    assert "shop owner" in " ".join(audience_to_role_types("shop owners")).lower()
    assert "independent shop owner" in " ".join(audience_to_role_types("independent shops")).lower()
    assert "sales manager" in " ".join(audience_to_role_types("sales teams")).lower()
    assert audience_to_role_types("you") == []
    assert audience_to_role_types("consumers") == []
    assert audience_to_role_types("businesses") == []
    assert not any("vp revenue" in r.lower() for r in audience_to_role_types("sales teams"))


def test_rich_marketing_site_extracts_pitch_not_saas_exec_pack():
    evidence = collect_website_evidence(
        "https://invoiceflow.example",
        homepage_html=RICH_HTML,
        fetch_extras=False,
    )
    assert evidence.richness == "rich"
    assert classify_site(evidence) == "b2b_product"
    inferred = infer_icp_from_evidence(evidence)
    payload = analyze_website(
        "https://invoiceflow.example",
        client=_no_llm(),
        page_html=RICH_HTML,
    ).as_dict()

    assert payload["company_name"] == "InvoiceFlow"
    titles = " ".join(payload["job_titles"]).lower()
    assert payload["job_titles"] == payload["target_job_titles"]
    assert titles
    assert "shop" in titles or "retail" in titles
    assert "vp revenue" not in titles
    assert "head of sales" not in titles
    desc = (payload["summary"] + " " + payload["offer"]).lower()
    assert "invoice" in desc or "gst" in desc
    assert "growth and prosperity" not in desc
    keywords = [k.lower() for k in payload["search_keywords"]]
    assert any("invoic" in k or "gst" in k or "retail" in k for k in keywords)
    rec_types = {str(s.get("type")) for s in payload["recommended_signals"]}
    assert "SEARCH_KEYWORD" in rec_types
    assert "RECENT_FUNDING_EVENT" not in rec_types
    assert "LOOKALIKE" not in rec_types
    assert payload["ignored_companies"] == payload["competitors"]
    assert payload["multichannel_sequence"]
    assert payload["multichannel_sequence"][0]["type"] == "visitProfile"
    assert len(payload["multichannel_sequence"]) == 5
    # Gojiberry UI defaults are separate from website-derived signals
    event_enabled = {
        s["type"]: s["enabled"] for s in payload["event_signal_defaults"]
    }
    assert event_enabled["RECENT_ACTIVITY"] is True
    assert event_enabled["RECENTLY_CHANGED_JOB"] is True
    assert event_enabled["RECENT_FUNDING_EVENT"] is False
    assert event_enabled["HIRING"] is False
    assert inferred["status"] == "ok"
    assert inferred["product_type"] == "b2b_product"


def test_thin_login_site_is_low_evidence_empty_icp():
    payload = analyze_website(
        "https://app.example.com/login",
        client=_no_llm(),
        page_html=THIN_LOGIN_HTML,
    ).as_dict()
    assert payload["status"] == "low_evidence"
    assert payload["product_type"] == "app_login"
    assert payload["job_titles"] == []
    assert payload["target_job_titles"] == []
    assert payload["search_keywords"] == []
    assert payload["recommended_signals"] == []
    assert payload["need_more_input"]
    assert "cloudflare" in payload["need_more_input"].lower() or "login" in payload["need_more_input"].lower()


def test_empty_html_is_low_evidence():
    payload = analyze_website(
        "https://blank.example",
        client=_no_llm(),
        page_html="",
    ).as_dict()
    assert payload["status"] == "low_evidence"
    assert payload["job_titles"] == []
    assert payload["recommended_signals"] == []
    assert payload["source"] in {"fallback", "evidence"}


def test_marketplace_copy_does_not_become_consumer_shop_icp():
    evidence = collect_website_evidence(
        "https://shopworld.example",
        homepage_html=MARKETPLACE_HTML,
        fetch_extras=False,
    )
    assert classify_site(evidence) == "consumer_marketplace"
    payload = analyze_website(
        "https://shopworld.example",
        client=_no_llm(),
        page_html=MARKETPLACE_HTML,
    ).as_dict()
    titles = " ".join(payload["job_titles"]).lower()
    assert payload["product_type"] == "consumer_marketplace"
    assert "vp revenue" not in titles
    assert "head of sales" not in titles
    offer = (payload["offer"] or payload["summary"] or "").lower()
    assert "growth and prosperity" not in offer
    # Consumer marketplace: empty buyer titles; keywords may come from the page.
    assert payload["job_titles"] == []
    keywords = " ".join(payload["search_keywords"]).lower()
    assert "electronics" in keywords or "fashion" in keywords or "marketplace" in keywords
    event_enabled = {s["type"]: s["enabled"] for s in payload["event_signal_defaults"]}
    assert event_enabled["RECENT_FUNDING_EVENT"] is False
    assert event_enabled["HIRING"] is False


def test_b2b_sales_copy_infers_sales_role_not_vp_revenue():
    payload = analyze_website(
        "https://outboundly.example",
        client=_no_llm(),
        page_html=B2B_SALES_HTML,
    ).as_dict()
    titles = " ".join(payload["job_titles"]).lower()
    assert payload["product_type"] == "b2b_product"
    assert "sales" in titles
    assert "vp revenue" not in titles
    assert "head of sales" not in titles
    assert "lemlist" in " ".join(payload["competitors"]).lower()
    keywords = " ".join(payload["search_keywords"]).lower()
    assert "outbound" in keywords or "linkedin" in keywords or "sales" in keywords


def test_product_blurb_promotes_thin_page_to_usable_pitch():
    payload = analyze_website(
        "https://app.example.com/login",
        client=_no_llm(),
        page_html=THIN_LOGIN_HTML,
        product_blurb="Clinic HR software that runs payroll and rostering for hospital staff.",
    ).as_dict()
    blob = (payload["summary"] + " " + payload["offer"] + " " + " ".join(payload["search_keywords"])).lower()
    assert "hr" in blob or "clinic" in blob or "hospital" in blob or "payroll" in blob
    assert "vp revenue" not in " ".join(payload["job_titles"]).lower()


class _FakeClient:
    has_api_key = True

    def generate_json(self, *, prompt, **kw):
        return GeminiResult(
            data={
                "status": "ok",
                "company_name": "InvoiceFlow",
                "summary": "GST invoicing for independent retailers.",
                "offer": "InvoiceFlow helps independent retailers send GST invoices.",
                "job_titles": ["Shop Owner", "Retail Store Manager"],
                "industries": ["Retail"],
                "search_keywords": ["GST invoicing", "unpaid bills"],
                "target_job_titles": ["Head of Sales", "VP Revenue"],
                "recommended_signals": [
                    {"type": "RECENT_FUNDING_EVENT", "label": "Funding", "value": "true"},
                    {"type": "SEARCH_KEYWORD", "label": "GST invoicing", "value": '"GST invoicing"'},
                ],
            },
            raw_text="{}",
            model="gemini-2.0-flash",
        )


def test_sanitizer_drops_invented_saas_titles_and_funding_on_unrelated_page():
    evidence = collect_website_evidence(
        "https://invoiceflow.example",
        homepage_html=RICH_HTML,
        fetch_extras=False,
    )
    cleaned = sanitize_llm_icp(
        {
            "status": "ok",
            "company_name": "InvoiceFlow",
            "offer": "We help teams grow with outbound automation.",
            "job_titles": ["Head of Sales", "VP Revenue", "Shop Owner"],
            "industries": ["B2B SaaS"],
            "search_keywords": ["GST invoicing"],
            "recommended_signals": [
                {"type": "RECENT_FUNDING_EVENT", "label": "Recent funding", "value": "true"},
                {"type": "SEARCH_KEYWORD", "label": "GST invoicing", "value": '"GST invoicing"'},
            ],
        },
        evidence,
    )
    titles = [t.lower() for t in cleaned["job_titles"]]
    assert "head of sales" not in titles
    assert "vp revenue" not in titles
    assert any("shop" in t for t in titles)


def test_sanitizer_drops_saas_titles_on_marketplace_even_if_llm_invents_them():
    evidence = collect_website_evidence(
        "https://shopworld.example",
        homepage_html=MARKETPLACE_HTML,
        fetch_extras=False,
    )
    cleaned = sanitize_llm_icp(
        {
            "status": "ok",
            "company_name": "ShopWorld",
            "offer": "We help consumers shop.",
            "job_titles": ["VP Revenue", "Head of Sales", "Shop Owner"],
            "industries": ["B2B SaaS"],
            "search_keywords": ["online shopping"],
        },
        evidence,
    )
    assert cleaned["job_titles"] == []
    assert cleaned["product_type"] == "consumer_marketplace"
    rec_types = {str(s.get("type")) for s in cleaned["recommended_signals"]}
    assert "RECENT_FUNDING_EVENT" not in rec_types
    assert "SEARCH_KEYWORD" in rec_types


def test_analyze_uses_llm_when_available():
    with patch("engine.services.website_analyzer.fetch_url_body", return_value=RICH_HTML):
        intake = analyze_website(
            "https://invoiceflow.example",
            client=_FakeClient(),
            page_html=RICH_HTML,
        )
    assert intake.source == "llm"
    assert intake.company_name == "InvoiceFlow"
    assert "invoice" in intake.offer.lower() or "gst" in intake.summary.lower()
    assert "head of sales" not in " ".join(intake.target_job_titles).lower()
    assert "vp revenue" not in " ".join(intake.target_job_titles).lower()
    payload = intake.as_dict()
    assert payload["job_titles"] == payload["target_job_titles"]
    assert payload["search_keywords"]


def test_analyze_falls_back_without_llm_or_fetch():
    intake = analyze_website("https://newco.io", client=_no_llm(), page_html="")
    payload = intake.as_dict()
    assert payload["source"] in {"fallback", "evidence"}
    assert payload["company_name"] == "Newco"
    assert payload["status"] == "low_evidence"
    assert payload["suggested_signal_types"] == []
    assert payload["recommended_signals"] == []
    assert "{first_name}" in payload["subject_template"]


# ── endpoint: auth + wiring ───────────────────────────────────────────────
def test_endpoint_requires_auth():
    r = client.post("/api/onboarding/analyze-website", json={"url": "https://acme.com"})
    assert r.status_code == 401


def test_endpoint_returns_draft_for_authed_user():
    with patch("cockpit.api.onboarding.analyze_website") as mock:
        mock.return_value = WebsiteIntake(
            url="https://acme.com", company_name="Acme", summary="s", offer="o",
            icp_description="i", client_cure="c", suggested_signal_types=[],
            subject_template="quick question, {first_name}", body_template="b", source="llm",
            search_keywords=["cold email"],
        )
        r = client.post("/api/onboarding/analyze-website", json={"url": "https://acme.com"}, headers=_auth())
    assert r.status_code == 200
    data = r.json()
    assert data["company_name"] == "Acme"
    assert data["companyName"] == "Acme"
    assert data["source"] == "llm"
    assert data["job_titles"] == []
    assert data["search_keywords"] == ["cold email"]
    assert data["ignored_companies"] == []
    assert data["event_signal_defaults"]
    assert data["multichannel_sequence"]
