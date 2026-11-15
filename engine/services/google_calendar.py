"""Google Calendar free/busy + event booking for Attainly Unibox.

Uses the same encrypted mailbox OAuth credentials as Gmail (DbTokenStore).
Creates events on the primary calendar with optional Google Meet and
sendUpdates=all so the prospect receives a Calendar invite email.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from engine.adapters.db_token_store import DbTokenStore
from engine.adapters.google_scopes import has_calendar_scopes, normalize_scopes
from engine.auth.mailbox_models import Mailbox

logger = logging.getLogger(__name__)


class CalendarNotConnected(RuntimeError):
    """No mailbox with Calendar scopes for this tenant."""


class CalendarApiError(RuntimeError):
    """Google Calendar API call failed."""


@dataclass(frozen=True)
class FreeSlot:
    start: datetime
    end: datetime
    timezone: str

    def to_dict(self) -> dict[str, str]:
        return {
            "start_iso": self.start.isoformat(),
            "end_iso": self.end.isoformat(),
            "timezone": self.timezone,
        }


@dataclass(frozen=True)
class BookedEvent:
    event_id: str
    html_link: str
    meet_link: str
    start_iso: str
    end_iso: str
    hangout_link: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "html_link": self.html_link,
            "meet_link": self.meet_link or self.hangout_link,
            "hangout_link": self.hangout_link,
            "start_iso": self.start_iso,
            "end_iso": self.end_iso,
        }


def mailbox_scopes(mailbox: Mailbox) -> list[str]:
    info = dict(mailbox.credentials_json or {})
    return normalize_scopes(info.get("scopes"))


def find_calendar_mailbox(store, tenant_id: str) -> Optional[Mailbox]:
    """Return the first active mailbox that has Calendar event scope."""
    for m in store.list_mailboxes(tenant_id):
        if m.status in ("revoked",):
            continue
        if has_calendar_scopes(mailbox_scopes(m)):
            return m
    return None


def _parse_dt(value: str | datetime, *, default_tz: str = "UTC") -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = (value or "").strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(default_tz))
        except Exception:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_calendar_service(creds):
    from googleapiclient.discovery import build  # type: ignore

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


class GoogleCalendarService:
    """Free/busy lookup + event creation against a tenant mailbox."""

    def __init__(self, *, store, tenant_id: str, mailbox_id: str | None = None) -> None:
        self._store = store
        self._tenant_id = tenant_id
        self._mailbox_id = mailbox_id

    def resolve_mailbox(self) -> Mailbox:
        if self._mailbox_id:
            m = self._store.get_mailbox(self._mailbox_id)
            if m is None or m.tenant_id != self._tenant_id:
                raise CalendarNotConnected("mailbox not found for tenant")
            if m.status == "revoked":
                raise CalendarNotConnected("mailbox revoked — reconnect Calendar")
            if not has_calendar_scopes(mailbox_scopes(m)):
                raise CalendarNotConnected(
                    "mailbox connected without Calendar scopes — reconnect Calendar"
                )
            return m
        m = find_calendar_mailbox(self._store, self._tenant_id)
        if m is None:
            raise CalendarNotConnected(
                "Google Calendar not connected — complete Calendar OAuth first"
            )
        return m

    def _credentials(self, mailbox: Mailbox):
        return DbTokenStore(store=self._store, mailbox_id=mailbox.id).load()

    def status(self) -> dict[str, Any]:
        mailboxes = [
            m
            for m in self._store.list_mailboxes(self._tenant_id)
            if m.status != "revoked"
        ]
        cal = find_calendar_mailbox(self._store, self._tenant_id)
        gmail = mailboxes[0] if mailboxes else None
        scopes = mailbox_scopes(cal) if cal else (mailbox_scopes(gmail) if gmail else [])
        return {
            "connected": cal is not None,
            "email": cal.email_address if cal else (gmail.email_address if gmail else None),
            "mailbox_id": cal.id if cal else (gmail.id if gmail else None),
            "scopes": scopes,
            "has_gmail": gmail is not None,
            "needs_reconsent": gmail is not None and cal is None,
            "calendar_id": "primary",
        }

    def list_free_slots(
        self,
        *,
        days: int = 7,
        slot_minutes: int = 30,
        max_slots: int = 8,
        timezone_name: str = "America/New_York",
        workday_start_hour: int = 9,
        workday_end_hour: int = 17,
        now: datetime | None = None,
    ) -> list[FreeSlot]:
        mailbox = self.resolve_mailbox()
        creds = self._credentials(mailbox)
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("UTC")
            timezone_name = "UTC"

        now_utc = now or datetime.now(timezone.utc)
        local_now = now_utc.astimezone(tz)
        window_start = local_now.replace(minute=0, second=0, microsecond=0)
        if window_start < local_now:
            window_start += timedelta(hours=1)
        window_end = (local_now + timedelta(days=max(1, days))).replace(
            hour=workday_end_hour, minute=0, second=0, microsecond=0
        )

        service = _build_calendar_service(creds)
        body = {
            "timeMin": window_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeMax": window_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeZone": timezone_name,
            "items": [{"id": "primary"}],
        }
        try:
            fb = service.freebusy().query(body=body).execute()
        except Exception as exc:
            raise CalendarApiError(f"freebusy query failed: {exc}") from exc

        busy_raw = (
            ((fb or {}).get("calendars") or {}).get("primary") or {}
        ).get("busy") or []
        busy_ranges: list[tuple[datetime, datetime]] = []
        for b in busy_raw:
            try:
                busy_ranges.append(
                    (_parse_dt(b["start"]), _parse_dt(b["end"]))
                )
            except Exception:
                continue

        slots: list[FreeSlot] = []
        cursor = window_start
        step = timedelta(minutes=max(15, slot_minutes))
        slot_len = timedelta(minutes=max(15, slot_minutes))

        while cursor + slot_len <= window_end and len(slots) < max_slots:
            local = cursor.astimezone(tz)
            end_local = (cursor + slot_len).astimezone(tz)
            in_workday = (
                local.weekday() < 5
                and local.hour >= workday_start_hour
                and end_local.hour <= workday_end_hour
                and not (end_local.hour == workday_end_hour and end_local.minute > 0)
            )
            if in_workday:
                slot_start = cursor.astimezone(timezone.utc)
                slot_end = (cursor + slot_len).astimezone(timezone.utc)
                if slot_start >= now_utc and not _overlaps_busy(slot_start, slot_end, busy_ranges):
                    slots.append(
                        FreeSlot(start=slot_start, end=slot_end, timezone=timezone_name)
                    )
            cursor += step
        return slots

    def book_event(
        self,
        *,
        prospect_email: str,
        start_iso: str | datetime,
        end_iso: str | datetime,
        prospect_name: str = "",
        title: str = "",
        description: str = "",
        timezone_name: str = "UTC",
        create_meet: bool = True,
    ) -> BookedEvent:
        mailbox = self.resolve_mailbox()
        creds = self._credentials(mailbox)
        start = _parse_dt(start_iso, default_tz=timezone_name)
        end = _parse_dt(end_iso, default_tz=timezone_name)
        if end <= start:
            raise CalendarApiError("end_iso must be after start_iso")

        attendee_email = (prospect_email or "").strip().lower()
        if not attendee_email or "@" not in attendee_email:
            raise CalendarApiError("prospect_email is required")

        display = (prospect_name or "").strip() or attendee_email.split("@")[0]
        summary = (title or "").strip() or f"Attainly intro with {display}"
        desc = (description or "").strip() or (
            "Booked via Attainly Unibox. Looking forward to the conversation."
        )

        event: dict[str, Any] = {
            "summary": summary,
            "description": desc,
            "start": {
                "dateTime": start.isoformat().replace("+00:00", "Z"),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end.isoformat().replace("+00:00", "Z"),
                "timeZone": "UTC",
            },
            "attendees": [{"email": attendee_email, "displayName": display}],
            "reminders": {"useDefault": True},
        }
        if create_meet:
            event["conferenceData"] = {
                "createRequest": {
                    "requestId": f"attainly-{secrets.token_hex(8)}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }

        service = _build_calendar_service(creds)
        try:
            created = (
                service.events()
                .insert(
                    calendarId="primary",
                    body=event,
                    conferenceDataVersion=1 if create_meet else 0,
                    sendUpdates="all",
                )
                .execute()
            )
        except Exception as exc:
            raise CalendarApiError(f"create event failed: {exc}") from exc

        meet_link = _extract_meet_link(created)
        return BookedEvent(
            event_id=str(created.get("id") or ""),
            html_link=str(created.get("htmlLink") or ""),
            meet_link=meet_link,
            hangout_link=str(created.get("hangoutLink") or ""),
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
        )


def _overlaps_busy(
    start: datetime,
    end: datetime,
    busy: list[tuple[datetime, datetime]],
) -> bool:
    for b_start, b_end in busy:
        if start < b_end and end > b_start:
            return True
    return False


def _extract_meet_link(event: dict[str, Any]) -> str:
    hangout = str(event.get("hangoutLink") or "").strip()
    if hangout:
        return hangout
    conf = event.get("conferenceData") or {}
    for ep in conf.get("entryPoints") or []:
        if (ep.get("entryPointType") or "") == "video" and ep.get("uri"):
            return str(ep["uri"])
    for ep in conf.get("entryPoints") or []:
        if ep.get("uri"):
            return str(ep["uri"])
    return ""


def format_slots_for_reply(slots: list[FreeSlot], *, limit: int = 3) -> str:
    """Human-readable slot list for AI drafts / confirmations."""
    if not slots:
        return ""
    parts: list[str] = []
    for s in slots[:limit]:
        local = s.start
        try:
            local = s.start.astimezone(ZoneInfo(s.timezone))
        except Exception:
            pass
        label = local.strftime("%a %b %d at %I:%M %p %Z")
        # Drop leading zero on hour for readability (portable; %-I is POSIX-only).
        parts.append(label.replace(" at 0", " at "))
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} or {parts[1]}"
    return ", ".join(parts[:-1]) + f", or {parts[-1]}"
