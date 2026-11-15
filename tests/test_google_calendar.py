"""Google Calendar freebusy + book event (mocked Google API)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from engine import Engagement, Prospect, open_storage
from engine.adapters.google_scopes import (
    CALENDAR_EVENTS,
    CALENDAR_FREEBUSY,
    GOOGLE_MAILBOX_SCOPES,
    GMAIL_SEND,
    has_calendar_scopes,
)
from engine.auth.mailbox_models import Mailbox
from engine.services.google_calendar import (
    CalendarNotConnected,
    GoogleCalendarService,
    format_slots_for_reply,
)


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path / 'gcal.db'}")


@pytest.fixture
def auth_client(tmp_path):
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'gcal_api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post(
        "/api/auth/signup",
        json={"email": "cal@acme.com", "password": "Password1!", "company_name": "Acme"},
    )
    return client, r.json()


def _mailbox(store, tenant_id: str, *, with_calendar: bool = True) -> Mailbox:
    now = datetime.now(timezone.utc)
    scopes = list(GOOGLE_MAILBOX_SCOPES) if with_calendar else [GMAIL_SEND]
    mb = Mailbox(
        id="mbx_cal",
        tenant_id=tenant_id,
        email_address="seller@gmail.com",
        credentials_json={
            "token": "access",
            "refresh_token": "refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "cid",
            "client_secret": "csec",
            "scopes": scopes,
        },
        oauth_client_id="cid",
        oauth_client_secret="csec",
        status="active",
        created_at=now,
        updated_at=now,
    )
    store.save_mailbox(mb)
    return mb


def test_has_calendar_scopes_helper():
    assert has_calendar_scopes([CALENDAR_EVENTS, GMAIL_SEND]) is True
    assert has_calendar_scopes([GMAIL_SEND]) is False
    assert CALENDAR_FREEBUSY in GOOGLE_MAILBOX_SCOPES


def test_status_needs_reconsent_without_calendar_scope(storage):
    store, _, _ = storage
    _mailbox(store, "t1", with_calendar=False)
    status = GoogleCalendarService(store=store, tenant_id="t1").status()
    assert status["connected"] is False
    assert status["needs_reconsent"] is True
    assert status["email"] == "seller@gmail.com"


def test_status_connected_with_calendar_scope(storage):
    store, _, _ = storage
    _mailbox(store, "t1", with_calendar=True)
    status = GoogleCalendarService(store=store, tenant_id="t1").status()
    assert status["connected"] is True
    assert status["email"] == "seller@gmail.com"
    assert CALENDAR_EVENTS in status["scopes"]


def test_list_free_slots_skips_busy(storage):
    store, _, _ = storage
    _mailbox(store, "t1", with_calendar=True)
    svc = GoogleCalendarService(store=store, tenant_id="t1")

    # Fixed "now": Monday 2026-06-01 12:00 UTC → 08:00 America/New_York
    fixed_now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    busy_start = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)  # 10:00 ET
    busy_end = datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)

    fake_service = MagicMock()
    fake_service.freebusy().query().execute.return_value = {
        "calendars": {
            "primary": {
                "busy": [
                    {
                        "start": busy_start.isoformat().replace("+00:00", "Z"),
                        "end": busy_end.isoformat().replace("+00:00", "Z"),
                    }
                ]
            }
        }
    }

    with patch.object(svc, "_credentials", return_value=object()), patch(
        "engine.services.google_calendar._build_calendar_service",
        return_value=fake_service,
    ):
        slots = svc.list_free_slots(
            days=2,
            slot_minutes=30,
            max_slots=6,
            timezone_name="America/New_York",
            now=fixed_now,
        )

    assert slots
    for s in slots:
        # No slot may overlap the busy hour.
        assert not (s.start < busy_end and s.end > busy_start)
    assert format_slots_for_reply(slots[:2])


def test_book_event_creates_meet_and_send_updates(storage):
    store, _, _ = storage
    _mailbox(store, "t1", with_calendar=True)
    svc = GoogleCalendarService(store=store, tenant_id="t1")

    start = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)

    insert_mock = MagicMock()
    insert_mock.execute.return_value = {
        "id": "evt_123",
        "htmlLink": "https://calendar.google.com/event?eid=evt_123",
        "hangoutLink": "https://meet.google.com/abc-defg-hij",
        "conferenceData": {
            "entryPoints": [
                {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"}
            ]
        },
    }
    fake_service = MagicMock()
    fake_service.events().insert.return_value = insert_mock

    with patch.object(svc, "_credentials", return_value=object()), patch(
        "engine.services.google_calendar._build_calendar_service",
        return_value=fake_service,
    ):
        booked = svc.book_event(
            prospect_email="prospect@example.com",
            prospect_name="Pat Prospect",
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
            title="Attainly intro",
            create_meet=True,
        )

    assert booked.event_id == "evt_123"
    assert "meet.google.com" in booked.meet_link
    kwargs = fake_service.events().insert.call_args.kwargs
    assert kwargs["sendUpdates"] == "all"
    assert kwargs["conferenceDataVersion"] == 1
    assert kwargs["body"]["attendees"][0]["email"] == "prospect@example.com"


def test_book_requires_calendar_connection(storage):
    store, _, _ = storage
    svc = GoogleCalendarService(store=store, tenant_id="t1")
    with pytest.raises(CalendarNotConnected):
        svc.book_event(
            prospect_email="a@b.com",
            start_iso="2026-06-02T15:00:00+00:00",
            end_iso="2026-06-02T15:30:00+00:00",
        )


def test_calendar_status_api(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.get("/api/calendar/status", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is False
    assert "scopes" in body


def test_calendar_connect_start_returns_auth_url(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "env-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "env-client-secret")
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "1")
    monkeypatch.delenv("AUTOREACH_PUBLIC_BASE_URL", raising=False)

    r = client.post("/api/calendar/connect/start", json={
        "redirect_uri": "http://127.0.0.1:8765/api/calendar/connect/callback",
    }, headers=h)
    assert r.status_code == 200
    assert "accounts.google.com" in r.json()["authorization_url"]
    assert "calendar.events" in r.json()["authorization_url"] or "calendar" in str(
        r.json().get("scopes", [])
    )


def test_mailboxes_connect_requests_calendar_scope(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "env-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "env-client-secret")
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "1")
    monkeypatch.delenv("AUTOREACH_PUBLIC_BASE_URL", raising=False)
    r = client.post("/api/mailboxes/connect/start", json={
        "redirect_uri": "http://127.0.0.1:8765/api/mailboxes/connect/callback",
    }, headers=h)
    assert r.status_code == 200
    # Scope is URL-encoded in the auth URL.
    assert "calendar.events" in r.json()["authorization_url"]


def test_inbox_book_meeting_persists_meta(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    app = client.app
    store = app.state.store
    me = client.get("/api/auth/me", headers=h).json()
    tenant_id = me["tenant_id"]

    _mailbox(store, tenant_id, with_calendar=True)
    now = datetime.now(timezone.utc)
    store.save_engagement(
        Engagement(
            id="eng_1",
            customer_name="Acme",
            offer="Demo",
            icp_description="ICP",
            booking_url="",
        ),
        tenant_id=tenant_id,
    )
    store.save_prospect(
        Prospect(
            id="p_1",
            engagement_id="eng_1",
            email="prospect@example.com",
            full_name="Pat Prospect",
            company="ExCo",
            title="VP",
            status="replied",
            created_at=now,
        )
    )
    from engine.core.types import Reply

    store.save_reply(
        Reply(
            id="r_1",
            engagement_id="eng_1",
            prospect_id="p_1",
            job_id=None,
            snippet="Sure, let's meet next week",
            classification="interested",
            suggested_reply="Happy to book time",
            status="pending",
            received_at=now,
        )
    )

    start = datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)

    with patch(
        "engine.services.google_calendar.GoogleCalendarService.list_free_slots"
    ) as mock_slots, patch(
        "engine.services.google_calendar.GoogleCalendarService.book_event"
    ) as mock_book:
        from engine.services.google_calendar import BookedEvent, FreeSlot

        mock_slots.return_value = [
            FreeSlot(start=start, end=end, timezone="UTC")
        ]
        mock_book.return_value = BookedEvent(
            event_id="evt_99",
            html_link="https://calendar.google.com/event?eid=evt_99",
            meet_link="https://meet.google.com/xyz-abcd-efg",
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
        )
        r = client.post("/api/inbox/r_1/book-meeting", json={}, headers=h)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["gcal_event_id"] == "evt_99"
    assert "meet.google.com" in body["meet_link"]

    prospect = store.get_prospect("p_1")
    assert prospect.status == "booked"
    assert prospect.raw["gcal_event_id"] == "evt_99"
    assert prospect.raw["meet_link"]
    assert prospect.raw["meeting_booked_at"]

    inbox = client.get("/api/inbox?campaign_id=eng_1", headers=h)
    assert inbox.status_code == 200
    row = next(x for x in inbox.json() if x["id"] == "r_1")
    assert row["gcal_event_id"] == "evt_99"
