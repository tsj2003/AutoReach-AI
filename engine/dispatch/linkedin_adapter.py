"""Runtime adapter: approved LinkedIn sequence jobs → Voyager seat actions."""

from __future__ import annotations

import logging
from typing import Any, Optional

from engine.core.protocols import AdapterContext
from engine.core.types import Event, EventKind, Job, JobKind
from engine.dispatch.linkedin import get_active_linkedin_provider
from engine.runtime.results import AdapterResultData

logger = logging.getLogger(__name__)


def normalize_voyager_step_type(raw: str | None) -> str:
    """Map Gojiberry / UI step kinds onto Voyager dispatch actions."""
    kind = str(raw or "").strip()
    key = kind.lower().replace("-", "").replace("_", "")
    mapping = {
        "visitprofile": "visitProfile",
        "linkedinvisit": "visitProfile",
        "likeposts": "likePosts",
        "linkedinlike": "likePosts",
        "invitation": "invitation",
        "invitationnote": "invitationNote",
        "linkedinconnect": "invitationNote",
        "connectionrequest": "invitation",
        "connectionnote": "invitationNote",
        "message": "message",
        "linkedinmessage": "message",
        "linkedindm": "message",
        "linkedin": "message",
        "comment": "commentOnPost",
        "commentonpost": "commentOnPost",
        "linkedincomment": "commentOnPost",
        "voicemessage": "message",
        "voicenote": "message",
        "linkedinvoicenote": "message",
    }
    return mapping.get(key, kind or "message")


class LinkedInVoyagerAdapter:
    """Execute Gojiberry-style LinkedIn steps via an encrypted Voyager seat."""

    name = "linkedin.voyager"

    def __init__(self, *, store: Any, events: Any = None, ledger: Any = None) -> None:
        self._store = store
        self._events = events
        self._ledger = ledger

    def handles(self, job: Job) -> bool:
        if job.kind == JobKind.LINKEDIN_ACTION:
            return True
        if job.kind != JobKind.EMAIL_SEND:
            return False
        payload = job.payload if isinstance(job.payload, dict) else {}
        return str(payload.get("channel") or "").lower() == "linkedin"

    def execute(self, job: Job, *, context: AdapterContext) -> AdapterResultData:
        payload = dict(job.payload or {})
        tenant_id = self._tenant_id_for(job)
        if not tenant_id:
            return AdapterResultData.fail("tenant_id required for LinkedIn dispatch", retryable=False)

        raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
        profile_url = (
            payload.get("linkedin_url")
            or payload.get("profile_url")
            or raw.get("linkedin_url")
        )
        if not profile_url:
            return AdapterResultData.fail("missing linkedin_url for LinkedIn step", retryable=False)

        step_type = normalize_voyager_step_type(
            payload.get("step_type") or payload.get("voyager_action") or payload.get("kind")
        )
        seat_id = payload.get("linkedin_seat_id")
        try:
            provider = get_active_linkedin_provider(self._store, tenant_id, seat_id=seat_id)
        except Exception as exc:
            return AdapterResultData.fail(f"linkedin seat load failed: {exc}", retryable=True)

        if not provider.has_cookie:
            return AdapterResultData.fail(
                "No LinkedIn Voyager seat connected. Connect under Operations → LinkedIn.",
                retryable=False,
            )

        try:
            if step_type == "visitProfile":
                res = provider.visit_profile_sync(str(profile_url))
                external_id = f"li_visit_{res.get('entity_urn', job.id)}"
            elif step_type == "likePosts":
                res = provider.like_posts_sync(str(profile_url), count=int(payload.get("count") or 2))
                external_id = f"li_like_{job.id}"
            elif step_type == "commentOnPost":
                comment = payload.get("body") or payload.get("body_text") or payload.get("comment") or ""
                res = provider.comment_on_post_sync(
                    str(profile_url),
                    comment_text=str(comment),
                    activity_urn=payload.get("activity_urn"),
                )
                external_id = f"li_comment_{job.id}"
            elif step_type in ("invitation", "invitationNote"):
                note = None
                if step_type == "invitationNote":
                    note = payload.get("body") or payload.get("body_text") or payload.get("note")
                res = provider.send_invitation_sync(str(profile_url), custom_message=note)
                external_id = f"li_inv_{res.get('inviteeProfileUrn', job.id)}"
            else:
                body = payload.get("body") or payload.get("body_text") or "Hi — wanted to connect."
                split_bubbles = bool(
                    payload.get("splitLinkedinMessagesIntoConversation")
                    or payload.get("split_into_conversation")
                )
                res = provider.send_message_sync(
                    str(profile_url),
                    str(body),
                    split_into_conversation=split_bubbles,
                )
                external_id = str(res.get("linkedinMessageBackendUrn") or f"li_msg_{job.id}")
        except Exception as exc:
            logger.exception("linkedin voyager action failed job=%s", job.id)
            return AdapterResultData.fail(f"linkedin action failed: {exc}", retryable=True)

        mode = str((res or {}).get("mode") or provider.mode or "")
        if mode == "dry_run_no_cookie":
            return AdapterResultData.fail(
                "LinkedIn seat has no live cookie — reconnect LinkedIn.",
                retryable=False,
            )

        context.emit(
            Event(
                id=f"ev_li_{job.id}",
                kind=EventKind.LINKEDIN_SENT,
                engagement_id=job.engagement_id,
                agent_id=job.agent_id,
                job_id=job.id,
                prospect_id=job.prospect_id,
                payload={
                    "step_type": step_type,
                    "external_id": external_id,
                    "linkedin_url": profile_url,
                    "mode": mode,
                },
            )
        )

        return AdapterResultData.ok(
            sent=True,
            channel="linkedin",
            step_type=step_type,
            external_id=external_id,
            mode=mode,
        )

    def _tenant_id_for(self, job: Job) -> Optional[str]:
        payload = job.payload if isinstance(job.payload, dict) else {}
        tenant_id = payload.get("tenant_id")
        if tenant_id:
            return str(tenant_id)
        resolver = getattr(self._store, "get_engagement_tenant_id", None)
        if callable(resolver):
            resolved = resolver(job.engagement_id)
            return str(resolved) if resolved else None
        return None
