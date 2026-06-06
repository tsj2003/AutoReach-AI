"""
OutboundAgentV1 — multi-step outbound sequence runner.

Plans email Jobs for prospects, supporting a configurable follow-up sequence:
each step has its own subject/body template and a delay (in days) measured
from the previous send. The agent stops a prospect's sequence the moment they
reply, book, or unsubscribe.

Sequence config (agent.config["sequence"])
-------------------------------------------
A list of steps. Step 1 (index 0) is the first touch (delay ignored).

    "sequence": [
        {"subject_template": "Quick question for {first_name}",
         "body_template": "Hi {first_name}, {offer} ..."},
        {"wait_days": 3,
         "subject_template": "Re: quick question",
         "body_template": "Hi {first_name}, following up ..."},
        {"wait_days": 5,
         "subject_template": "Last note",
         "body_template": "Closing the loop, {first_name} ..."},
    ]

Backward compatibility
----------------------
If no `sequence` is configured, the agent uses the single-step behaviour
(subject_template / body_template config keys) exactly as before — one
first-touch email per prospect, no follow-ups.

How "next step" is determined
-----------------------------
For each prospect we count their `email.sent` events:
    sent_count == 0  → send step 1 (first touch)
    sent_count >= 1  → if a next step exists AND the per-step delay has
                       elapsed since the last send → send it
A prospect whose status is replied / booked / unsubscribed is skipped — their
sequence is over.

Personalization (Phase 3 step 6) applies per step, unchanged.

Idempotency
-----------
Job IDs are deterministic on (engagement, prospect, kind, step), so re-running
plan() never duplicates a step. Crash-resume safe.
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

# A prospect in any of these statuses has finished its sequence.
_TERMINAL_PROSPECT_STATUSES = frozenset({"replied", "booked", "unsubscribed", "dead"})


def _deterministic_job_id(engagement_id: str, prospect_id: str, kind: str, step: int) -> str:
    """Deterministic job ID so re-running plan() is idempotent per step."""
    h = hashlib.sha1(f"{engagement_id}|{prospect_id}|{kind}|{step}".encode()).hexdigest()[:16]
    return f"job_{h}"


class OutboundAgentV1:
    """Multi-step outbound sequence scheduler."""

    runner_kind = "outbound.v1"
    DEFAULT_HITL_THRESHOLD = 50

    def __init__(
        self,
        *,
        gemini: Optional[GeminiClient] = None,
        ledger: Optional[CostLedger] = None,
    ) -> None:
        self._gemini = gemini
        self._ledger = ledger

    # ── sequence config ──────────────────────────────────────────────────

    def _resolve_sequence(self, agent: Agent) -> list[dict]:
        """
        Return the list of sequence steps. Falls back to a single step built
        from the legacy subject_template / body_template config keys.
        """
        seq = agent.config.get("sequence")
        if isinstance(seq, list) and seq:
            return seq
        # Legacy single-step fallback.
        return [{
            "subject_template": agent.config.get("subject_template", "Quick question for {first_name}"),
            "body_template": agent.config.get(
                "body_template",
                "Hi {first_name},\n\n{offer}\n\nWorth a 15-minute chat?\n\n— Sent via AutoReach",
            ),
        }]

    # ── planning ─────────────────────────────────────────────────────────

    def plan(self, agent: Agent, *, context: AgentContext) -> Iterable[Job]:
        engagement = context.get_engagement(agent.engagement_id)
        if engagement is None or engagement.status != "active":
            return []

        sequence = self._resolve_sequence(agent)
        threshold = int(agent.config.get("hitl_threshold", self.DEFAULT_HITL_THRESHOLD))
        gap_seconds = int(agent.config.get("send_gap_seconds", 90))
        batch = int(agent.config.get("plan_batch_size", 10))
        personalize_enabled = bool(agent.config.get("personalize", True)) and self._gemini is not None

        # HITL trust ramp counts total sends across the engagement.
        all_events = list(context.list_recent_events(engagement.id, limit=5000))
        sent_so_far = sum(1 for ev in all_events if ev.kind.value == "email.sent")
        requires_approval = sent_so_far < threshold

        # Build a per-prospect view of their sent history from the event log.
        # prospect_id -> (sent_count, last_sent_at)
        sent_history: dict[str, tuple[int, datetime]] = {}
        for ev in all_events:
            if ev.kind.value == "email.sent" and ev.prospect_id:
                count, last = sent_history.get(ev.prospect_id, (0, None))
                new_last = ev.occurred_at if (last is None or (ev.occurred_at and ev.occurred_at > last)) else last
                sent_history[ev.prospect_id] = (count + 1, new_last)

        now = datetime.now(timezone.utc)
        jobs: list[Job] = []
        scheduled_count = 0

        # Consider both brand-new prospects and those mid-sequence (contacted).
        candidates: list = []
        candidates.extend(context.list_prospects(engagement.id, status="new", limit=batch))
        candidates.extend(context.list_prospects(engagement.id, status="contacted", limit=batch))

        seen_ids = set()
        for prospect in candidates:
            if prospect.id in seen_ids:
                continue
            seen_ids.add(prospect.id)
            if not prospect.email:
                continue
            if prospect.status in _TERMINAL_PROSPECT_STATUSES:
                continue
            if scheduled_count >= batch:
                break

            sent_count, last_sent_at = sent_history.get(prospect.id, (0, None))
            next_step_index = sent_count  # 0-based index into `sequence`

            # Whole sequence done for this prospect.
            if next_step_index >= len(sequence):
                continue

            step_cfg = sequence[next_step_index]
            step_number = next_step_index + 1  # 1-based for job id + payload

            # Delay gate for follow-ups (step 1 sends immediately).
            if next_step_index > 0:
                wait_days = int(step_cfg.get("wait_days", 3))
                if last_sent_at is not None:
                    ready_at = last_sent_at + timedelta(days=wait_days)
                    if now < ready_at:
                        continue  # not time for the next step yet

            scheduled = now + timedelta(seconds=gap_seconds * scheduled_count)
            scheduled_count += 1

            subject_template = step_cfg.get("subject_template", "Quick question for {first_name}")
            body_template = step_cfg.get("body_template", "Hi {first_name},\n\n{offer}")
            # Feature #5: per-step HTML body (supports personalized image variables,
            # e.g. <img src="https://img.co/{first_name}.png">). Rendered by the adapter.
            body_html = step_cfg.get("body_html")

            payload: dict = {
                "to_email": prospect.email,
                "to_name": prospect.full_name or "",
                "company": prospect.company or "",
                "title": prospect.title or "",
                "step": step_number,
                "offer": engagement.offer,
                "subject_template": subject_template,
                "body_template": body_template,
            }
            if body_html:
                # Substitute {first_name} from full_name for image-variable URLs.
                first_name = (prospect.full_name or "").split()[0] if prospect.full_name else ""
                payload["body_html"] = (
                    body_html
                    .replace("{first_name}", first_name)
                    .replace("{company}", prospect.company or "")
                    .replace("{offer}", engagement.offer or "")
                )

            if personalize_enabled:
                prospect_fields = {
                    "full_name": prospect.full_name or "",
                    "title": prospect.title or "",
                    "company": prospect.company or "",
                    "raw": dict(prospect.raw or {}),
                }
                base_subject = subject_template.replace("{offer}", engagement.offer or "")
                base_body = body_template.replace("{offer}", engagement.offer or "")
                pres = personalize_outbound(
                    subject_template=base_subject,
                    body_template=base_body,
                    prospect_fields=prospect_fields,
                    client=self._gemini,
                )
                payload["subject"] = pres.subject
                payload["body_text"] = pres.body_text
                payload["personalized"] = not pres.fallback_used
                payload["personalization_used_fields"] = list(pres.used_fields)
                if pres.fallback_used:
                    payload["personalization_error"] = pres.error or "fallback used"
                if pres.estimated_cost_cents > 0 and self._ledger is not None:
                    self._ledger.debit(
                        CostEntry(
                            id=f"cost_pers_{_deterministic_job_id(engagement.id, prospect.id, 'email.send', step_number)}",
                            engagement_id=engagement.id,
                            job_id=_deterministic_job_id(engagement.id, prospect.id, "email.send", step_number),
                            category="llm",
                            amount_cents=pres.estimated_cost_cents,
                            metadata={"purpose": "outbound_personalize", "step": step_number},
                        )
                    )

            jobs.append(
                Job(
                    id=_deterministic_job_id(engagement.id, prospect.id, "email.send", step_number),
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
