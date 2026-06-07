"""
Razorpay billing endpoints — config gating, order creation, signature
verification, and plan upgrade.

The razorpay SDK is monkeypatched so no real API calls happen. Signature
verification uses the real HMAC against a test secret.
"""

from __future__ import annotations

import hmac
import hashlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_client(tmp_path):
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / 'billing_rzp.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post("/api/auth/signup", json={
        "email": "founder@acme.com", "password": "Password1!", "company_name": "Acme",
    })
    assert r.status_code == 200, r.text
    tokens = r.json()
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    return client, h, tokens


def test_config_disabled_by_default(auth_client, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    client, h, _ = auth_client
    r = client.get("/api/billing/config")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_config_enabled_when_keys_set(auth_client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    client, h, _ = auth_client
    r = client.get("/api/billing/config")
    body = r.json()
    assert body["enabled"] is True
    assert body["key_id"] == "rzp_test_abc"


def test_order_disabled_returns_503(auth_client, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    client, h, _ = auth_client
    r = client.post("/api/billing/order", json={"plan": "pro"}, headers=h)
    assert r.status_code == 503


def test_order_unknown_plan_rejected(auth_client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    client, h, _ = auth_client
    r = client.post("/api/billing/order", json={"plan": "unicorn"}, headers=h)
    assert r.status_code == 400


class _FakeOrders:
    def __init__(self, store):
        self.store = store

    def create(self, data):
        oid = "order_test_1"
        self.store[oid] = {
            "id": oid, "amount": data["amount"], "currency": data["currency"],
            "notes": data["notes"], "status": "created",
        }
        return self.store[oid]

    def fetch(self, oid):
        return self.store[oid]


class _FakeClient:
    _orders_store = {}

    def __init__(self, auth=None):
        self.order = _FakeOrders(_FakeClient._orders_store)


def _patch_razorpay(monkeypatch):
    import razorpay
    _FakeClient._orders_store = {}
    monkeypatch.setattr(razorpay, "Client", _FakeClient)


def _sign(order_id, payment_id, secret):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def test_full_purchase_upgrades_plan(auth_client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    _patch_razorpay(monkeypatch)
    client, h, _ = auth_client

    # Create order for pro.
    r = client.post("/api/billing/order", json={"plan": "pro"}, headers=h)
    assert r.status_code == 200, r.text
    order_id = r.json()["order_id"]

    # Mark the order paid (simulating Razorpay-side state after payment).
    _FakeClient._orders_store[order_id]["status"] = "paid"

    # Verify with a valid signature.
    payment_id = "pay_test_1"
    sig = _sign(order_id, payment_id, "secret123")
    r = client.post("/api/billing/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": sig,
    }, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == "pro"

    # The tenant plan is now pro — a fresh token reflects it.
    login = client.post("/api/auth/login", json={
        "email": "founder@acme.com", "password": "Password1!",
    })
    assert login.json()["plan"] == "pro"


def test_verify_bad_signature_rejected(auth_client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    _patch_razorpay(monkeypatch)
    client, h, _ = auth_client

    r = client.post("/api/billing/order", json={"plan": "starter"}, headers=h)
    order_id = r.json()["order_id"]

    r = client.post("/api/billing/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": "pay_x",
        "razorpay_signature": "deadbeef",
    }, headers=h)
    assert r.status_code == 400


def test_verify_unpaid_order_rejected(auth_client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    _patch_razorpay(monkeypatch)
    client, h, _ = auth_client

    r = client.post("/api/billing/order", json={"plan": "starter"}, headers=h)
    order_id = r.json()["order_id"]
    # leave status as "created" (not paid)
    sig = _sign(order_id, "pay_y", "secret123")
    r = client.post("/api/billing/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": "pay_y",
        "razorpay_signature": sig,
    }, headers=h)
    assert r.status_code == 400


def test_verify_foreign_order_rejected(auth_client, monkeypatch):
    """An order belonging to another tenant must not upgrade my account."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    _patch_razorpay(monkeypatch)
    client, h, _ = auth_client

    # Forge an order in the fake store with a different tenant id.
    _FakeClient._orders_store["order_evil"] = {
        "id": "order_evil", "amount": 790000, "currency": "INR",
        "notes": {"tenant_id": "tnt_someone_else", "plan": "pro"}, "status": "paid",
    }
    sig = _sign("order_evil", "pay_z", "secret123")
    r = client.post("/api/billing/verify", json={
        "razorpay_order_id": "order_evil",
        "razorpay_payment_id": "pay_z",
        "razorpay_signature": sig,
    }, headers=h)
    assert r.status_code == 403
