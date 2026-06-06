"""
RealGmailSendAdapter — production Gmail send with token store, dry-run,
and explicit error classification.

Differences vs `engine.adapters.email_gmail.GmailEmailAdapter`
--------------------------------------------------------------
* Pulls credentials through a `GmailTokenStore`, not a callable.
  This is the wedge for multi-mailbox rotation later.
* Honors `Retry-After` on HTTP 429 by setting `Job.not_before`.
* Distinguishes 429 from generic 5xx and emits a dedicated
  `email.rate_limited` event.
* Distinguishes invalid_grant / 401 / 403 from generic 4xx and emits a
  `gmail.token_invalid` event the cockpit can render as a banner.
* Constructor takes `dry_run` flag (default reads `AUTOREACH_GMAIL_DRY_RUN`).
  Dry-run runs the full path (auth fetch, MIME build, token validation) but
  stops short of the network call. Emits `email.dry_run` with a payload preview.
* Supports `thread_id` for in-thread replies (Phase 3 reply pipeline).
* Supports both pre-rendered `subject`/`body_text` and template fields
  (`subject_template`/`body_template`) — adapter renders if templates given.
* Supports optional `body_html` (multipart/alternative).

Payload contract (Job.payload)
------------------------------
Required:
    to_email           str

One of:
    subject            str   (already rendered)
    subject_template   str   (rendered against payload data)
And one of:
    body_text          str
    body_template      str

Optional:
    body_html          str   (rendered HTML alternative; templated if rendered=False)
    thread_id          str   (Gmail threadId, for replies)
    in_reply_to        str   (RFC 5322 message-id; sets In-Reply-To + References)
    attachment_paths   list[str]
    to_name, company, title, offer  (rendering data)

Result (Job.result)
-------------------
On success:
    sent | dry_run            bool
    gmail_message_id          str | None
    gmail_thread_id           str | None
    rendered_subject          str
    rendered_body_text        str
    sent_at_iso               str
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import re
from datetime import datetime, timedelta, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from typing import Iterable, Optional

from engine.adapters.gmail_token_store import (
    GmailTokenStore,
    TokenInvalid,
    TokenUnavailable,
)
from engine.core.protocols import AdapterContext
from engine.core.types import CostEntry, Event, EventKind, Job, JobKind
from engine.runtime.results import AdapterResultData

logger = logging.getLogger(__name__)


# Patterns that classify Google API errors. We match on `repr(exc)` to
# survive both googleapiclient.HttpError and the various wrappers.
_NON_RETRYABLE_AUTH_PATTERNS = (
    "invalid_grant",
    "Token has been expired or revoked",
    "Invalid Credentials",
    "Insufficient Permission",
    "insufficient_scope",
    "User-rate limit",  # different — quota exhaustion vs token error
    " 401 ",
    " 403 ",
)


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
    body_text: str,
    body_html: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    attachment_paths: Iterable[str] = (),
) -> str:
    has_attachments = any(attachment_paths)
    if has_attachments:
        outer: MIMEBase = MIMEMultipart("mixed")
    elif body_html:
        outer = MIMEMultipart("alternative")
    else:
        outer = MIMEText(body_text, "plain", "utf-8")

    if isinstance(outer, MIMEMultipart):
        if body_html:
            inner = MIMEMultipart("alternative")
            inner.attach(MIMEText(body_text, "plain", "utf-8"))
            inner.attach(MIMEText(body_html, "html", "utf-8"))
            outer.attach(inner)
        else:
            outer.attach(MIMEText(body_text, "plain", "utf-8"))

    outer["From"] = sender
    outer["To"] = to
    outer["Subject"] = subject
    if in_reply_to:
        outer["In-Reply-To"] = in_reply_to
        outer["References"] = in_reply_to

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
        outer.attach(part)  # type: ignore[union-attr]

    raw_bytes = outer.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")


def _classify_send_error(exc: BaseException) -> tuple[str, bool, Optional[int]]:
    """
    Return (kind, retryable, retry_after_seconds).

    `kind` is one of: 'rate_limited' | 'token_invalid' | 'transient' | 'fatal'.
    `retry_after_seconds` is set only for rate-limit responses if Gmail
    provides one; otherwise None and the runtime uses default backoff.
    """
    err = repr(exc)
    status = _extract_status_code(exc)
    retry_after = _extract_retry_after(exc)

    # Token problems first — these are never retryable until operator acts.
    for pat in _NON_RETRYABLE_AUTH_PATTERNS:
        if pat in err:
            return "token_invalid", False, None
    if status in (401, 403):
        return "token_invalid", False, None

    # Rate limits — retryable, honor Retry-After if Gmail gave us one.
    if status == 429 or "rateLimitExceeded" in err or "userRateLimitExceeded" in err:
        return "rate_limited", True, retry_after

    # Server errors — retryable.
    if status is not None and 500 <= status < 600:
        return "transient", True, retry_after

    # Other 4xx — non-retryable (bad request, recipient invalid, etc.).
    if status is not None and 400 <= status < 500:
        return "fatal", False, None

    # Network / unknown — assume retryable.
    return "transient", True, None


def _extract_status_code(exc: BaseException) -> Optional[int]:
    # googleapiclient.HttpError.resp.status
    resp = getattr(exc, "resp", None)
    if resp is not None and hasattr(resp, "status"):
        try:
            return int(resp.status)
        except (TypeError, ValueError):
            pass
    # Fallback: dig out a 3-digit code from the repr.
    m = re.search(r"\b(4\d\d|5\d\d|429)\b", repr(exc))
    return int(m.group(1)) if m else None


def _extract_retry_after(exc: BaseException) -> Optional[int]:
    """Read `Retry-After` from an HttpError's response headers, if any."""
    resp = getattr(exc, "resp", None)
    if resp is None:
        return None
    headers = getattr(resp, "_headers", None) or getattr(resp, "headers", None)
    if not headers:
        return None
    for k, v in headers.items() if hasattr(headers, "items") else []:
        if str(k).lower() == "retry-after":
            try:
                return max(0, int(str(v).strip()))
            except ValueError:
                return None
    return None


