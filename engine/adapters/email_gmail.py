"""
GmailEmailAdapter — sends real email through the Gmail API.

Wraps the OAuth + MIME construction logic that lives in `app/worker.py` but
re-shapes it as a clean Adapter implementation. The adapter is stateless from
the engine's view; it expects a `gmail_credentials_provider` callable that
returns `google.oauth2.credentials.Credentials` for the configured sender.

Inputs (from `job.payload`):
    to_email, to_name, company, title, offer
    subject_template, body_template
    optional: from_name, attachment_paths (list of absolute paths)

Outputs (to `job.result`):
    gmail_message_id, gmail_thread_id, sent_at_iso, rendered_subject, rendered_body

Failure semantics
-----------------
* missing payload fields → non-retryable failure (caller bug, retry won't help)
* transient HttpError (rate limit, 5xx, network) → retryable
* invalid_grant / refresh failures → non-retryable (operator must reconnect)
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from datetime import datetime, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from typing import Callable, Iterable, Optional

from engine.core.protocols import AdapterContext
from engine.core.types import Event, EventKind, Job, JobKind
from engine.runtime.results import AdapterResultData

logger = logging.getLogger(__name__)


def _render(template: str, data: dict) -> str:
    out = template
    for k, v in data.items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    return out


def _build_mime(
    *,
    sender: str,
    to: str,
    subject: str,
    body: str,
    attachment_paths: Iterable[str] = (),
) -> str:
    """Construct a Gmail-compatible base64url-encoded MIME message."""
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in attachment_paths:
        if not path or not os.path.exists(path):
            continue
        ctype, encoding = mimetypes.guess_type(path)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(path)}"',
        )
        msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


class GmailEmailAdapter:
    """
    Real-Gmail adapter.

    Parameters
    ----------
    sender_email : str
        The "From" address. Must be the authorized Gmail / Workspace user.
    credentials_provider : Callable[[], google.oauth2.credentials.Credentials]
        Returns fresh Credentials on every send. Lets the operator implement
        token storage / refresh however they like (DB row, JSON file, vault).
    """

    name = "email.gmail"

    def __init__(
        self,
        *,
        sender_email: str,
        credentials_provider: Callable[[], "object"],  # google Credentials
        gmail_build: Optional[Callable] = None,
        send_cost_cents: int = 1,
    ) -> None:
        self._sender_email = sender_email
        self._creds_provider = credentials_provider
        self._gmail_build = gmail_build  # injectable for tests
        self._send_cost_cents = send_cost_cents

    def handles(self, job: Job) -> bool:
        return job.kind == JobKind.EMAIL_SEND

    def execute(self, job: Job, *, context: AdapterContext) -> AdapterResultData:
        p = dict(job.payload)
        to_email = p.get("to_email")
        if not to_email:
            return AdapterResultData.fail("missing to_email", retryable=False)

        rendering_data = {
            "to_name": p.get("to_name") or "there",
            "company": p.get("company") or "",
            "title": p.get("title") or "",
            "offer": p.get("offer") or "",
        }
        subject = _render(p.get("subject_template", ""), rendering_data).strip()
        body = _render(p.get("body_template", ""), rendering_data)

        if not subject or not body:
            return AdapterResultData.fail(
                "subject and body must render to non-empty strings",
                retryable=False,
            )

        # Build MIME up-front (no network) so failures here are clearly local bugs.
        try:
            raw = _build_mime(
                sender=self._sender_email,
                to=to_email,
                subject=subject,
                body=body,
                attachment_paths=p.get("attachment_paths") or (),
            )
        except Exception as exc:  # malformed input
            return AdapterResultData.fail(
                f"mime construction failed: {exc}",
                retryable=False,
            )

        # Get credentials. Failures here are usually operator config issues
        # (token expired, scopes wrong); not retryable until they reconnect.
        try:
            creds = self._creds_provider()
        except Exception as exc:
            return AdapterResultData.fail(
                f"credentials unavailable: {exc}",
                retryable=False,
            )

        # Build the Gmail client lazily so the import doesn't blow up tests
        # that don't actually need Google libs.
        try:
            if self._gmail_build is None:
                from googleapiclient.discovery import build  # type: ignore

                gmail = build("gmail", "v1", credentials=creds)
            else:
                gmail = self._gmail_build(creds)
        except Exception as exc:
            return AdapterResultData.fail(
                f"gmail client init failed: {exc}",
                retryable=True,
            )

        # Send.
        try:
            response = (
                gmail.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
        except Exception as exc:
            # Treat 4xx auth-style errors as non-retryable, everything else as retryable.
            err = repr(exc)
            non_retryable_signals = ("invalid_grant", "401", "403", "Forbidden", "insufficient")
            retryable = not any(sig in err for sig in non_retryable_signals)
            return AdapterResultData.fail(
                f"gmail send failed: {exc}",
                retryable=retryable,
            )

        sent_at = datetime.now(timezone.utc).isoformat()
        message_id = response.get("id") if isinstance(response, dict) else None
        thread_id = response.get("threadId") if isinstance(response, dict) else None

        # Record domain event + cost.
        context.emit(
            Event(
                id=f"ev_gmail_{job.id}",
                kind=EventKind.EMAIL_SENT,
                engagement_id=job.engagement_id,
                agent_id=job.agent_id,
                job_id=job.id,
                prospect_id=job.prospect_id,
                payload={
                    "to": to_email,
                    "via": "gmail",
                    "gmail_message_id": message_id,
                    "gmail_thread_id": thread_id,
                },
            )
        )
        from engine.core.types import CostEntry  # local import to keep top tidy

        context.debit(
            CostEntry(
                id=f"cost_gmail_{job.id}",
                engagement_id=job.engagement_id,
                job_id=job.id,
                category="email_send",
                amount_cents=self._send_cost_cents,
                metadata={"channel": "gmail"},
            )
        )

        return AdapterResultData.ok(
            gmail_message_id=message_id,
            gmail_thread_id=thread_id,
            sent_at_iso=sent_at,
            rendered_subject=subject,
            rendered_body=body,
        )
