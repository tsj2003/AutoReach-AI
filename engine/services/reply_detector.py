"""
GmailReplyDetector — pulls new replies for an Engagement and lands them in the
cockpit triage queue.

Pipeline
--------
1. Iterate prospects whose status is in {sent, replied, contacted} and whose
   most-recent EMAIL_SENT event has a `gmail_thread_id`. (We only know to
   look in Gmail if we sent through Gmail, not the console adapter.)
2. For each, ask Gmail for messages in that thread newer than our last seen.
3. Skip messages from us; keep messages from anyone else.
4. Skip if we've already recorded this Gmail message_id (dedupe via
   `Reply.external_message_id`).
5. Classify with `engine.llm.classifier.classify_and_draft`.
6. If classification is `auto`, push `Prospect.next_send_after` out 5 days
   (so the sequence doesn't keep poking an out-of-office).
7. Otherwise, call `OperationsService.record_reply` — same code path as the
   manual cockpit form. The reply lands in the operator's queue.
8. Debit cost ledger for the LLM call.

Idempotency
-----------
Safe to run repeatedly. Duplicate Gmail message ids are filtered via the
existing `Reply.external_message_id` unique lookup. A reply seen twice does
not double-record.

Failure tolerance
-----------------
* Gmail token invalid -> emits gmail.token_invalid + returns gracefully.
* Gemini unavailable  -> reply still recorded with classification='objection'
                         and fallback_used=True. The operator sees a yellow flag.
* Per-prospect errors are logged and don't stop the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from engine.adapters.db_token_store import DbTokenStore

from engine.adapters.gmail_token_store import (
    GmailTokenStore,
    TokenInvalid,
    TokenUnavailable,
)
from engine.core.protocols import CostLedger, EventSink, Store
from engine.core.types import (
    CostEntry,
    Event,
    EventKind,
)
from engine.llm.classifier import ClassificationResult, classify_and_draft
from engine.llm.gemini import GeminiClient
from engine.services.operations import OperationsService

logger = logging.getLogger(__name__)


@dataclass
class ReplyDetectionResult:
    """Outcome of one detector pass over an Engagement."""

    prospects_scanned: int = 0
    threads_polled: int = 0
    replies_recorded: int = 0
    auto_responders: int = 0
    duplicates_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    fell_back_to_default: int = 0
    llm_cost_cents: int = 0
    token_invalid: bool = False


class GmailReplyDetector:
    """
    Polls Gmail for replies to outbound messages.

    Constructed with the same dependencies as the rest of the engine: a Store
    (read prospects + their sent-event history), an EventSink (emit observability),
    a CostLedger (debit LLM costs), an OperationsService (land replies via the
    same code path as the manual cockpit form), and a GmailTokenStore + sender
    email (so it can authenticate as the same mailbox the sends went out from).

    For tests, `gmail_build` lets you swap in a fake gmail client.
    """

    def __init__(
        self,
        *,
        store: Store,
        events: EventSink,
        ledger: CostLedger,
        ops: OperationsService,
        token_store: GmailTokenStore,
        sender_email: str,
        gemini: Optional[GeminiClient] = None,
        gmail_build: Optional[Callable] = None,  # for tests
        mailbox_id: Optional[str] = None,
    ) -> None:
        self._store = store
        self._events = events
        self._ledger = ledger
        self._ops = ops
        self._tokens = token_store
        self._sender = sender_email.lower().strip()
        self._gemini = gemini
        self._gmail_build = gmail_build
        self._mailbox_id = mailbox_id

    # ─── Public API ─────────────────────────────────────────────────────

    def poll(self, engagement_id: str, *, max_prospects: int = 200) -> ReplyDetectionResult:
        """
        Scan one Engagement for new replies. Returns a summary report.

        Tolerates token issues (returns with `token_invalid=True`) so that
        callers in a cron loop don't crash the whole process for one bad
        engagement.
        """
        result = ReplyDetectionResult()

        engagement = self._store.get_engagement(engagement_id)
        if engagement is None:
            result.errors.append(f"engagement not found: {engagement_id}")
            return result

        # Authenticate. Token failures are surfaced but never raised.
        try:
            creds = self._tokens.load()
        except TokenUnavailable as exc:
            result.errors.append(f"token unavailable: {exc}")
            return result
        except TokenInvalid as exc:
            result.token_invalid = True
            self._events.emit(
                Event(
                    id=_new_id("ev"),
                    kind=EventKind.GMAIL_TOKEN_INVALID,
                    engagement_id=engagement_id,
                    payload={"reason": str(exc), "scope": "reply_detector"},
                )
            )
            result.errors.append(f"token invalid: {exc}")
            return result

        gmail = self._build_gmail(creds)

        # Scan candidate prospects: those we've contacted and aren't terminal.
        candidates = list(
            self._iter_candidate_prospects(engagement_id, limit=max_prospects)
        )
        result.prospects_scanned = len(candidates)

        for prospect, thread_id in candidates:
            try:
                self._poll_one_thread(
                    engagement_id=engagement_id,
                    prospect=prospect,
                    thread_id=thread_id,
                    booking_url=engagement.booking_url or "",
                    gmail=gmail,
                    result=result,
                )
            except Exception as exc:
                # Per-prospect resilience.
                logger.exception("reply detector failed on prospect %s", prospect.id)
                result.errors.append(f"{prospect.email}: {exc}")
                continue

        return result

    # ─── Internals ──────────────────────────────────────────────────────

    def _build_gmail(self, creds):
        if self._gmail_build is not None:
            return self._gmail_build(creds)
        from googleapiclient.discovery import build  # type: ignore

        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def _iter_candidate_prospects(self, engagement_id: str, *, limit: int):
        """
        Yield (Prospect, gmail_thread_id) pairs for prospects worth polling:
        those we've sent to (have a thread id from a EMAIL_SENT event), and
        whose status hasn't already terminated the sequence.

        We iterate per-status to keep DB pressure small; an Engagement with
        10k contacted prospects shouldn't hit this in one pass without paging.
        """
        active_statuses = ("contacted", "sent", "new", "replied")
        seen = set()
        for status in active_statuses:
            for prospect in self._store.list_prospects(engagement_id, status=status, limit=limit):
                if prospect.id in seen or not prospect.email:
                    continue
                seen.add(prospect.id)
                if prospect.status in ("unsubscribed", "booked"):
                    continue
                thread_id = self._latest_thread_id_for(prospect.id)
                if thread_id is None:
                    continue
                yield prospect, thread_id

    def _latest_thread_id_for(self, prospect_id: str) -> Optional[str]:
        """Find the most recent EMAIL_SENT event's gmail_thread_id for a prospect."""
        # Listing by prospect requires scanning recent events; engagements have
        # bounded volume so list_recent(limit=500) is plenty for now.
        for ev in self._events.list_recent(limit=500):
            if (
                ev.kind == EventKind.EMAIL_SENT
                and ev.prospect_id == prospect_id
                and ev.payload.get("gmail_thread_id")
            ):
                if self._mailbox_id is not None and ev.payload.get("mailbox_id") != self._mailbox_id:
                    continue
                return str(ev.payload.get("gmail_thread_id"))
        return None

    def _poll_one_thread(
        self,
        *,
        engagement_id: str,
        prospect,
        thread_id: str,
        booking_url: str,
        gmail,
        result: ReplyDetectionResult,
    ) -> None:
        result.threads_polled += 1

        try:
            thread = (
                gmail.users()
                .threads()
                .get(userId="me", id=thread_id, format="metadata",
                     metadataHeaders=["From", "Subject", "Message-ID", "Date"])
                .execute()
            )
        except Exception as exc:
            err = repr(exc)
            if any(s in err for s in ("404", "Not Found")):
                # Thread deleted on the user's side — skip silently.
                return
            raise

        messages = thread.get("messages", []) if isinstance(thread, dict) else []
        if not messages:
            return

        # Find the original outbound message (first one from us) to ground
        # the LLM prompt. Falls back to empty strings if we can't find it.
        original_subject = ""
        original_body = ""
        for m in messages:
            from_header = _header(m, "From").lower()
            if self._sender and self._sender in from_header:
                original_subject = _header(m, "Subject")
                original_body = m.get("snippet", "")
                break

        # Iterate inbound messages (not from us).
        for m in messages:
            msg_id = m.get("id")
            if not msg_id:
                continue

            from_header = _header(m, "From").lower()
            if self._sender and self._sender in from_header:
                # Our own message; skip.
                continue

            # Dedupe — have we already recorded this gmail message id?
            if self._ops._store.get_reply_by_external_id(msg_id) is not None:
                result.duplicates_skipped += 1
                continue

            snippet = (m.get("snippet") or "").strip()
            if not snippet:
                continue

            # Classify (graceful fallback inside).
            classification = classify_and_draft(
                snippet=snippet,
                original_subject=original_subject,
                original_body=original_body,
                booking_url=booking_url,
                client=self._gemini,
            )
            if classification.fallback_used:
                result.fell_back_to_default += 1
            if classification.estimated_cost_cents > 0:
                self._ledger.debit(
                    CostEntry(
                        id=_new_id("cost_llm"),
                        engagement_id=engagement_id,
                        job_id=None,
                        category="llm",
                        amount_cents=classification.estimated_cost_cents,
                        metadata={
                            "purpose": "reply_classify_and_draft",
                            "openinference_trace_id": classification.openinference_trace_id,
                        },
                    )
                )
                result.llm_cost_cents += classification.estimated_cost_cents

            # Auto-responder handling: don't record as a real reply, just delay.
            if classification.classification == "auto":
                result.auto_responders += 1
                self._defer_prospect(prospect.id)
                self._events.emit(
                    Event(
                        id=_new_id("ev"),
                        kind=EventKind.EMAIL_REPLY_RECEIVED,
                        engagement_id=engagement_id,
                        prospect_id=prospect.id,
                        payload={
                            "via": "gmail",
                            "auto_responder": True,
                            "external_message_id": msg_id,
                            "openinference_trace_id": classification.openinference_trace_id,
                        },
                    )
                )
                continue

            # Real reply — land it in the cockpit triage queue.
            self._ops.record_reply(
                engagement_id=engagement_id,
                prospect_id=prospect.id,
                snippet=snippet,
                classification=classification.classification,
                suggested_reply=classification.suggested_reply,
                external_message_id=msg_id,
            )
            self._events.emit(
                Event(
                    id=_new_id("ev"),
                    kind=EventKind.REPLY_CLASSIFIED,
                    engagement_id=engagement_id,
                    prospect_id=prospect.id,
                    payload={
                        "classification": classification.classification,
                        "fallback_used": classification.fallback_used,
                        "external_message_id": msg_id,
                        "openinference_trace_id": classification.openinference_trace_id,
                    },
                )
            )
            result.replies_recorded += 1

    def _defer_prospect(self, prospect_id: str) -> None:
        """Push next_send_after out 5 days for an auto-responder."""
        from datetime import timedelta
        from engine.core.types import Prospect

        prospect = self._store.get_prospect(prospect_id)
        if prospect is None:
            return
        # Prospect is frozen; replace.
        deferred_until = datetime.now(timezone.utc) + timedelta(days=5)
        new_raw = dict(prospect.raw)
        new_raw["next_send_after"] = deferred_until.isoformat()
        replacement = Prospect(
            id=prospect.id,
            engagement_id=prospect.engagement_id,
            email=prospect.email,
            full_name=prospect.full_name,
            company=prospect.company,
            title=prospect.title,
            raw=new_raw,
            research=prospect.research,
            status=prospect.status,
            created_at=prospect.created_at,
        )
        self._store.save_prospect(replacement)