class RealGmailSendAdapter:
    """Production Gmail send adapter."""

    name = "email.gmail"

    def __init__(
        self,
        *,
        sender_email: str,
        token_store: GmailTokenStore,
        dry_run: Optional[bool] = None,
        gmail_build: Optional[callable] = None,  # type: ignore[type-arg]
        send_cost_cents: int = 1,
    ) -> None:
        if dry_run is None:
            dry_run = os.getenv("AUTOREACH_GMAIL_DRY_RUN", "").strip().lower() in (
                "1", "true", "yes", "on",
            )
        self._sender_email = sender_email
        self._tokens = token_store
        self._dry_run = bool(dry_run)
        self._gmail_build = gmail_build
        self._send_cost_cents = send_cost_cents

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def handles(self, job: Job) -> bool:
        return job.kind == JobKind.EMAIL_SEND

    def execute(self, job: Job, *, context: AdapterContext) -> AdapterResultData:
        # 1. Read & validate payload.
        p = dict(job.payload)
        to_email = (p.get("to_email") or "").strip()
        if not to_email:
            return AdapterResultData.fail("missing to_email", retryable=False)

        rendering_data = {
            "to_name": p.get("to_name") or "there",
            "company": p.get("company") or "",
            "title": p.get("title") or "",
            "offer": p.get("offer") or "",
        }
        subject = (p.get("subject") or _render(p.get("subject_template", ""), rendering_data)).strip()
        body_text = p.get("body_text") or _render(p.get("body_template", ""), rendering_data)
        body_html = p.get("body_html")
        if body_html and "{" in body_html and "}" in body_html:
            body_html = _render(body_html, rendering_data)

        if not subject or not body_text:
            return AdapterResultData.fail(
                "subject and body_text must be non-empty after rendering",
                retryable=False,
            )

        # 2. Build MIME (catches malformed input before the network).
        try:
            raw = _build_mime(
                sender=self._sender_email,
                to=to_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                in_reply_to=p.get("in_reply_to"),
                attachment_paths=p.get("attachment_paths") or (),
            )
        except Exception as exc:
            return AdapterResultData.fail(
                f"mime construction failed: {exc}",
                retryable=False,
            )

        # 3. Load credentials. Token problems are non-retryable.
        try:
            creds = self._tokens.load()
        except TokenUnavailable as exc:
            return AdapterResultData.fail(
                f"gmail token unavailable: {exc}",
                retryable=False,
            )
        except TokenInvalid as exc:
            context.emit(
                Event(
                    id=f"ev_token_invalid_{job.id}",
                    kind=EventKind.GMAIL_TOKEN_INVALID,
                    engagement_id=job.engagement_id,
                    agent_id=job.agent_id,
                    job_id=job.id,
                    prospect_id=job.prospect_id,
                    payload={"reason": str(exc)},
                )
            )
            return AdapterResultData.fail(
                f"gmail token invalid: {exc}",
                retryable=False,
            )

        # 4. Dry-run path: full validation + event, but no network call.
        if self._dry_run:
            sent_at = datetime.now(timezone.utc).isoformat()
            preview = body_text[:240] + ("…" if len(body_text) > 240 else "")
            context.emit(
                Event(
                    id=f"ev_dryrun_{job.id}",
                    kind=EventKind.EMAIL_DRY_RUN,
                    engagement_id=job.engagement_id,
                    agent_id=job.agent_id,
                    job_id=job.id,
                    prospect_id=job.prospect_id,
                    payload={
                        "to": to_email,
                        "subject": subject,
                        "body_preview": preview,
                        "thread_id": p.get("thread_id"),
                        "via": "gmail.dry_run",
                    },
                )
            )
            return AdapterResultData.ok(
                sent=False,
                dry_run=True,
                gmail_message_id=None,
                gmail_thread_id=p.get("thread_id"),
                rendered_subject=subject,
                rendered_body_text=body_text,
                sent_at_iso=sent_at,
            )

        # 5. Build Gmail client.
        try:
            if self._gmail_build is None:
                from googleapiclient.discovery import build  # type: ignore

                gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
            else:
                gmail = self._gmail_build(creds)
        except Exception as exc:
            return AdapterResultData.fail(
                f"gmail client init failed: {exc}",
                retryable=True,
            )

        # 6. Send.
        body: dict[str, object] = {"raw": raw}
        thread_id = p.get("thread_id")
        if thread_id:
            body["threadId"] = thread_id

        try:
            response = (
                gmail.users()
                .messages()
                .send(userId="me", body=body)
                .execute()
            )
        except Exception as exc:
            kind, retryable, retry_after = _classify_send_error(exc)

            if kind == "token_invalid":
                self._tokens.mark_invalid(repr(exc)[:500])
                context.emit(
                    Event(
                        id=f"ev_token_invalid_{job.id}",
                        kind=EventKind.GMAIL_TOKEN_INVALID,
                        engagement_id=job.engagement_id,
                        agent_id=job.agent_id,
                        job_id=job.id,
                        prospect_id=job.prospect_id,
                        payload={"reason": repr(exc)[:500]},
                    )
                )
            elif kind == "rate_limited":
                # Set Job.not_before so the runtime won't pick it up before
                # Gmail's recommended Retry-After. Fallback: 60 seconds.
                delay_secs = retry_after if retry_after is not None else 60
                job.not_before = datetime.now(timezone.utc) + timedelta(seconds=delay_secs)
                context.emit(
                    Event(
                        id=f"ev_rate_limited_{job.id}",
                        kind=EventKind.EMAIL_RATE_LIMITED,
                        engagement_id=job.engagement_id,
                        agent_id=job.agent_id,
                        job_id=job.id,
                        prospect_id=job.prospect_id,
                        payload={"retry_after_seconds": delay_secs, "reason": repr(exc)[:500]},
                    )
                )

            logger.warning(
                "gmail send failed (kind=%s, retryable=%s): %s",
                kind, retryable, exc,
            )
            return AdapterResultData.fail(
                f"gmail send failed [{kind}]: {exc}",
                retryable=retryable,
            )

        # 7. Success — persist refreshed creds, record event + cost.
        try:
            self._tokens.save(creds)  # google-auth may have refreshed in-place
        except Exception as exc:  # pragma: no cover - non-fatal
            logger.warning("could not persist refreshed token: %s", exc)

        sent_at = datetime.now(timezone.utc).isoformat()
        message_id = response.get("id") if isinstance(response, dict) else None
        gmail_thread_id = response.get("threadId") if isinstance(response, dict) else None

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
                    "gmail_thread_id": gmail_thread_id,
                    "thread_id_requested": thread_id,
                },
            )
        )
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
            sent=True,
            dry_run=False,
            gmail_message_id=message_id,
            gmail_thread_id=gmail_thread_id,
            rendered_subject=subject,
            rendered_body_text=body_text,
            sent_at_iso=sent_at,
        )
