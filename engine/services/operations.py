"""
OperationsService — engagement / agent / prospect / reply / meeting operations.

Single chokepoint for the cockpit and CLI. Encapsulates ID generation,
event emission, and state-transition rules that don't belong in storage
or the runtime.

Why this exists
---------------
Without a service layer, the cockpit ends up duplicating business logic
across HTTP handlers (e.g., "when a reply is approved + sent, also
transition the prospect to status='replied' and emit reply.sent + maybe
auto-create a meeting"). We want exactly one implementation of that.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Iterable, Optional

from engine.core.protocols import EventSink, Store
from engine.core.types import (
    Agent,
    Engagement,
    Event,
    EventKind,
    Meeting,
    Prospect,
    Reply,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


class OperationsService:
    """Business operations the cockpit / CLI / future API call into."""

    def __init__(self, *, store: Store, events: EventSink) -> None:
        self._store = store
        self._events = events

    # ─── Engagements ────────────────────────────────────────────────────

    def create_engagement(
        self,
        *,
        id: Optional[str] = None,
        customer_name: str,
        offer: str,
        icp_description: str,
        booking_url: Optional[str] = None,
        monthly_meeting_target: Optional[int] = None,
        price_per_outcome_cents: Optional[int] = None,
        monthly_budget_cents: Optional[int] = None,
    ) -> Engagement:
        eng = Engagement(
            id=id or _new_id("eng"),
            customer_name=customer_name,
            offer=offer,
            icp_description=icp_description,
            booking_url=booking_url,
            monthly_meeting_target=monthly_meeting_target,
            price_per_outcome_cents=price_per_outcome_cents,
            monthly_budget_cents=monthly_budget_cents,
        )
        self._store.save_engagement(eng)
        self._events.emit(
            Event(
                id=_new_id("ev"),
                kind=EventKind.ENGAGEMENT_CREATED,
                engagement_id=eng.id,
                payload={
                    "customer_name": eng.customer_name,
                    "monthly_meeting_target": eng.monthly_meeting_target,
                    "price_per_outcome_cents": eng.price_per_outcome_cents,
                },
            )
        )
        return eng

    def list_engagements(self) -> list[Engagement]:
        return list(self._store.list_engagements())

    def pause_engagement(self, engagement_id: str) -> bool:
        eng = self._store.get_engagement(engagement_id)
        if eng is None or eng.status != "active":
            return False
        # Engagement is frozen — replace with a paused copy.
        paused = Engagement(
            id=eng.id,
            customer_name=eng.customer_name,
            offer=eng.offer,
            icp_description=eng.icp_description,
            icp_filters=eng.icp_filters,
            booking_url=eng.booking_url,
            monthly_meeting_target=eng.monthly_meeting_target,
            price_per_outcome_cents=eng.price_per_outcome_cents,
            monthly_budget_cents=eng.monthly_budget_cents,
            status="paused",
            created_at=eng.created_at,
            metadata=eng.metadata,
        )
        self._store.save_engagement(paused)
        self._events.emit(
            Event(id=_new_id("ev"), kind=EventKind.ENGAGEMENT_PAUSED, engagement_id=eng.id)
        )
        return True

    # ─── Agents ─────────────────────────────────────────────────────────

    def create_agent(
        self,
        *,
        engagement_id: str,
        runner_kind: str = "outbound.v1",
        id: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> Agent:
        agent = Agent(
            id=id or _new_id("agent"),
            engagement_id=engagement_id,
            runner_kind=runner_kind,
            config=config or {},
        )
        self._store.save_agent(agent)
        self._events.emit(
            Event(
                id=_new_id("ev"),
                kind=EventKind.AGENT_CREATED,
                engagement_id=engagement_id,
                agent_id=agent.id,
                payload={"runner_kind": runner_kind},
            )
        )
        return agent

    # ─── Prospects ──────────────────────────────────────────────────────

    def add_prospect(
        self,
        *,
        engagement_id: str,
        email: str,
        full_name: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
        raw: Optional[dict] = None,
        id: Optional[str] = None,
    ) -> Prospect:
        prospect = Prospect(
            id=id or _new_id("p"),
            engagement_id=engagement_id,
            email=email,
            full_name=full_name,
            company=company,
            title=title,
            raw=raw or {},
        )
        self._store.save_prospect(prospect)
        return prospect

    def list_prospects(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> Iterable[Prospect]:
        return self._store.list_prospects(engagement_id, status=status, limit=limit)

    # ─── Replies ────────────────────────────────────────────────────────

    def record_reply(
        self,
        *,
        engagement_id: str,
        prospect_id: str,
        snippet: str,
        suggested_reply: str = "",
        classification: str = "objection",
        job_id: Optional[str] = None,
        external_message_id: Optional[str] = None,
    ) -> Reply:
        # Idempotency: if we already saw this external_message_id, return it.
        if external_message_id is not None:
            existing = self._store.get_reply_by_external_id(external_message_id)
            if existing is not None:
                return existing

        reply = Reply(
            id=_new_id("rep"),
            engagement_id=engagement_id,
            prospect_id=prospect_id,
            job_id=job_id,
            snippet=snippet,
            classification=classification,
            suggested_reply=suggested_reply,
            status="pending",
            external_message_id=external_message_id,
        )
        self._store.save_reply(reply)
        self._events.emit(
            Event(
                id=_new_id("ev"),
                kind=EventKind.EMAIL_REPLY_RECEIVED,
                engagement_id=engagement_id,
                prospect_id=prospect_id,
                job_id=job_id,
                payload={"classification": classification, "snippet_chars": len(snippet)},
            )
        )
        # Update the prospect status, if the prospect record exists.
        prospect = self._store.get_prospect(prospect_id)
        if prospect is not None and prospect.status not in ("replied", "booked", "unsubscribed"):
            updated = Prospect(
                id=prospect.id,
                engagement_id=prospect.engagement_id,
                email=prospect.email,
                full_name=prospect.full_name,
                company=prospect.company,
                title=prospect.title,
                raw=prospect.raw,
                research=prospect.research,
                status="unsubscribed" if classification == "unsubscribe" else "replied",
                created_at=prospect.created_at,
            )
            self._store.save_prospect(updated)
        return reply

    def list_replies(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Reply]:
        return self._store.list_replies(engagement_id, status=status, limit=limit)

    def update_reply_draft(self, reply_id: str, *, suggested_reply: str) -> Optional[Reply]:
        existing = self._store.get_reply(reply_id)
        if existing is None:
            return None
        updated = Reply(
            id=existing.id,
            engagement_id=existing.engagement_id,
            prospect_id=existing.prospect_id,
            job_id=existing.job_id,
            snippet=existing.snippet,
            classification=existing.classification,
            suggested_reply=suggested_reply,
            status=existing.status,
            received_at=existing.received_at,
            external_message_id=existing.external_message_id,
        )
        self._store.save_reply(updated)
        return updated

    def mark_reply_sent(self, reply_id: str) -> bool:
        existing = self._store.get_reply(reply_id)
        if existing is None or existing.status not in ("pending", "approved"):
            return False
        updated = Reply(
            id=existing.id,
            engagement_id=existing.engagement_id,
            prospect_id=existing.prospect_id,
            job_id=existing.job_id,
            snippet=existing.snippet,
            classification=existing.classification,
            suggested_reply=existing.suggested_reply,
            status="sent",
            received_at=existing.received_at,
            external_message_id=existing.external_message_id,
        )
        self._store.save_reply(updated)
        self._events.emit(
            Event(
                id=_new_id("ev"),
                kind=EventKind.REPLY_SENT,
                engagement_id=existing.engagement_id,
                prospect_id=existing.prospect_id,
                payload={"reply_id": reply_id},
            )
        )
        return True

    def discard_reply(self, reply_id: str) -> bool:
        existing = self._store.get_reply(reply_id)
        if existing is None:
            return False
        updated = Reply(
            id=existing.id,
            engagement_id=existing.engagement_id,
            prospect_id=existing.prospect_id,
            job_id=existing.job_id,
            snippet=existing.snippet,
            classification=existing.classification,
            suggested_reply=existing.suggested_reply,
            status="discarded",
            received_at=existing.received_at,
            external_message_id=existing.external_message_id,
        )
        self._store.save_reply(updated)
        return True

    # ─── Meetings ───────────────────────────────────────────────────────

    def book_meeting(
        self,
        *,
        engagement_id: str,
        prospect_id: str,
        scheduled_for: datetime,
        reply_id: Optional[str] = None,
        notes: str = "",
    ) -> Meeting:
        # Ensure scheduled_for is tz-aware UTC.
        if scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
        else:
            scheduled_for = scheduled_for.astimezone(timezone.utc)

        meeting = Meeting(
            id=_new_id("mtg"),
            engagement_id=engagement_id,
            prospect_id=prospect_id,
            reply_id=reply_id,
            scheduled_for=scheduled_for,
            status="booked",
            notes=notes,
        )
        self._store.save_meeting(meeting)
        self._events.emit(
            Event(
                id=_new_id("ev"),
                kind=EventKind.MEETING_BOOKED,
                engagement_id=engagement_id,
                prospect_id=prospect_id,
                payload={
                    "meeting_id": meeting.id,
                    "scheduled_for": scheduled_for.isoformat(),
                },
            )
        )
        # Mark the prospect as booked.
        prospect = self._store.get_prospect(prospect_id)
        if prospect is not None and prospect.status not in ("booked", "unsubscribed"):
            updated = Prospect(
                id=prospect.id,
                engagement_id=prospect.engagement_id,
                email=prospect.email,
                full_name=prospect.full_name,
                company=prospect.company,
                title=prospect.title,
                raw=prospect.raw,
                research=prospect.research,
                status="booked",
                created_at=prospect.created_at,
            )
            self._store.save_prospect(updated)
        return meeting

    def update_meeting_status(self, meeting_id: str, *, status: str, notes: Optional[str] = None) -> bool:
        if status not in ("booked", "qualified", "no_show", "cancelled"):
            return False
        existing = self._store.get_meeting(meeting_id)
        if existing is None:
            return False
        updated = Meeting(
            id=existing.id,
            engagement_id=existing.engagement_id,
            prospect_id=existing.prospect_id,
            reply_id=existing.reply_id,
            scheduled_for=existing.scheduled_for,
            status=status,
            booked_at=existing.booked_at,
            notes=notes if notes is not None else existing.notes,
        )
        self._store.save_meeting(updated)

        kind_map = {
            "qualified": EventKind.MEETING_QUALIFIED,
            "no_show": EventKind.MEETING_NO_SHOW,
            "cancelled": EventKind.MEETING_CANCELLED,
        }
        ev_kind = kind_map.get(status)
        if ev_kind is not None:
            self._events.emit(
                Event(
                    id=_new_id("ev"),
                    kind=ev_kind,
                    engagement_id=existing.engagement_id,
                    prospect_id=existing.prospect_id,
                    payload={"meeting_id": meeting_id},
                )
            )
        return True

    def list_meetings(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Meeting]:
        return self._store.list_meetings(engagement_id, status=status, limit=limit)
