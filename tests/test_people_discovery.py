"""ICP people discovery fills a campaign without CSV or invented VPs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from engine.services.people_discovery import (
    DiscoveredBuyer,
    PeopleDiscoveryResult,
    discover_people_for_icp,
    icp_from_engagement,
    persist_discovered_people,
    run_campaign_people_discovery,
)


MOCK_SPIDER_PEOPLE = [
    {
        "first_name": "Priya",
        "last_name": "Rao",
        "full_name": "Priya Rao",
        "title": "VP Sales",
        "company_name": "Northwind Analytics",
        "company_domain": "northwind.io",
        "location": "Austin, TX",
        "linkedin_url": "https://www.linkedin.com/in/priya-rao-gtm",
        "discovery_source": "duckduckgo_linkedin_dork",
        "discovery_query": 'site:linkedin.com/in/ "VP Sales" "B2B SaaS"',
    },
    {
        "first_name": "Jonah",
        "last_name": "Kim",
        "full_name": "Jonah Kim",
        "title": "Head of Revenue",
        "company_name": "Harbor Labs",
        "company_domain": "harborlabs.com",
        "location": "San Francisco, CA",
        "linkedin_url": "https://www.linkedin.com/in/jonah-kim-rev",
        "discovery_source": "bing_rss_linkedin_dork",
        "discovery_query": 'site:linkedin.com/in/ "Head of Revenue"',
    },
]


class FakeSpider:
    def __init__(self, people=None):
        self.people = list(people or [])
        self.calls = []

    def discover_icp_people(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.people)


def _auth_client(tmp_path):
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'people_disc.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    res = client.post(
        "/api/auth/signup",
        json={
            "email": "founder@acme-discovery.test",
            "password": "Password1!",
            "full_name": "Ada Founder",
            "company_name": "Acme Discovery",
        },
    )
    assert res.status_code == 200, res.text
    return client, {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_discover_people_for_icp_uses_mocked_spider_and_skips_fake_vps():
    spider = FakeSpider(MOCK_SPIDER_PEOPLE)
    result = discover_people_for_icp(
        job_titles=["VP Sales", "Head of Revenue"],
        search_keywords=["outbound", "intent"],
        industries=["B2B SaaS"],
        locations=["United States"],
        max_results=20,
        spider=spider,
        resolve_emails=False,
        crawl_team_pages=False,
    )
    assert result.status == "complete"
    assert len(result.people) == 2
    assert result.people[0].linkedin_url.endswith("/priya-rao-gtm")
    assert result.people[1].email == ""
    assert spider.calls and spider.calls[0]["invent_missing_title"] is False
    names = " ".join(p.full_name for p in result.people).lower()
    assert "alex rivera" not in names
    assert "eileen" not in names


def test_discover_people_empty_icp_is_honest_not_fake_vps():
    result = discover_people_for_icp(
        job_titles=[],
        search_keywords=[],
        industries=[],
        max_results=20,
        spider=FakeSpider([{"full_name": "Should Not Appear", "linkedin_url": "https://www.linkedin.com/in/nope"}]),
        resolve_emails=False,
        crawl_team_pages=False,
    )
    assert result.status == "needs_icp"
    assert result.people == []
    assert "blurb" in result.message.lower() or "titles" in result.message.lower()


def test_icp_from_engagement_uses_description_when_lists_empty():
    class Eng:
        icp_description = "VP Sales at B2B SaaS using intent data"
        metadata = {}
        icp_filters = {}

    icp = icp_from_engagement(Eng())
    assert icp["job_titles"] == []
    assert icp["search_keywords"] == ["VP Sales at B2B SaaS using intent data"]


def test_icp_from_engagement_ignores_generic_description():
    class Eng:
        icp_description = "unknown"
        metadata = {}
        icp_filters = {}

    icp = icp_from_engagement(Eng())
    assert icp["search_keywords"] == []
    assert icp["job_titles"] == []


def test_pytest_does_not_live_spider_without_stub():
    result = discover_people_for_icp(
        job_titles=["VP Sales"],
        search_keywords=["outbound"],
        industries=["B2B SaaS"],
        spider=None,
        resolve_emails=False,
        crawl_team_pages=False,
    )
    assert result.status == "empty"
    assert result.people == []
    assert "alex rivera" not in result.message.lower()


def test_discover_people_zero_spider_hits_stays_empty():
    result = discover_people_for_icp(
        job_titles=["Director of Billing"],
        search_keywords=["invoicing"],
        industries=["Retail"],
        spider=FakeSpider([]),
        resolve_emails=False,
        crawl_team_pages=False,
    )
    assert result.status == "empty"
    assert result.people == []
    assert "invent" not in result.message.lower()


def test_campaign_create_persists_mocked_spider_results(tmp_path, monkeypatch):
    def fake_discover(**kwargs):
        assert "VP Sales" in kwargs["job_titles"]
        assert "intent data" in kwargs["search_keywords"]
        return PeopleDiscoveryResult(
            people=[
                DiscoveredBuyer(
                    first_name="Priya",
                    last_name="Rao",
                    full_name="Priya Rao",
                    title="VP Sales",
                    company="Northwind Analytics",
                    company_domain="northwind.io",
                    linkedin_url="https://www.linkedin.com/in/priya-rao-gtm",
                    email="priya.rao@northwind.io",
                    discovery_source="duckduckgo_linkedin_dork",
                ),
                DiscoveredBuyer(
                    first_name="Jonah",
                    last_name="Kim",
                    full_name="Jonah Kim",
                    title="Head of Revenue",
                    company="Harbor Labs",
                    company_domain="harborlabs.com",
                    linkedin_url="https://www.linkedin.com/in/jonah-kim-rev",
                    email="",
                    discovery_source="bing_rss_linkedin_dork",
                ),
            ],
            status="complete",
            message="Found 2 buyers from public people search.",
            cap=20,
        )

    monkeypatch.setattr("engine.services.people_discovery.discover_people_for_icp", fake_discover)
    client, headers = _auth_client(tmp_path)
    created = client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "Gojiberry-style Agent",
            "offer": "Intent outbound",
            "icp_description": "VP Sales at B2B SaaS using intent data",
            "target_job_titles": ["VP Sales", "Head of Revenue"],
            "search_keywords": ["intent data", "outbound"],
            "target_industries": ["B2B SaaS"],
            "target_locations": ["United States"],
            "auto_discover_people": True,
            "discovery_cap": 20,
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    disc = created.json().get("people_discovery") or {}
    assert disc.get("status") == "complete"
    assert disc.get("created", disc.get("found")) == 2

    contacts = client.get(f"/api/contacts?campaign_id={campaign_id}", headers=headers)
    assert contacts.status_code == 200
    rows = contacts.json()["data"]
    assert len(rows) == 2
    by_name = {r["full_name"]: r for r in rows}
    assert by_name["Priya Rao"]["email"] == "priya.rao@northwind.io"
    assert by_name["Jonah Kim"]["email"] in (None, "")
    assert by_name["Jonah Kim"]["linkedin_url"] == "https://www.linkedin.com/in/jonah-kim-rev"
    assert not any("alex rivera" in (r.get("full_name") or "").lower() for r in rows)
    assert not any((r.get("title") or "") == "VP of Growth" and "stripe" in (r.get("company") or "").lower() for r in rows)


def test_launch_with_icp_description_only_fills_contacts(tmp_path, monkeypatch):
    def fake_discover(**kwargs):
        assert "VP Sales at B2B SaaS using intent data" in kwargs["search_keywords"]
        return PeopleDiscoveryResult(
            people=[
                DiscoveredBuyer(
                    first_name="Priya",
                    last_name="Rao",
                    full_name="Priya Rao",
                    title="VP Sales",
                    company="Northwind Analytics",
                    company_domain="northwind.io",
                    linkedin_url="https://www.linkedin.com/in/priya-rao-gtm",
                    email="priya.rao@northwind.io",
                )
            ],
            status="complete",
            message="Found 1 buyers from public people search.",
            cap=20,
        )

    monkeypatch.setattr("engine.services.people_discovery.discover_people_for_icp", fake_discover)
    client, headers = _auth_client(tmp_path)
    created = client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "Description-only Agent",
            "offer": "Intent outbound",
            "icp_description": "VP Sales at B2B SaaS using intent data",
            "auto_discover_people": True,
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    assert created.json()["people_discovery"]["status"] == "complete"
    rows = client.get(f"/api/contacts?campaign_id={campaign_id}", headers=headers).json()["data"]
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Priya Rao"
    assert rows[0]["email"] == "priya.rao@northwind.io"


def test_campaign_create_without_titles_does_not_invent_vps(tmp_path):
    client, headers = _auth_client(tmp_path)
    created = client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "Empty ICP Agent",
            "offer": "O",
            "icp_description": "unknown",
            "auto_discover_people": True,
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    disc = created.json().get("people_discovery") or {}
    assert disc.get("status") in {"needs_icp", "empty", "queued"}
    contacts = client.get(f"/api/contacts?campaign_id={campaign_id}", headers=headers).json()["data"]
    assert contacts == []
    summary = client.get(f"/api/contacts/summary?campaign_id={campaign_id}", headers=headers).json()
    assert summary["total"] == 0
    assert "titles" in (summary.get("people_discovery") or {}).get("message", disc.get("message", "")).lower() or \
        "blurb" in (summary.get("people_discovery") or {}).get("message", disc.get("message", "")).lower()


def test_discover_people_endpoint_reruns_with_mocked_spider(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_discover(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return PeopleDiscoveryResult(status="empty", message="No public buyers matched this ICP. Add a product blurb or titles and try again.", cap=20)
        return PeopleDiscoveryResult(
            people=[
                DiscoveredBuyer(
                    first_name="Sam",
                    last_name="Ortiz",
                    full_name="Sam Ortiz",
                    title="Director of Billing",
                    company="Shopkeep",
                    company_domain="shopkeep.test",
                    linkedin_url="https://www.linkedin.com/in/sam-ortiz-billing",
                    email="",
                )
            ],
            status="complete",
            message="Found 1 buyers from public people search.",
            cap=20,
        )

    monkeypatch.setattr("engine.services.people_discovery.discover_people_for_icp", fake_discover)
    client, headers = _auth_client(tmp_path)
    created = client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "Retail Billing Agent",
            "offer": "Invoicing",
            "icp_description": "Directors of billing at retail",
            "target_job_titles": ["Director of Billing"],
            "search_keywords": ["invoicing"],
            "auto_discover_people": True,
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    assert created.json()["people_discovery"]["status"] == "empty"
    assert client.get(f"/api/contacts?campaign_id={campaign_id}", headers=headers).json()["data"] == []

    rerun = client.post(
        f"/api/campaigns/{campaign_id}/discover-people",
        headers=headers,
        json={"job_titles": ["Director of Billing"], "search_keywords": ["invoicing"]},
    )
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["created_count"] == 1
    rows = client.get(f"/api/contacts?campaign_id={campaign_id}", headers=headers).json()["data"]
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Sam Ortiz"
    assert rows[0]["linkedin_url"] == "https://www.linkedin.com/in/sam-ortiz-billing"
    assert not rows[0]["email"]


def test_persist_caps_first_run_at_twenty(tmp_path):
    from cockpit import create_app
    from engine.auth.jwt_handler import decode_jwt

    app = create_app(db_url=f"sqlite:///{tmp_path / 'cap.db'}")
    store = app.state.store
    ops = app.state.ops
    client = TestClient(app, raise_server_exceptions=True)
    signup = client.post(
        "/api/auth/signup",
        json={"email": "cap@test.io", "password": "Password1!", "company_name": "Cap Co"},
    )
    tenant_id = decode_jwt(signup.json()["access_token"])["tenant_id"]
    eng = ops.create_engagement(customer_name="Cap", offer="O", icp_description="I")
    store.save_engagement(eng, tenant_id=tenant_id)
    people = [
        DiscoveredBuyer(
            first_name=f"Lead{i}",
            last_name="Buyer",
            full_name=f"Lead{i} Buyer",
            title="VP Sales",
            company=f"Co{i}",
            company_domain=f"co{i}.example",
            linkedin_url=f"https://www.linkedin.com/in/lead-{i}-buyer",
        )
        for i in range(40)
    ]
    result = persist_discovered_people(
        store,
        tenant_id=tenant_id,
        campaign_id=eng.id,
        people=people,
        cap=20,
        plan="pro",
    )
    assert result["created"] == 20
    saved = list(store.list_prospects(eng.id, limit=100))
    assert len(saved) == 20


def test_run_campaign_discovery_with_spider_stub(tmp_path):
    from engine.auth.jwt_handler import decode_jwt

    client, headers = _auth_client(tmp_path)
    token = headers["Authorization"].split(" ", 1)[1]
    tenant_id = decode_jwt(token)["tenant_id"]
    created = client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "Run",
            "offer": "O",
            "icp_description": "I",
            "target_job_titles": ["VP Sales"],
            "auto_discover_people": False,
        },
    )
    campaign_id = created.json()["id"]
    store = client.app.state.store
    result = run_campaign_people_discovery(
        store,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        cap=20,
        spider=FakeSpider(MOCK_SPIDER_PEOPLE),
        resolve_emails=False,
        crawl_team_pages=False,
    )
    assert result["status"] == "complete"
    assert result["created"] == 2
    prospects = list(store.list_prospects(campaign_id, limit=50))
    assert len(prospects) == 2
    assert {p.full_name for p in prospects} == {"Priya Rao", "Jonah Kim"}
