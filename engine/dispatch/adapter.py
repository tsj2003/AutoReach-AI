"""Runtime adapter that sends email through the smart inbox router."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from engine.core.protocols import AdapterContext
from engine.core.types import Job, JobKind
from engine.dispatch.provider import SMTPProvider
from engine.dispatch.router import SmartInboxRouter
from engine.runtime.results import AdapterResultData
from engine.services.mailbox_health import MailboxHealthMonitor


class SmartRoutedEmailAdapter:
    """Adapter bridge from legacy EngineRuntime email jobs to smart dispatch."""

    name = "email.smart_router"

    def __init__(
        self,
        *,
        store: Any,
        events: Any,
        ledger: Any,
        health_monitor: Optional[MailboxHealthMonitor] = None,
        provider: Optional[SMTPProvider] = None,
    ) -> None:
        self._store = store
        self._events = events
        self._ledger = ledger
        self._health_monitor = health_monitor or MailboxHealthMonitor(store=store, events=events)
        self._provider = provider or SMTPProvider(store=store, events=events, ledger=ledger)

    def handles(self, job: Job) -> bool:
        return job.kind == JobKind.EMAIL_SEND

    def execute(self, job: Job, *, context: AdapterContext) -> AdapterResultData:
        tenant_id = self._tenant_id_for(job)
        if not tenant_id:
            return AdapterResultData.fail("tenant_id required for smart email dispatch", retryable=False)

        try:
            return asyncio.run(self._execute_async(job=job, tenant_id=tenant_id))
        except RuntimeError as exc:
            return AdapterResultData.fail(f"smart dispatch failed: {exc}", retryable=True)

    async def _execute_async(self, *, job: Job, tenant_id: str) -> AdapterResultData:
        router = SmartInboxRouter(
            health_monitor=self._health_monitor,
            provider=self._provider,
            store=self._store,
        )
        recipient_email = job.payload.get("to") if isinstance(job.payload, dict) else None
        mailbox = await router.get_next_available_mailbox(
            tenant_id=tenant_id, recipient_email=recipient_email
        )
        if mailbox is None:
            return AdapterResultData.fail("no healthy mailbox available for tenant", retryable=True)

        payload = dict(job.payload)
        payload.setdefault("tenant_id", tenant_id)
        payload.setdefault("engagement_id", job.engagement_id)
        payload.setdefault("campaign_id", job.engagement_id)
        payload.setdefault("agent_id", job.agent_id)
        payload.setdefault("job_id", job.id)
        payload.setdefault("prospect_id", job.prospect_id)
        payload["mailbox_id"] = mailbox.id

        sent = await router.dispatch_email(mailbox_id=mailbox.id, payload=payload)
        if not sent:
            return AdapterResultData.fail(
                "email dispatch failed through selected mailbox",
                retryable=True,
                mailbox_id=mailbox.id,
            )
        return AdapterResultData.ok(sent=True, mailbox_id=mailbox.id)

    def _tenant_id_for(self, job: Job) -> Optional[str]:
        tenant_id = job.payload.get("tenant_id") if isinstance(job.payload, dict) else None
        if tenant_id:
            return str(tenant_id)
        resolver = getattr(self._store, "get_engagement_tenant_id", None)
        if callable(resolver):
            resolved = resolver(job.engagement_id)
            return str(resolved) if resolved else None
        return None