class TenantMailboxReplyDetector:
    """Poll replies through the tenant's connected Gmail mailboxes."""

    def __init__(
        self,
        *,
        store: Store,
        events: EventSink,
        ledger: CostLedger,
        ops: OperationsService,
        gemini: Optional[GeminiClient] = None,
        gmail_build_factory: Optional[Callable[[object], Callable]] = None,
    ) -> None:
        self._store = store
        self._events = events
        self._ledger = ledger
        self._ops = ops
        self._gemini = gemini
        self._gmail_build_factory = gmail_build_factory

    def poll(self, engagement_id: str, *, max_prospects: int = 200) -> ReplyDetectionResult:
        result = ReplyDetectionResult()
        tenant_id = self._tenant_id_for_engagement(engagement_id)
        if not tenant_id:
            result.errors.append(f"tenant not found for engagement: {engagement_id}")
            return result

        mailboxes = [
            mailbox for mailbox in self._store.list_mailboxes(tenant_id)
            if getattr(mailbox, "provider", "gmail") == "gmail"
            and getattr(mailbox, "status", "active") in {"active", "warming"}
        ]
        if not mailboxes:
            result.errors.append(f"no active gmail mailboxes for tenant: {tenant_id}")
            return result

        for mailbox in mailboxes:
            detector = GmailReplyDetector(
                store=self._store,
                events=self._events,
                ledger=self._ledger,
                ops=self._ops,
                token_store=DbTokenStore(store=self._store, mailbox_id=mailbox.id),
                sender_email=mailbox.email_address,
                gemini=self._gemini,
                gmail_build=self._gmail_build_for(mailbox),
                mailbox_id=mailbox.id,
            )
            mailbox_result = detector.poll(engagement_id, max_prospects=max_prospects)
            self._merge_result(result, mailbox_result)

        return result

    def _tenant_id_for_engagement(self, engagement_id: str) -> Optional[str]:
        resolver = getattr(self._store, "get_engagement_tenant_id", None)
        if callable(resolver):
            return resolver(engagement_id)
        return None

    def _gmail_build_for(self, mailbox: object) -> Optional[Callable]:
        if self._gmail_build_factory is None:
            return None
        return self._gmail_build_factory(mailbox)

    @staticmethod
    def _merge_result(target: ReplyDetectionResult, source: ReplyDetectionResult) -> None:
        target.prospects_scanned += source.prospects_scanned
        target.threads_polled += source.threads_polled
        target.replies_recorded += source.replies_recorded
        target.auto_responders += source.auto_responders
        target.duplicates_skipped += source.duplicates_skipped
        target.errors.extend(source.errors)
        target.fell_back_to_default += source.fell_back_to_default
        target.llm_cost_cents += source.llm_cost_cents
        target.token_invalid = target.token_invalid or source.token_invalid


# ─── Helpers ────────────────────────────────────────────────────────────────


def _header(gmail_msg: dict, name: str) -> str:
    """Pull a header value out of the Gmail metadata-format message dict."""
    payload = gmail_msg.get("payload") or {}
    for h in payload.get("headers", []):
        if str(h.get("name", "")).lower() == name.lower():
            return str(h.get("value", "") or "")
    return ""


def _new_id(prefix: str) -> str:
    import secrets

    return f"{prefix}_{secrets.token_hex(6)}"
