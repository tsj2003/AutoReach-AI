"""
ConsoleEmailAdapter — sends "emails" to stdout / a captured list.

This is the dev/test adapter. Use it to:
    * exercise the full Job lifecycle without touching real Gmail
    * write fast deterministic integration tests
    * preview what the live engine *would* send before flipping to Gmail

Inputs (from `job.payload`):
    to_email, to_name, company, title, offer, subject_template, body_template

Outputs (to `job.result`):
    rendered_subject, rendered_body, sent_at_iso
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from engine.core.protocols import AdapterContext
from engine.core.types import EventKind, Event, Job, JobKind
from engine.runtime.results import AdapterResultData

logger = logging.getLogger(__name__)


def _render(template: str, data: dict) -> str:
    """Tiny safe-format that only substitutes provided keys."""
    out = template
    for k, v in data.items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    return out


class ConsoleEmailAdapter:
    """Pretend-send emails. Captures every send for inspection."""

    name = "email.console"

    def __init__(self) -> None:
        # In-memory log of every send, oldest first. Useful in tests.
        self.outbox: list[dict] = []

    def handles(self, job: Job) -> bool:
        return job.kind == JobKind.EMAIL_SEND

    def execute(self, job: Job, *, context: AdapterContext) -> AdapterResultData:
        p = dict(job.payload)
        # First substitute the offer into body, then {to_name} etc.
        body_template = p.get("body_template", "")
        subject_template = p.get("subject_template", "")
        rendering_data = {
            "to_name": p.get("to_name") or "there",
            "company": p.get("company") or "",
            "title": p.get("title") or "",
            "offer": p.get("offer") or "",
        }
        rendered_body = _render(body_template, rendering_data)
        rendered_subject = _render(subject_template, rendering_data)

        # Sanity: must have a recipient.
        to_email: Optional[str] = p.get("to_email")
        if not to_email:
            return AdapterResultData.fail("missing to_email", retryable=False)

        sent_at = datetime.now(timezone.utc).isoformat()
        record = {
            "to": to_email,
            "subject": rendered_subject,
            "body": rendered_body,
            "sent_at": sent_at,
            "job_id": job.id,
        }
        self.outbox.append(record)
        logger.info(
            "[console-email] -> %s | %s",
            to_email,
            rendered_subject[:80],
        )

        # Emit a domain event the platform UI/analytics consume.
        context.emit(
            Event(
                id=f"ev_console_{job.id}",
                kind=EventKind.EMAIL_SENT,
                engagement_id=job.engagement_id,
                agent_id=job.agent_id,
                job_id=job.id,
                prospect_id=job.prospect_id,
                payload={
                    "to": to_email,
                    "subject_chars": len(rendered_subject),
                    "body_chars": len(rendered_body),
                    "via": "console",
                },
            )
        )

        return AdapterResultData.ok(
            rendered_subject=rendered_subject,
            rendered_body=rendered_body,
            sent_at_iso=sent_at,
        )
