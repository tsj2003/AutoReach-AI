"""
Phase 2 tests.

Cover:
    * Reply / Meeting domain types persist correctly
    * OperationsService behaviour (create / record reply / book meeting / status)
    * PnLService computes revenue from `qualified` meetings only
    * CsvIngestService loads, dedupes, validates
    * Cockpit FastAPI app: every CRUD round-trip via HTTP
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from engine import (
    AdapterRegistry,
    ConsoleEmailAdapter,
    EngineRuntime,
    Meeting,
    OutboundAgentV1,
    Reply,
    open_storage,
)
from engine.services import CsvIngestService, OperationsService, PnLService


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path/'p2.db'}")


@pytest.fixture
def ops_pnl_csv(storage):
    store, events, ledger = storage
    ops = OperationsService(store=store, events=events)
    pnl = PnLService(store=store, ledger=ledger)
    csv_ingest = CsvIngestService(ops)
    return ops, pnl, csv_ingest, store, events, ledger


@pytest.fixture
def cockpit_client(tmp_path):
    db_url = f"sqlite:///{tmp_path/'cockpit.db'}"
    from cockpit import create_app

    app = create_app(db_url=db_url)
    return TestClient(app, raise_server_exceptions=True)


# ───────────────────── Domain types persistence ─────────────────────


def test_reply_roundtrip(storage):
    store, _, _ = storage
    from engine import Engagement

    store.save_engagement(Engagement(id="e", customer_name="X", offer="O", icp_description="I"))
    rep = Reply(
        id="rep_1", engagement_id="e", prospect_id="p_1", job_id="j_1",
        snippet="hi, interested", classification="interested",
        suggested_reply="thanks!", external_message_id="gmail_abc",
    )
    store.save_reply(rep)
    fetched = store.get_reply("rep_1")
    assert fetched.classification == "interested"
    assert fetched.external_message_id == "gmail_abc"
    by_ext = store.get_reply_by_external_id("gmail_abc")
    assert by_ext.id == "rep_1"


def test_meeting_roundtrip(storage):
    store, _, _ = storage
    from engine import Engagement

    store.save_engagement(Engagement(id="e", customer_name="X", offer="O", icp_description="I"))
    when = datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)
    m = Meeting(
        id="mtg_1", engagement_id="e", prospect_id="p_1",
        reply_id=None, scheduled_for=when, status="booked",
    )
    store.save_meeting(m)
    fetched = store.get_meeting("mtg_1")
    assert fetched.scheduled_for == when
    assert fetched.status == "booked"


# ───────────────────── OperationsService ─────────────────────


def test_record_reply_marks_prospect_replied(ops_pnl_csv):
    ops, _, _, store, _, _ = ops_pnl_csv
    eng = ops.create_engagement(customer_name="X", offer="O", icp_description="I")
    p = ops.add_prospect(engagement_id=eng.id, email="x@y.com")
    ops.record_reply(
        engagement_id=eng.id, prospect_id=p.id,
        snippet="ok", classification="interested",
    )
    refreshed = store.get_prospect(p.id)
    assert refreshed.status == "replied"


def test_record_reply_unsubscribe_marks_prospect_unsubscribed(ops_pnl_csv):
    ops, _, _, store, _, _ = ops_pnl_csv
    eng = ops.create_engagement(customer_name="X", offer="O", icp_description="I")
    p = ops.add_prospect(engagement_id=eng.id, email="x@y.com")
    ops.record_reply(
        engagement_id=eng.id, prospect_id=p.id,
        snippet="please remove me", classification="unsubscribe",
    )
    assert store.get_prospect(p.id).status == "unsubscribed"


def test_record_reply_is_idempotent_via_external_id(ops_pnl_csv):
    ops, _, _, _, _, _ = ops_pnl_csv
    eng = ops.create_engagement(customer_name="X", offer="O", icp_description="I")
    p = ops.add_prospect(engagement_id=eng.id, email="x@y.com")
    a = ops.record_reply(engagement_id=eng.id, prospect_id=p.id, snippet="hi", external_message_id="m1")
    b = ops.record_reply(engagement_id=eng.id, prospect_id=p.id, snippet="duplicate", external_message_id="m1")
    assert a.id == b.id  # idempotent


def test_book_meeting_marks_prospect_booked(ops_pnl_csv):
    ops, _, _, store, _, _ = ops_pnl_csv
    eng = ops.create_engagement(customer_name="X", offer="O", icp_description="I",
                                price_per_outcome_cents=50_000)
    p = ops.add_prospect(engagement_id=eng.id, email="x@y.com")
    ops.book_meeting(
        engagement_id=eng.id, prospect_id=p.id,
        scheduled_for=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
    )
    assert store.get_prospect(p.id).status == "booked"


def test_meeting_status_transitions(ops_pnl_csv):
    ops, _, _, store, _, _ = ops_pnl_csv
    eng = ops.create_engagement(customer_name="X", offer="O", icp_description="I")
    p = ops.add_prospect(engagement_id=eng.id, email="x@y.com")
    m = ops.book_meeting(
        engagement_id=eng.id, prospect_id=p.id,
        scheduled_for=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
    )
    assert ops.update_meeting_status(m.id, status="qualified") is True
    assert store.get_meeting(m.id).status == "qualified"
    assert ops.update_meeting_status(m.id, status="bogus") is False


# ───────────────────── PnL service ─────────────────────


def test_pnl_only_qualified_counts_as_revenue(ops_pnl_csv):
    ops, pnl, _, _, _, ledger = ops_pnl_csv
    eng = ops.create_engagement(
        customer_name="X", offer="O", icp_description="I",
        price_per_outcome_cents=50_000, monthly_budget_cents=200_000,
    )
    p1 = ops.add_prospect(engagement_id=eng.id, email="a@x.com")
    p2 = ops.add_prospect(engagement_id=eng.id, email="b@x.com")
    p3 = ops.add_prospect(engagement_id=eng.id, email="c@x.com")
    when = datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)
    m1 = ops.book_meeting(engagement_id=eng.id, prospect_id=p1.id, scheduled_for=when)
    m2 = ops.book_meeting(engagement_id=eng.id, prospect_id=p2.id, scheduled_for=when)
    m3 = ops.book_meeting(engagement_id=eng.id, prospect_id=p3.id, scheduled_for=when)
    ops.update_meeting_status(m1.id, status="qualified")
    ops.update_meeting_status(m2.id, status="no_show")
    # m3 left as booked (pipeline)

    # Add some "cost"
    from engine.core.types import CostEntry
    ledger.debit(CostEntry(id="c1", engagement_id=eng.id, job_id=None, category="llm", amount_cents=500))

    report = pnl.report_for(eng.id)
    assert report.booked_count == 1  # only the still-booked one
    assert report.qualified_count == 1
    assert report.no_show_count == 1
    assert report.cancelled_count == 0
    assert report.revenue_cents == 50_000
    assert report.cost_cents == 500
    assert report.margin_cents == 49_500
    assert report.margin_pct == pytest.approx(0.99)


# ───────────────────── CSV ingest ─────────────────────


def test_csv_ingest_basic(ops_pnl_csv):
    ops, _, csv_ingest, _, _, _ = ops_pnl_csv
    eng = ops.create_engagement(customer_name="X", offer="O", icp_description="I")
    csv_text = """email,full_name,company,title
