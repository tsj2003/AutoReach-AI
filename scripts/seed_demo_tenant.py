#!/usr/bin/env python3
"""
seed_demo_tenant.py — populate the database with a ready-to-demo tenant.

Bypasses real OAuth/SMTP and creates a complete, realistic tenant so you can log
into the React dashboard on production and run a live demo immediately.

Creates:
  * 1 demo user (owner)            login: demo@autoreach.ai / DemoPass123!
  * 3 connected mailboxes          mocked healthy (no real OAuth)
  * 2 active campaigns             each with a 3-step follow-up sequence
  * 50 dummy leads                 spread across the campaigns, varied statuses
  * 15 Unibox replies              spanning all 7 AI categories

Usage
-----
    PYTHONPATH=. python scripts/seed_demo_tenant.py
    PYTHONPATH=. python scripts/seed_demo_tenant.py --db postgresql://... --reset

After seeding, the script prints the demo login + a ready-to-use JWT.
"""

from __future__ import annotations

import argparse
import os
import random
import secrets
import sys
from datetime import datetime, timedelta, timezone

from engine import Agent, Engagement, Prospect, open_storage
from engine.auth import Tenant, User, hash_password, sign_jwt
from engine.auth.mailbox_models import Mailbox
from engine.services import OperationsService

DEMO_EMAIL = "demo@autoreach.ai"
DEMO_PASSWORD = "DemoPass123!"

# All 7 categories the AI reply agent produces.
REPLY_SAMPLES = [
    ("interested", "This looks great — can you send some times for a quick call next week?"),
    ("interested", "We're actively evaluating tools like this. Send a calendar link."),
    ("interested", "Interesting. What does pricing look like for a 10-person team?"),
    ("objection", "We're slammed this quarter — can you follow up in a month?"),
    ("objection", "How is this different from what Smartlead offers?"),
    ("not_interested", "Not a fit for us right now, but thanks for reaching out."),
    ("not_interested", "We just signed with another vendor. Appreciate the note."),
    ("out_of_office", "I'm out of office until 2026-07-15 with limited email access."),
    ("out_of_office", "On parental leave, back 2026-08-01. Please contact ops@ meanwhile."),
    ("referral", "I don't own this — talk to our head of growth, priya@targetco.com."),
    ("referral", "You'll want to reach our CTO on this. Looping in mark@targetco.com."),
    ("do_not_contact", "Remove me from your list and do not contact me again."),
    ("do_not_contact", "Unsubscribe. This is unsolicited."),
    ("auto", "Thank you for your email. This inbox is no longer monitored."),
    ("interested", "Yes — very relevant. How soon could we get started?"),
]

FIRST_NAMES = ["Alex", "Priya", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley",
               "Jamie", "Devon", "Quinn", "Avery", "Noah", "Maya", "Leo"]
COMPANIES = ["Northwind", "Acme Cloud", "Vertex Labs", "BrightForge", "Cobalt", "Lumen IO",
             "Stratus", "Pinecrest", "Halcyon", "Ironclad Data", "Nimbus", "Forge AI"]
TITLES = ["Founder", "VP Engineering", "Head of Growth", "CTO", "Director of Sales", "CEO"]

SEQUENCE = [
    {"subject_template": "Quick question for {first_name}",
     "body_template": "Hi {first_name},\n\n{offer}\n\nWorth a 15-minute look?\n\n— The AutoReach team"},
    {"wait_days": 3, "subject_template": "Re: quick question",
     "body_template": "Hi {first_name}, following up on my note — happy to share a 2-min demo."},
    {"wait_days": 5, "subject_template": "Closing the loop, {first_name}",
     "body_template": "Last note from me — if outbound deliverability is on your radar this quarter, I'm here."},
]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _reset_demo(store) -> None:
    """Remove a prior demo user/tenant so re-seeding is idempotent-ish."""
    existing = store.get_user_by_email(DEMO_EMAIL)
    if existing is None:
        return
    # We don't hard-delete (no destructive cascade in the store API); instead we
    # rename the old demo user's email so the new one is the canonical login.
    from engine.auth.models import User as _User
    stale = _User(
        id=existing.id, tenant_id=existing.tenant_id,
        email=f"stale-{secrets.token_hex(3)}@{DEMO_EMAIL}", password_hash=existing.password_hash,
        full_name=existing.full_name, role=existing.role, is_active=False,
        created_at=existing.created_at, updated_at=datetime.now(timezone.utc),
    )
    store.save_user(stale)


