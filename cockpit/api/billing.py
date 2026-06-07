"""
M5 + Payments — Billing / usage / Razorpay checkout API.

GET  /api/billing/plan      — current plan + limits
GET  /api/billing/usage     — current usage vs limits
GET  /api/billing/config    — is Razorpay configured? (public key + currency)
GET  /api/billing/plans     — purchasable plans with pricing
POST /api/billing/order     — create a Razorpay order for a chosen plan
POST /api/billing/verify    — verify payment signature → upgrade tenant plan

Environment
-----------
    RAZORPAY_KEY_ID         — public key id (safe to send to the browser)
    RAZORPAY_KEY_SECRET     — secret key (server only, never exposed)
    RAZORPAY_CURRENCY       — optional, defaults to "INR"

When the key/secret are unset, the checkout endpoints report "disabled" and the
frontend hides the upgrade buttons — no dead flows.
"""

from __future__ import annotations

import dataclasses
import hmac
import hashlib
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cockpit.api.deps import get_current_user, get_store
from engine.auth import CurrentUser
from engine.policies import get_plan_limits, PLANS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ─── Pricing ────────────────────────────────────────────────────────────────
# Amounts are in the smallest currency unit (paise for INR, cents for USD),
# matching what Razorpay expects for the order `amount`.

PURCHASABLE_PLANS: dict[str, dict] = {
    "starter": {"name": "Starter", "amount": 290000, "blurb": "5 campaigns · 3 mailboxes · 5k leads"},
    "pro": {"name": "Pro", "amount": 790000, "blurb": "25 campaigns · 15 mailboxes · 50k leads"},
}


def _key_id() -> str:
    return os.getenv("RAZORPAY_KEY_ID", "").strip()


def _key_secret() -> str:
    return os.getenv("RAZORPAY_KEY_SECRET", "").strip()


def _currency() -> str:
    return os.getenv("RAZORPAY_CURRENCY", "INR").strip() or "INR"


def _razorpay_enabled() -> bool:
    return bool(_key_id() and _key_secret())


def _client():
    if not _razorpay_enabled():
        raise HTTPException(503, "Payments are not configured on this server")
    try:
        import razorpay
    except ImportError as exc:  # pragma: no cover - dependency present in prod
        raise HTTPException(503, "Razorpay library unavailable") from exc
    return razorpay.Client(auth=(_key_id(), _key_secret()))


# ─── Models ───────────────────────────────────────────────────────────────────


class OrderRequest(BaseModel):
    plan: str


class VerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ─── Plan + usage (existing M5) ────────────────────────────────────────────────


@router.get("/plan")
def get_plan(current_user: CurrentUser = Depends(get_current_user)):
    limits = get_plan_limits(current_user.plan)
    return {
        "plan": limits.plan,
        "limits": {
            "max_campaigns": limits.max_campaigns,
            "max_mailboxes": limits.max_mailboxes,
            "max_leads_total": limits.max_leads_total,
            "max_emails_per_day": limits.max_emails_per_day,
            "personalization": limits.personalization,
        },
    }


@router.get("/usage")
def get_usage(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    limits = get_plan_limits(current_user.plan)
    engagements = list(store.list_engagements(tenant_id=current_user.tenant_id))
    active = [e for e in engagements if e.status != "cancelled"]
    total_leads = sum(
        len(list(store.list_prospects(e.id, limit=10_000))) for e in active
    )
    return {
        "plan": limits.plan,
        "usage": {
            "campaigns": len(active),
            "campaigns_limit": limits.max_campaigns,
            "leads_total": total_leads,
            "leads_limit": limits.max_leads_total,
        },
    }


# ─── Razorpay checkout ──────────────────────────────────────────────────────


@router.get("/config")
def billing_config():
    """Public: lets the SPA decide whether to show upgrade buttons."""
    return {
        "enabled": _razorpay_enabled(),
        "key_id": _key_id(),
        "currency": _currency(),
    }


@router.get("/plans")
def list_plans(current_user: CurrentUser = Depends(get_current_user)):
    """Purchasable plans with pricing + the user's current plan."""
    return {
        "current_plan": current_user.plan,
        "currency": _currency(),
        "plans": [
            {"id": pid, "name": p["name"], "amount": p["amount"], "blurb": p["blurb"]}
            for pid, p in PURCHASABLE_PLANS.items()
        ],
    }


@router.post("/order")
def create_order(
    body: OrderRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    if body.plan not in PURCHASABLE_PLANS:
        raise HTTPException(400, f"Unknown plan '{body.plan}'")

    plan = PURCHASABLE_PLANS[body.plan]
    client = _client()

    # The plan + tenant are recorded in the order notes so we can re-derive the
    # purchase server-side at verify time — never trusting the client.
    order = client.order.create({
        "amount": plan["amount"],
        "currency": _currency(),
        "receipt": f"{current_user.tenant_id}:{body.plan}",
        "notes": {
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.user_id,
            "plan": body.plan,
        },
    })

    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "key_id": _key_id(),
        "plan": body.plan,
        "plan_name": plan["name"],
    }


def _verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Razorpay checkout signature = HMAC_SHA256(order_id|payment_id, secret)."""
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(_key_secret().encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/verify")
def verify_payment(
    body: VerifyRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    if not _razorpay_enabled():
        raise HTTPException(503, "Payments are not configured on this server")

    # 1) Verify the signature binds this order to this payment.
    if not _verify_payment_signature(
        body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature
    ):
        logger.warning("Razorpay signature mismatch for order %s", body.razorpay_order_id)
        raise HTTPException(400, "Payment signature verification failed")

    # 2) Fetch the order from Razorpay (source of truth) — never trust the client
    #    for which plan was bought or who bought it.
    client = _client()
    try:
        order = client.order.fetch(body.razorpay_order_id)
    except Exception as exc:  # razorpay raises various errors
        logger.warning("Could not fetch Razorpay order %s: %s", body.razorpay_order_id, exc)
        raise HTTPException(400, "Could not verify the order with Razorpay") from exc

    notes = order.get("notes") or {}
    order_tenant = notes.get("tenant_id")
    plan = notes.get("plan")

    if order_tenant != current_user.tenant_id:
        raise HTTPException(403, "This order does not belong to your account")
    if plan not in PURCHASABLE_PLANS:
        raise HTTPException(400, "Order has no valid plan")
    if order.get("status") != "paid":
        raise HTTPException(400, f"Order is not paid (status: {order.get('status')})")

    # 3) Upgrade the tenant plan.
    tenant = store.get_tenant(current_user.tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    updated = dataclasses.replace(
        tenant, plan=plan, updated_at=datetime.now(timezone.utc)
    )
    store.save_tenant(updated)
    logger.info("Tenant %s upgraded to plan %s", tenant.id, plan)

    return {"ok": True, "plan": plan, "limits": {
        "max_campaigns": PLANS[plan].max_campaigns,
        "max_mailboxes": PLANS[plan].max_mailboxes,
        "max_leads_total": PLANS[plan].max_leads_total,
    }}
