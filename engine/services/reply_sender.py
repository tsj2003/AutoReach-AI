"""Send approved inbox replies via tenant Gmail mailbox."""

from __future__ import annotations

import logging
import os
import secrets
from typing import Callable, Optional

from engine.adapters.db_token_store import DbTokenStore
from engine.adapters.email_gmail_real import RealGmailSendAdapter
from engine.core.state import JobState
from engine.core.types import Event, EventKind, Job, JobKind, Reply
from engine.runtime.contexts import DefaultAdapterContext

logger = logging.getLogger(__name__)


def reply_send_job_id(reply_id: str) -> str:
    """Deterministic job ID — retries must not double-send."""
    return f"reply_send_{reply_id}"


class ReplySender:
    """Send a human-approved reply through the tenant's active mailbox."""

    def __init__(self, *, store, events, ledger) -> None:
        self._store = store
        self._events = events
        self._ledger = ledger

    def send(self, reply: Reply, body: str, *, tenant_id: str) -> bool:
        if reply.status == "sent":
            logger.info("reply send skipped: already sent reply=%s", reply.id)
            return True

        job_id = reply_send_job_id(reply.id)
        existing = self._store.get_job(job_id)
        if existing is not None and existing.state == JobState.SUCCEEDED.value:
            logger.info("reply send skipped: job already succeeded reply=%s", reply.id)
            return True

        prospect = self._store.get_prospect(reply.prospect_id)
        if prospect is None or not prospect.email:
            logger.warning("reply send skipped: no prospect email reply=%s", reply.id)
            return False

        mailboxes = list(self._store.list_mailboxes(tenant_id, status="active"))
        if not mailboxes:
            logger.warning("reply send skipped: no active mailbox tenant=%s", tenant_id)
            return False
        mailbox = mailboxes[0]

        thread_id = self._latest_thread_id(reply.prospect_id)
        dry_run = os.getenv("AUTOREACH_GMAIL_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")

        adapter = RealGmailSendAdapter(
            sender_email=mailbox.email_address,
            token_store=DbTokenStore(store=self._store, mailbox_id=mailbox.id),
            dry_run=dry_run,
        )
        subject = self._reply_subject(reply)
        job = Job(
            id=job_id,
            engagement_id=reply.engagement_id,
            agent_id="inbox_reply",
            kind=JobKind.EMAIL_REPLY_SEND,
            payload={
                "to_email": prospect.email,
                "subject": subject,
                "body_text": body,
                "thread_id": thread_id,
                "prospect_id": reply.prospect_id,
                "reply_id": reply.id,
            },
            prospect_id=reply.prospect_id,
            state=JobState.RUNNING.value,
        )
        self._store.save_job(job)
        context = DefaultAdapterContext(self._store, self._events, self._ledger)
        try:
            result = adapter.execute(job, context=context)
        except Exception:
            logger.exception("reply send failed reply=%s", reply.id)
            job.state = JobState.FAILED.value
            job.last_error = "adapter_exception"
            self._store.save_job(job)
            return False
        if not result.succeeded:
            job.state = JobState.FAILED.value
            job.last_error = (result.error or "send_failed")[:500]
            self._store.save_job(job)
            return False
        job.state = JobState.SUCCEEDED.value
        job.result = dict(result.output or {})
        self._store.save_job(job)
        self._events.emit(Event(
            id=f"ev_{secrets.token_hex(6)}",
            kind=EventKind.REPLY_SENT,
            engagement_id=reply.engagement_id,
            prospect_id=reply.prospect_id,
            payload={"reply_id": reply.id, "via": "inbox_approve", "mailbox_id": mailbox.id},
        ))
        return True

    def _latest_thread_id(self, prospect_id: str) -> Optional[str]:
        for ev in self._events.list_recent(limit=500):
            if ev.prospect_id == prospect_id and ev.kind == EventKind.EMAIL_SENT:
                tid = ev.payload.get("gmail_thread_id")
                if tid:
                    return tid
        return None

    @staticmethod
    def _reply_subject(reply: Reply) -> str:
        snippet = (reply.snippet or "").strip()
        if snippet.lower().startswith("re:"):
            return snippet.split("\n", 1)[0][:120]
        return "Re: your note"


def build_reply_send_fn(*, store, events, ledger, tenant_id: str) -> Callable[[Reply, str], bool]:
    sender = ReplySender(store=store, events=events, ledger=ledger)

    def _send(reply: Reply, body: str) -> bool:
        return sender.send(reply, body, tenant_id=tenant_id)

    return _send