alice@a.com,Alice,Startup A,Founder
bob@b.com,Bob,Startup B,CEO
not-an-email,Carol,Startup C,
"""
    result = csv_ingest.ingest_text(engagement_id=eng.id, text=csv_text)
    assert result.total_rows == 3
    assert result.loaded == 2
    assert result.skipped_invalid_email == 1
    assert result.errors == []


def test_csv_ingest_dedupe_and_existing(ops_pnl_csv):
    ops, _, csv_ingest, _, _, _ = ops_pnl_csv
    eng = ops.create_engagement(customer_name="X", offer="O", icp_description="I")
    ops.add_prospect(engagement_id=eng.id, email="alice@a.com", full_name="Alice (existing)")
    csv_text = """email,name
alice@a.com,Alice
alice@a.com,Alice DUPE
bob@b.com,Bob
"""
    result = csv_ingest.ingest_text(engagement_id=eng.id, text=csv_text)
    assert result.loaded == 1  # only bob
    assert result.skipped_existing == 1
    assert result.skipped_duplicates == 1


def test_csv_ingest_requires_email_column(ops_pnl_csv):
    ops, _, csv_ingest, _, _, _ = ops_pnl_csv
    eng = ops.create_engagement(customer_name="X", offer="O", icp_description="I")
    result = csv_ingest.ingest_text(engagement_id=eng.id, text="name,company\nAlice,A\n")
    assert result.loaded == 0
    assert any("email" in e for e in result.errors)


# ───────────────────── Cockpit (HTTP) ─────────────────────


def test_cockpit_health(cockpit_client):
    r = cockpit_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_cockpit_root_redirects_to_engagements(cockpit_client):
    r = cockpit_client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/engagements" in r.headers["location"]


def test_cockpit_engagement_create_and_detail_flow(cockpit_client):
    # Create
    r = cockpit_client.post(
        "/engagements",
        data={
            "customer_name": "AutoReach (self)",
            "offer": "AI sales infra",
            "icp_description": "B2B SaaS founders",
            "booking_url": "",
            "monthly_meeting_target": 20,
            "price_per_outcome_cents": 50000,
            "monthly_budget_cents": 100000,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    detail_url = r.headers["location"]
    assert detail_url.startswith("/engagements/")
    eng_id = detail_url.split("/")[-1]

    # Detail page renders
    r = cockpit_client.get(detail_url)
    assert r.status_code == 200
    assert "AutoReach (self)" in r.text
    # Default agent was auto-created
    assert "outbound.v1" in r.text

    # List page shows it with a $0 / $0 P&L
    r = cockpit_client.get("/engagements")
    assert r.status_code == 200
    assert "AutoReach (self)" in r.text


def test_cockpit_prospect_csv_upload(cockpit_client):
    r = cockpit_client.post(
        "/engagements",
        data={
            "customer_name": "Demo",
            "offer": "Demo offer",
            "icp_description": "Demo ICP",
            "booking_url": "",
            "monthly_meeting_target": 10,
            "price_per_outcome_cents": 50000,
            "monthly_budget_cents": 0,
        },
        follow_redirects=False,
    )
    eng_id = r.headers["location"].split("/")[-1]

    csv_bytes = (
        b"email,name,company,title\n"
        b"alice@a.com,Alice,Startup A,Founder\n"
        b"bob@b.com,Bob,Startup B,CEO\n"
        b"not-an-email,Carol,Startup C,\n"
    )
    r = cockpit_client.post(
        f"/engagements/{eng_id}/prospects/upload",
        files={"file": ("p.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200
    assert "loaded <strong>2</strong>" in r.text
    assert "skipped invalid <strong>1</strong>" in r.text


def test_cockpit_full_outbound_loop(cockpit_client, tmp_path):
    # 1. Create engagement
    r = cockpit_client.post(
        "/engagements",
        data={
            "customer_name": "Full Loop",
            "offer": "Cold outbound infra",
            "icp_description": "founders",
            "booking_url": "https://cal.com/x",
            "monthly_meeting_target": 5,
            "price_per_outcome_cents": 50000,
            "monthly_budget_cents": 0,
        },
        follow_redirects=False,
    )
    eng_id = r.headers["location"].split("/")[-1]

    # 2. Upload one prospect
    csv_bytes = b"email,name,company\nfoo@bar.com,Foo,Bar Co\n"
    cockpit_client.post(
        f"/engagements/{eng_id}/prospects/upload",
        files={"file": ("p.csv", csv_bytes, "text/csv")},
    )
    # Find prospect ID via the prospects list page (lazy but real).
    rp = cockpit_client.get(f"/engagements/{eng_id}/prospects")
    assert "foo@bar.com" in rp.text

    # 3. Tick — default agent has hitl_threshold=50, so the job will await approval
    r = cockpit_client.post(f"/engagements/{eng_id}/tick", follow_redirects=False)
    assert r.status_code == 303

    # 4. Detail page shows the awaiting-approval job
    rd = cockpit_client.get(f"/engagements/{eng_id}")
    assert rd.status_code == 200
    assert "HITL approval queue" in rd.text


def test_cockpit_reply_triage_and_meeting_booking(cockpit_client):
    # Create engagement + prospect
    r = cockpit_client.post(
        "/engagements",
        data={
            "customer_name": "Replies",
            "offer": "Offer",
            "icp_description": "ICP",
            "booking_url": "https://cal.com/x",
            "monthly_meeting_target": 0,
            "price_per_outcome_cents": 50000,
            "monthly_budget_cents": 0,
        },
        follow_redirects=False,
    )
    eng_id = r.headers["location"].split("/")[-1]

    cockpit_client.post(
        f"/engagements/{eng_id}/prospects/upload",
        files={"file": ("p.csv", b"email,name\ntarget@startup.com,Target\n", "text/csv")},
    )

    # We need the prospect id — fetch via app state on the ASGI test client
    app = cockpit_client.app
    prospects = list(app.state.ops.list_prospects(eng_id))
    prospect_id = prospects[0].id

    # Record a reply
    r = cockpit_client.post(
        f"/engagements/{eng_id}/replies",
        data={
            "prospect_id": prospect_id,
            "snippet": "hey, interested — send me a calendar link",
            "classification": "interested",
            "suggested_reply": "Awesome — here's my Cal.com link.",
            "external_message_id": "gmail_xyz",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    rep_list = cockpit_client.get(f"/engagements/{eng_id}/replies?status=pending")
    assert "interested" in rep_list.text
    assert "send me a calendar link" in rep_list.text

    # Mark sent
    replies = list(app.state.ops.list_replies(eng_id))
    rep_id = replies[0].id
    r = cockpit_client.post(f"/replies/{rep_id}/send", follow_redirects=False)
    assert r.status_code == 303
    assert app.state.store.get_reply(rep_id).status == "sent"

    # Book meeting
    r = cockpit_client.post(
        f"/engagements/{eng_id}/meetings",
        data={
            "prospect_id": prospect_id,
            "scheduled_for": "2026-06-01T15:00",
            "notes": "intro call",
            "reply_id": rep_id,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    meetings = list(app.state.ops.list_meetings(eng_id))
    assert len(meetings) == 1
    mtg_id = meetings[0].id

    # Qualify it (revenue counts here)
    r = cockpit_client.post(
        f"/meetings/{mtg_id}/status",
        data={"status": "qualified", "notes": "real fit"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Meetings page shows revenue
    page = cockpit_client.get(f"/engagements/{eng_id}/meetings")
    assert page.status_code == 200
    assert "$500.00" in page.text  # qualified × price = $500


def test_cockpit_hitl_approve_drives_send(cockpit_client):
    # Create engagement, then use lower HITL so jobs go through quickly.
    app = cockpit_client.app
    eng = app.state.ops.create_engagement(
        customer_name="HITL Test", offer="Offer", icp_description="ICP",
        price_per_outcome_cents=50_000,
    )
    # Replace default agent (created via cockpit form) by creating a custom one.
    app.state.ops.create_agent(
        engagement_id=eng.id, runner_kind="outbound.v1",
        config={"hitl_threshold": 1, "send_gap_seconds": 0},
    )
    app.state.ops.add_prospect(engagement_id=eng.id, email="x@y.com", full_name="X")
    app.state.ops.add_prospect(engagement_id=eng.id, email="y@z.com", full_name="Y")

    # Tick — should plan 2 jobs; both go to awaiting_approval (threshold=1, sent=0).
    cockpit_client.post(f"/engagements/{eng.id}/tick", follow_redirects=False)
    awaiting = list(app.state.store.list_jobs_by_state("awaiting_approval", engagement_id=eng.id))
    assert len(awaiting) == 2

    # Approve both via HTTP; runtime then drains.
    for job in awaiting:
        cockpit_client.post(f"/jobs/{job.id}/approve", follow_redirects=False)
    cockpit_client.post(f"/engagements/{eng.id}/drain", follow_redirects=False)

    succeeded = list(app.state.store.list_jobs_by_state("succeeded", engagement_id=eng.id))
    assert len(succeeded) == 2
