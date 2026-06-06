"""
OutboundAgentV1 — the first concrete AgentRunner.

Plans first-touch email Jobs for prospects in `status='new'`. Honors the
HITL trust ramp: the first N sends per Engagement (configurable) require
human approval before they go out, defaulting to 50.

Personalization (Phase 3 step 6)
--------------------------------
If the runner has been constructed with a `GeminiClient`, every planned
Job is personalized: subject + body are LLM-rewritten using the prospect's
known fields (name, company, title, plus a small whitelist of CSV columns).
The rewritten subject/body are baked into `job.payload` as `subject` /
`body_text` (pre-rendered), so adapters send the personalized version
without re-templating.

If Gemini is unavailable / fails, we fall back to the raw template-with-
placeholder-substitution behavior — the email still goes out, just generic.
The runner records `personalized=False` + `personalization_error=...` in
the payload so the cockpit can surface a yellow flag.

Reverse-targeting note
----------------------
Personalization here uses ONLY the prospect's known fields. It does not
audit the prospect's website / GitHub / job posts / funding. The audit
engine (Phase 6) is gated behind `Engagement.client_cure` per
`docs/PLATFORM.md` and is not yet wired.

Deliberately simple in v1
-------------------------
    * no follow-up sequencing yet (Phase 4 will add multi-step)
    * no per-prospect research yet (Phase 6, behind client_cure)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from engine.core.protocols import AgentContext, CostLedger
from engine.core.types import Agent, CostEntry, Job, JobKind
from engine.llm import GeminiClient, personalize_outbound

logger = logging.getLogger(__name__)


def _deterministic_job_id(engagement_id: str, prospect_id: str, kind: str, step: int) -> str:
    """
    Deterministic job ID so re-running plan() is idempotent.

    If we naively used random IDs, every plan() call would queue a
    duplicate first-touch email for every new prospect. Hashing the
    (engagement, prospect, kind, step) tuple keeps planning safe to
    call repeatedly, which is critical for crash-resume semantics.
    """
    h = hashlib.sha1(f"{engagement_id}|{prospect_id}|{kind}|{step}".encode()).hexdigest()[:16]
    return f"job_{h}"


class OutboundAgentV1:
    """First-touch email scheduler. See module docstring."""

    runner_kind = "outbound.v1"

    # Default trust-ramp: first 50 sends per engagement require approval.
    DEFAULT_HITL_THRESHOLD = 50

    def __init__(
        self,
        *,
        gemini: Optional[GeminiClient] = None,
        ledger: Optional[CostLedger] = None,
    ) -> None:
        """
        Parameters
        ----------
        gemini : GeminiClient | None
            When provided, jobs are LLM-personalized at plan time. When None,
            jobs use the raw subject_template / body_template with placeholder
            substitution (existing Phase 1 behavior).
        ledger : CostLedger | None
            When provided, personalization LLM cost is debited at plan time.
            Optional; the cockpit always passes one, tests usually don't.
        """
        self._gemini = gemini
        self._ledger = ledger

    def plan(self, agent: Agent, *, context: AgentContext) -> Iterable[Job]:
        engagement = context.get_engagement(agent.engagement_id)
        if engagement is None or engagement.status != "active":
            return []

        # How many sends has this engagement done so far? Anything past the
        # threshold sends without approval; below it, every job blocks at HITL.
        threshold = int(agent.config.get("hitl_threshold", self.DEFAULT_HITL_THRESHOLD))
        sent_so_far = sum(
            1
            for ev in context.list_recent_events(engagement.id, limit=1000)
            if ev.kind.value == "email.sent"
        )
        requires_approval = sent_so_far < threshold

        # How fast to send: minimum gap between consecutive jobs.
        gap_seconds = int(agent.config.get("send_gap_seconds", 90))

        # Per-tick batch cap, so we don't enqueue thousands at once.
        batch = int(agent.config.get("plan_batch_size", 10))

        new_prospects = list(
            context.list_prospects(engagement.id, status="new", limit=batch)
        )
        # Configurable per-engagement override: agent.config["personalize"] = False
        # turns off the LLM rewrite even if a GeminiClient is wired.
        personalize_enabled = bool(agent.config.get("personalize", True)) and self._gemini is not None

        subject_template = agent.config.get(
            "subject_template", "Quick question for {first_name}"
        )
        body_template = agent.config.get(
            "body_template",
            "Hi {first_name},\n\n{offer}\n\nWorth a 15-minute chat?\n\n— Sent via AutoReach",
        )

        now = datetime.now(timezone.utc)
        jobs: list[Job] = []
        for i, prospect in enumerate(new_prospects):
            if not prospect.email:
                continue  # nothing to send to
            scheduled = now + timedelta(seconds=gap_seconds * i)

            payload: dict = {
                "to_email": prospect.email,
                "to_name": prospect.full_name or "",
                "company": prospect.company or "",
                "title": prospect.title or "",
                "step": 1,
                "offer": engagement.offer,
                # Always include templates as fallback. Adapters use these
                # if `subject` / `body_text` aren't already pre-rendered.
                "subject_template": subject_template,
                "body_template": body_template,
            }

            if personalize_enabled:
                # Build the field map the personalizer needs.
                prospect_fields = {
                    "full_name": prospect.full_name or "",
                    "title": prospect.title or "",
                    "company": prospect.company or "",
                    "raw": dict(prospect.raw or {}),
                }
                # Render the offer into the template so Gemini sees the
                # full pitch, not a placeholder.
                base_subject = subject_template.replace("{offer}", engagement.offer or "")
                base_body = body_template.replace("{offer}", engagement.offer or "")

                pres = personalize_outbound(
                    subject_template=base_subject,
                    body_template=base_body,
                    prospect_fields=prospect_fields,
                    client=self._gemini,
                )

                # Bake the rendered version into the payload — adapters
                # check `subject` / `body_text` first.
                payload["subject"] = pres.subject
                payload["body_text"] = pres.body_text
                payload["personalized"] = not pres.fallback_used
                payload["personalization_used_fields"] = list(pres.used_fields)
                if pres.fallback_used:
                    payload["personalization_error"] = pres.error or "fallback used"

                # Debit cost ledger for the LLM call (if wired).
                if pres.estimated_cost_cents > 0 and self._ledger is not None:
                    self._ledger.debit(
                        CostEntry(
                            id=f"cost_pers_{_deterministic_job_id(engagement.id, prospect.id, 'email.send', 1)}",
                            engagement_id=engagement.id,
                            job_id=_deterministic_job_id(
                                engagement.id, prospect.id, "email.send", 1,
                            ),
                            category="llm",
                            amount_cents=pres.estimated_cost_cents,
                            metadata={"purpose": "outbound_personalize"},
                        )
                    )

            jobs.append(
                Job(
                    id=_deterministic_job_id(engagement.id, prospect.id, "email.send", 1),
                    engagement_id=engagement.id,
                    agent_id=agent.id,
                    kind=JobKind.EMAIL_SEND,
                    payload=payload,
                    prospect_id=prospect.id,
                    requires_approval=requires_approval,
                    scheduled_for=scheduled,
                )
            )
        return jobs