def seed(db_url: str, *, reset: bool = False) -> dict:
    store, events, ledger = open_storage(db_url)
    ops = OperationsService(store=store, events=events)
    now = datetime.now(timezone.utc)

    if reset:
        _reset_demo(store)

    # ── Tenant + user ────────────────────────────────────────────────────
    tenant = Tenant(id=_new_id("tnt"), name="AutoReach Demo Co", plan="pro",
                    created_at=now, updated_at=now)
    store.save_tenant(tenant)

    user = User(
        id=_new_id("usr"), tenant_id=tenant.id, email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD), full_name="Demo Operator",
        role="owner", is_active=True, created_at=now, updated_at=now,
    )
    store.save_user(user)

    # ── 3 mocked-healthy mailboxes ───────────────────────────────────────
    mailbox_specs = [
        ("demo.sales@gmail.com", "gmail", "active", 0),
        ("demo.outreach@gmail.com", "gmail", "active", 8),     # graduated warmup
        ("demo.team@outlook.com", "microsoft", "warming", 2),  # mid-warmup reserve
    ]
    for addr, provider, status, warmup_day in mailbox_specs:
        store.save_mailbox(Mailbox(
            id=_new_id("mbx"), tenant_id=tenant.id, user_id=user.id,
            provider=provider, email_address=addr, display_name=addr,
            credentials_json={"token": "demo-mock", "refresh_token": "demo-mock",
                              "scopes": ["https://www.googleapis.com/auth/gmail.send"]},
            oauth_client_id="demo-client", oauth_client_secret="demo-secret",
            max_emails_per_day=150 if status == "active" else 25,
            emails_sent_today=random.randint(0, 20), warmup_day=warmup_day,
            status=status, reputation_score=random.randint(92, 100),
            created_at=now, updated_at=now,
        ))

    # ── 2 active campaigns with sequences ────────────────────────────────
    campaigns = []
    for name, offer in [
        ("SaaS Founders Q3", "We help B2B teams scale cold outbound without burning domains."),
        ("Agency Outreach", "Deliverability-first cold email infrastructure for agencies."),
    ]:
        eng = ops.create_engagement(
            customer_name=name, offer=offer,
            icp_description="B2B SaaS founders & growth leaders, US/EU, 5-50 employees",
            booking_url="https://cal.com/autoreach-demo/intro",
            monthly_meeting_target=20, price_per_outcome_cents=50000,
            monthly_budget_cents=200000,
        )
        store.save_engagement(eng, tenant_id=tenant.id)
        ops.create_agent(
            engagement_id=eng.id, runner_kind="outbound.v1",
            config={"hitl_threshold": 50, "send_gap_seconds": 90,
                    "personalize": True, "sequence": SEQUENCE},
        )
        campaigns.append(eng)

    # ── 50 dummy leads spread across campaigns ───────────────────────────
    statuses = (["new"] * 18) + (["contacted"] * 22) + (["replied"] * 6) + (["booked"] * 4)
    random.shuffle(statuses)
    all_prospects = []
    for i in range(50):
        eng = campaigns[i % 2]
        fn = random.choice(FIRST_NAMES)
        company = random.choice(COMPANIES)
        p = ops.add_prospect(
            engagement_id=eng.id,
            email=f"{fn.lower()}.{i}@{company.lower().replace(' ', '')}.com",
            full_name=f"{fn} {random.choice(['Lee','Patel','Chen','Reyes','Okoro','Novak'])}",
            company=company, title=random.choice(TITLES),
        )
        # Apply a varied status (add_prospect creates as 'new'; override).
        st = statuses[i]
        if st != "new":
            store.save_prospect(Prospect(
                id=p.id, engagement_id=p.engagement_id, email=p.email,
                full_name=p.full_name, company=p.company, title=p.title,
                raw=p.raw, research=p.research, status=st, created_at=p.created_at,
            ))
        all_prospects.append((eng, store.get_prospect(p.id)))

    # ── 15 Unibox replies across all 7 categories ────────────────────────
    booking = "https://cal.com/autoreach-demo/intro"
    for idx, (classification, snippet) in enumerate(REPLY_SAMPLES):
        eng, prospect = all_prospects[idx % len(all_prospects)]
        suggested = ""
        if classification == "interested":
            suggested = f"Great to hear, {prospect.full_name.split()[0]} — grab a time here: {booking}"
        elif classification == "objection":
            suggested = "Totally understand. I'll keep it brief — would a 10-minute async Loom be easier?"
        elif classification in ("do_not_contact",):
            suggested = "Thanks for letting me know — I've removed you. Best of luck."
        elif classification == "referral":
            suggested = "Appreciate the steer — would you be open to a quick intro?"
        ops.record_reply(
            engagement_id=eng.id, prospect_id=prospect.id, snippet=snippet,
            classification=classification, suggested_reply=suggested,
            external_message_id=f"demo_msg_{idx}",
        )

    # ── A couple of orphaned (Others-folder) replies for the demo ────────
    for j, (from_email, snip) in enumerate([
        ("colleague@northwind.com", "Forwarding from my coworker — is this still available?"),
        ("personal.gmail@gmail.com", "Saw this from my work address, replying from personal. Interested."),
    ]):
        store.save_orphaned_reply(
            id=_new_id("orph"), tenant_id=tenant.id, from_email=from_email,
            from_name=from_email.split("@")[0].title(), subject="Fwd: quick question",
            snippet=snip, external_message_id=f"demo_orph_{j}",
        )

    # ── Issue a ready-to-use JWT for instant login ───────────────────────
    token = sign_jwt(
        user_id=user.id, tenant_id=tenant.id, email=user.email,
        role=user.role, plan=tenant.plan, token_type="access",
    )

    return {
        "tenant_id": tenant.id, "user_id": user.id,
        "login_email": DEMO_EMAIL, "login_password": DEMO_PASSWORD,
        "campaigns": [c.id for c in campaigns], "leads": len(all_prospects),
        "replies": len(REPLY_SAMPLES), "orphaned": 2, "mailboxes": 3,
        "access_token": token,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed a demo tenant for live product demos.")
    parser.add_argument("--db", default=os.getenv("DATABASE_URL") or os.getenv("AUTOREACH_DB")
                        or "sqlite:///autoreach_engine.db", help="database URL")
    parser.add_argument("--reset", action="store_true", help="retire any existing demo user first")
    args = parser.parse_args(argv)

    result = seed(args.db, reset=args.reset)

    print("\n✨ Demo tenant seeded\n")
    print(f"  DB:         {args.db}")
    print(f"  Login:      {result['login_email']} / {result['login_password']}")
    print(f"  Mailboxes:  {result['mailboxes']} (mocked healthy)")
    print(f"  Campaigns:  {len(result['campaigns'])} (3-step sequences)")
    print(f"  Leads:      {result['leads']}")
    print(f"  Replies:    {result['replies']} across all 7 AI categories + {result['orphaned']} orphaned")
    print(f"\n  Ready-to-use access token (Authorization: Bearer …):")
    print(f"  {result['access_token']}\n")
    print("  → Log into /app/login with the credentials above, or paste the token.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
