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

        # Hard opt-outs → unsubscribe + stop, always automatic.
        if cls in ("unsubscribe", "do_not_contact"):
            return self._unsubscribe(reply)

        # Soft no → mark dead, stop sequence, no reply pushed.
        if cls == "not_interested":
            return self._mark_dead(reply)

        # OOO → defer the prospect's next step; never reply to an auto-responder.
        if cls == "out_of_office":
            return self._defer_for_ooo(reply)

        # Referral → create the referred contact as a new prospect, flag original.
        if cls == "referral":
            return self._handle_referral(reply, mode=mode)

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

    def _mark_dead(self, reply: Reply) -> ReplyActionResult:
        from engine.core.types import Prospect
        p = self._store.get_prospect(reply.prospect_id)
        if p is not None and p.status not in ("unsubscribed", "booked", "dead"):
            self._store.save_prospect(Prospect(
                id=p.id, engagement_id=p.engagement_id, email=p.email,
                full_name=p.full_name, company=p.company, title=p.title,
                raw=p.raw, research=p.research, status="dead", created_at=p.created_at,
            ))
        self._emit(EventKind.REPLY_SENT, reply, {"action": "marked_not_interested", "auto": True})
        return ReplyActionResult("not_interested", False, "prospect marked not interested, sequence stopped")

    def _defer_for_ooo(self, reply: Reply, *, default_days: int = 7) -> ReplyActionResult:
        """Reschedule the prospect's next send to the OOO return date (or +7d)."""
        from datetime import datetime, timedelta, timezone
        from engine.core.types import Prospect

        # Parse return date if the classifier extracted one and stashed it on the reply.
        return_date = None
        # Reply doesn't carry the date; the detector passes it via suggested_reply meta.
        # We default to +default_days unless the snippet has an ISO date.
        import re as _re
        m = _re.search(r"\b(\d{4}-\d{2}-\d{2})\b", reply.snippet or "")
        if m:
            try:
                return_date = datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
            except ValueError:
                return_date = None
        resume_at = return_date or (datetime.now(timezone.utc) + timedelta(days=default_days))

        p = self._store.get_prospect(reply.prospect_id)
        if p is not None and p.status not in ("unsubscribed", "booked", "dead"):
            new_raw = dict(p.raw or {})
            new_raw["next_send_after"] = resume_at.isoformat()
            # OOO is not a real reply — keep the prospect in-sequence ('contacted')
            # so the follow-up resumes after the return date.
            self._store.save_prospect(Prospect(
                id=p.id, engagement_id=p.engagement_id, email=p.email,
                full_name=p.full_name, company=p.company, title=p.title,
                raw=new_raw, research=p.research,
                status="contacted",
                created_at=p.created_at,
            ))
        self._emit(EventKind.REPLY_SENT, reply, {
            "action": "ooo_rescheduled", "auto": True, "resume_at": resume_at.isoformat(),
        })
        return ReplyActionResult("ooo_rescheduled", False, f"follow-up rescheduled to {resume_at.date()}")

    def _handle_referral(self, reply: Reply, *, mode: str) -> ReplyActionResult:
        """Flag the referral for the operator. New-prospect creation is operator-confirmed
        (we don't auto-email a referred contact without a human in the loop)."""
        self._emit(EventKind.REPLY_DRAFT_APPROVED, reply, {
            "action": "referral", "pending": True, "mode": mode,
        })
        return ReplyActionResult("flagged_for_approval", False, "referral flagged for operator intro")

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
