"""Celery task shims for tenant-scoped agent execution."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from engine.runtime.context import ExecutionResult, TenantContext
from engine.worker import celery_app


@celery_app.task(name="engine.tasks.dispatch_agent_task")
def dispatch_agent_task(
    task_name: str,
    payload: dict[str, Any],
    tenant_context: dict[str, Any],
) -> dict[str, Any]:
    """Execute a dispatched agent task."""
    started = time.perf_counter()
    context = TenantContext.model_validate(tenant_context)

    if task_name in {"email_send", "email.send"}:
        result = asyncio.run(
            dispatch_email_send_task(
                payload=dict(payload),
                context=context,
                started=started,
            )
        )
        return result.model_dump()

    result = ExecutionResult(
        success=True,
        output={
            "task_name": task_name,
            "payload": dict(payload),
            "tenant_id": context.tenant_id,
            "campaign_id": context.campaign_id,
        },
        duration_ms=max((time.perf_counter() - started) * 1000.0, 0.001),
    )
    return result.model_dump()


async def dispatch_email_send_task(
    *,
    payload: dict[str, Any],
    context: TenantContext,
    started: float | None = None,
) -> ExecutionResult:
    """Health-gated production dispatch for approved HITL email jobs."""

    from engine import open_storage
    from engine.dispatch.provider import SMTPProvider
    from engine.dispatch.router import SmartInboxRouter
    from engine.services.mailbox_health import MailboxHealthMonitor

    started = started if started is not None else time.perf_counter()
    db_url = os.getenv("DATABASE_URL") or os.getenv("AUTOREACH_DB", "sqlite:///autoreach_engine.db")
    store, events, ledger = open_storage(db_url)
    health_monitor = MailboxHealthMonitor(store=store, events=events)
    provider = SMTPProvider(store=store, events=events, ledger=ledger)
    router = SmartInboxRouter(
        health_monitor=health_monitor,
        provider=provider,
        store=store,
    )

    mailbox = await router.get_next_available_mailbox(tenant_id=context.tenant_id)
    if mailbox is None:
        return ExecutionResult(
            success=False,
            error="no healthy mailbox available for tenant",
            output={"tenant_id": context.tenant_id},
            duration_ms=max((time.perf_counter() - started) * 1000.0, 0.001),
        )

    enriched_payload = dict(payload)
    enriched_payload.setdefault("tenant_id", context.tenant_id)
    enriched_payload.setdefault("campaign_id", context.campaign_id)
    enriched_payload.setdefault("engagement_id", context.campaign_id)
    enriched_payload["mailbox_id"] = mailbox.id
    sent = await router.dispatch_email(mailbox_id=mailbox.id, payload=enriched_payload)
    return ExecutionResult(
        success=bool(sent),
        output={
            "task_name": "email_send",
            "tenant_id": context.tenant_id,
            "campaign_id": context.campaign_id,
            "mailbox_id": mailbox.id,
            "sent": bool(sent),
        },
        error=None if sent else "email dispatch failed",
        duration_ms=max((time.perf_counter() - started) * 1000.0, 0.001),
    )
