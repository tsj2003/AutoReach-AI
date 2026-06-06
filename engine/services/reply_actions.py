"""
M6 — ReplyActionExecutor: HITL vs Autopilot reply handling.

Given a recorded Reply + its classification, decide and (optionally) execute
the follow-up action:

    interested   → draft calendar reply.  HITL: flag for approval.
                                          Autopilot: send via Gmail immediately.
    objection    → draft handling reply.  HITL only (never auto-send objection handling).
    unsubscribe  → unsubscribe + blocklist, stop sequence. Always automatic.
    auto         → no action (handled upstream by the detector — deferred).

Mode comes from the agent's config: reply_mode = "hitl" | "autopilot".

Autopilot is deliberately conservative: it ONLY auto-sends "interested" replies
(the high-value, low-risk case). Objections still require a human, because a bad
auto-objection-response is how you turn a maybe into a never.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from engine.core.protocols import EventSink, Store
from engine.core.types import Event, EventKind, Reply

logger = logging.getLogger(__name__)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


@dataclass(frozen=True)
class ReplyActionResult:
    action: str          # "flagged_for_approval" | "auto_sent" | "unsubscribed" | "none"
    auto_sent: bool
    detail: str


class ReplyActionExecutor:
    """
    Decides + executes reply follow-ups.

    `send_fn` is an optional callable (reply, body) -> bool used to actually
    send in autopilot mode. In tests we inject a fake; in production the
    cockpit wires the Gmail adapter.
    """

    def __init__(
        self,
        *,
        store: Store,
        events: EventSink,
        send_fn=None,
    ) -> None:
        self._store = store
        self._events = events
        self._send_fn = send_fn

    def handle(self, reply: Reply, *, mode: str = "hitl") -> ReplyActionResult:
        cls = reply.classification

        if cls == "unsubscribe":
            return self._unsubscribe(reply)

        if cls == "interested":
            if mode == "autopilot" and reply.suggested_reply and self._send_fn:
                ok = False
                try:
                    ok = bool(self._send_fn(reply, reply.suggested_reply))
                except Exception as exc:
                    logger.warning("autopilot send failed: %s", exc)
                if ok:
                    self._mark_sent(reply)
                    self._emit(EventKind.REPLY_SENT, reply, {"mode": "autopilot"})
                    return ReplyActionResult("auto_sent", True, "interested reply auto-sent")
                # fall through to flag if send failed
            self._emit(EventKind.REPLY_DRAFT_APPROVED, reply, {"mode": "hitl", "pending": True})
            return ReplyActionResult("flagged_for_approval", False, "interested reply flagged for approval")

        # objection / other → always HITL
        return ReplyActionResult("flagged_for_approval", False, f"{cls} reply flagged for approval")

    # ── internals ──────────────────────────────────────────────────────────

    def _unsubscribe(self, reply: Reply) -> ReplyActionResult:
        # Mark the prospect unsubscribed (frozen → replace).
        from engine.core.types import Prospect

        p = self._store.get_prospect(reply.prospect_id)
        if p is not None and p.status != "unsubscribed":
            self._store.save_prospect(Prospect(
                id=p.id, engagement_id=p.engagement_id, email=p.email,
                full_name=p.full_name, company=p.company, title=p.title,
                raw=p.raw, research=p.research, status="unsubscribed",
                created_at=p.created_at,
            ))
        self._emit(EventKind.REPLY_SENT, reply, {"action": "unsubscribed", "auto": True})
        return ReplyActionResult("unsubscribed", False, "prospect unsubscribed + sequence stopped")

    def _mark_sent(self, reply: Reply) -> None:
        from engine.core.types import Reply as _Reply
        self._store.save_reply(_Reply(
            id=reply.id, engagement_id=reply.engagement_id, prospect_id=reply.prospect_id,
            job_id=reply.job_id, snippet=reply.snippet, classification=reply.classification,
            suggested_reply=reply.suggested_reply, status="sent",
            received_at=reply.received_at, external_message_id=reply.external_message_id,
        ))

    def _emit(self, kind: EventKind, reply: Reply, payload: dict) -> None:
        self._events.emit(Event(
            id=_new_id("ev"), kind=kind, engagement_id=reply.engagement_id,
            prospect_id=reply.prospect_id, payload={**payload, "reply_id": reply.id},
        ))
