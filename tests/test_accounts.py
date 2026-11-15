"""Account-first domain grouping."""

from __future__ import annotations

from engine.services.accounts import account_id_for, normalize_company_domain, upsert_account


def test_normalize_company_domain():
    assert normalize_company_domain("https://www.Acme.com/about") == "acme.com"
    assert normalize_company_domain("ada@acme.com") == "acme.com"
    assert normalize_company_domain("not a domain") is None


def test_upsert_account_merges_contacts_same_domain(tmp_path):
    from engine import open_storage, Engagement

    store, _, _ = open_storage(f"sqlite:///{tmp_path / 'acct.db'}")
    store.save_engagement(
        Engagement(id="e1", customer_name="C", offer="O", icp_description="I"),
        tenant_id="t1",
    )
    a1 = upsert_account(store, tenant_id="t1", engagement_id="e1", company_domain="acme.com", company_name="Acme")
    a2 = upsert_account(
        store,
        tenant_id="t1",
        engagement_id="e1",
        company_domain="https://acme.com",
        evidence=[{"signal_type": "funding_round", "summary": "Raised Series A"}],
    )
    assert a1.id == a2.id
    assert a2.id == account_id_for(tenant_id="t1", engagement_id="e1", company_domain="acme.com")
    fetched = store.get_account(a1.id)
    assert fetched.company_domain == "acme.com"
    assert len(fetched.evidence) == 1


def test_accounts_api_lists_contactable(tmp_path):
    from fastapi.testclient import TestClient
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'acct_api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    tok = client.post("/api/auth/signup", json={
        "email": "acct@example.com", "password": "Password1!", "company_name": "Acct Co",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    cid = client.post("/api/campaigns", headers=headers, json={
        "customer_name": "Camp", "offer": "O", "icp_description": "I",
        "monthly_budget_cents": 1000,
    }).json()["id"]
    client.post("/api/contacts", headers=headers, json={
        "campaign_id": cid, "email": "a@acme.com", "full_name": "A", "company": "acme.com",
    })
    client.post("/api/contacts", headers=headers, json={
        "campaign_id": cid, "email": "b@acme.com", "full_name": "B", "company": "https://www.acme.com",
    })
    res = client.get(f"/api/campaigns/{cid}/accounts", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["company_domain"] == "acme.com"
    assert data[0]["contact_count"] == 2
    assert data[0]["contactable_count"] == 2
