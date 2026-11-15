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
For each prospect we count their `email.sent` + `linkedin.sent` events:
    sent_count == 0  → send step 1 (first touch)
    sent_count >= 1  → if a next step exists AND the per-step delay has
                       elapsed since the last send → send it
A prospect whose status is replied / booked / unsubscribed is skipped — their
sequence is over. LinkedIn steps require a Voyager seat + `linkedin_url`;
email steps require an email address.

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
from engine.services.ai_email_critic import build_ai_critic
from engine.services.deliverability_guardian import DeliverabilityGuardian

logger = logging.getLogger(__name__)

# A prospect in any of these statuses has finished its sequence.
_TERMINAL_PROSPECT_STATUSES = frozenset({"replied", "booked", "unsubscribed", "dead"})

_LINKEDIN_STEP_TYPES = frozenset({
    "visitprofile",
    "likeposts",
    "comment",
    "commentonpost",
    "linkedincomment",
    "invitation",
    "invitationnote",
    "connectionnote",
    "connectionrequest",
    "message",
    "voicemessage",
    "voicenote",
    "linkedin",
    "linkedinvisit",
    "linkedinlike",
    "linkedinconnect",
    "linkedindm",
    "linkedinmessage",
    "linkedinvoicenote",
    # legacy underscored forms (normalized by step_is_linkedin)
    "linkedin_visit",
    "linkedin_like",
    "linkedin_connect",
    "linkedin_dm",
    "connection_request",
})


def _step_kind(step: dict) -> str:
    return str(step.get("type") or step.get("kind") or step.get("channel") or "").strip()


def step_is_linkedin(step: dict) -> bool:
    kind = _step_kind(step).lower().replace("-", "").replace("_", "")
    channel = str(step.get("channel") or "").strip().lower()
    if channel == "email" or kind == "email":
        return False
    # Accept Gojiberry wizard kinds (VISIT_PROFILE, LINKEDIN_CONNECT, …) and channel tags.
    return channel == "linkedin" or kind in _LINKEDIN_STEP_TYPES or kind.startswith("linkedin")


def effective_sequence(
    sequence: list[dict],
    *,
    has_linkedin_seat: bool,
) -> tuple[list[dict], list[str]]:
    """Collapse LinkedIn-first sequences to email when no Voyager seat exists.

    Observation (Gojiberry ``skipInvitationAfterDays``): pending LinkedIn steps
    are skipped and only email steps run. Inference: with no seat connected,
    skip immediately instead of a silent no-op.
    """
    notes: list[str] = []
    seq = [dict(s) for s in sequence if isinstance(s, dict)]
    if not seq:
        return seq, notes
    if has_linkedin_seat:
        return seq, notes
    had_linkedin = any(step_is_linkedin(s) for s in seq)
    email_steps = [s for s in seq if not step_is_linkedin(s)]
    if had_linkedin:
        notes.append("skipped_linkedin_no_seat")
    if not email_steps:
        notes.append("synthesized_email_fallback")
        return [{"type": "email", "channel": "email", "wait_days": 0}], notes
    first = dict(email_steps[0])
    first["wait_days"] = 0
    first["delay_days"] = 0
    first["type"] = first.get("type") or first.get("kind") or "email"
    first["channel"] = "email"
    rest = []
    for item in email_steps[1:]:
        nxt = dict(item)
        nxt["channel"] = nxt.get("channel") or "email"
        rest.append(nxt)
    return [first, *rest], notes


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

        raw_sequence = self._resolve_sequence(agent)
        tenant_id = None
        store = getattr(context, "_store", None)
        if store is not None and hasattr(store, "get_engagement_tenant_id"):
            tenant_id = store.get_engagement_tenant_id(engagement.id)
        has_li_seat = False
        if tenant_id:
            from engine.dispatch.linkedin import tenant_has_linkedin_seat

            has_li_seat = tenant_has_linkedin_seat(store, tenant_id)
        sequence, seq_notes = effective_sequence(raw_sequence, has_linkedin_seat=has_li_seat)
        if seq_notes:
            logger.info(
                "full-cycle sequence fallback engagement=%s notes=%s",
                engagement.id,
                ",".join(seq_notes),
            )
        default_subject = agent.config.get("subject_template", "Quick question for {first_name}")
        default_body = agent.config.get(
            "body_template",
            "Hi {first_name},\n\n{offer}\n\nWorth a 15-minute chat?\n\n— Sent via AutoReach",
        )
        for step in sequence:
            step.setdefault("subject_template", default_subject)
            step.setdefault("body_template", default_body)
        threshold = int(agent.config.get("hitl_threshold", self.DEFAULT_HITL_THRESHOLD))
        gap_seconds = int(agent.config.get("send_gap_seconds", 90))
        batch = int(agent.config.get("plan_batch_size", 10))
        message_mode = str(agent.config.get("message_mode") or "ai").strip().lower()
        personalize_enabled = (
            message_mode not in {"template", "structured"}
            and bool(agent.config.get("personalize", True))
            and self._gemini is not None
        )

        # HITL trust ramp counts total sends across the engagement.
        _PROGRESS_KINDS = frozenset({"email.sent", "linkedin.sent"})
        all_events = list(context.list_recent_events(engagement.id, limit=5000))
        sent_so_far = sum(1 for ev in all_events if ev.kind.value in _PROGRESS_KINDS)
        requires_approval = sent_so_far < threshold

        # Build a per-prospect view of their sent history from the event log.
        # prospect_id -> (sent_count, last_sent_at)
        sent_history: dict[str, tuple[int, datetime]] = {}
        for ev in all_events:
            if ev.kind.value in _PROGRESS_KINDS and ev.prospect_id:
                count, last = sent_history.get(ev.prospect_id, (0, None))
                new_last = ev.occurred_at if (last is None or (ev.occurred_at and ev.occurred_at > last)) else last
                sent_history[ev.prospect_id] = (count + 1, new_last)

        now = datetime.now(timezone.utc)
        # LLM critic activates only when OPENAI_API_KEY is set (else deterministic-only).
        guardian = DeliverabilityGuardian(llm_critic=build_ai_critic())
        jobs: list[Job] = []
        scheduled_count = 0

        # Consider both brand-new prospects and those mid-sequence (contacted).
        candidates: list = []
        candidates.extend(context.list_prospects(engagement.id, status="new", limit=batch))
        candidates.extend(context.list_prospects(engagement.id, status="contacted", limit=batch))

        from engine.signals.prioritization import sort_prospects_by_priority

        icp_text = engagement.icp_description or ""
        icp_keywords = [w.strip().lower() for w in icp_text.split() if len(w.strip()) > 3][:12]
        candidates = sort_prospects_by_priority(candidates, icp_keywords=icp_keywords or None)

        seen_ids = set()
        for prospect in candidates:
            if prospect.id in seen_ids:
                continue
            seen_ids.add(prospect.id)
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
            is_li_step = step_is_linkedin(step_cfg)
            raw_fields = dict(prospect.raw or {})
            linkedin_url = str(
                raw_fields.get("linkedin_url")
                or raw_fields.get("profile_url")
                or getattr(prospect, "linkedin_url", "")
                or ""
            ).strip()

            # Channel eligibility — don't hard-require email for LinkedIn steps.
            if is_li_step:
                if not has_li_seat or not linkedin_url:
                    continue
            elif not prospect.email:
                continue

            # Delay gate for follow-ups (step 1 sends immediately).
            if next_step_index > 0:
                wait_days = int(step_cfg.get("wait_days") or step_cfg.get("delay_days") or 3)
                if last_sent_at is not None:
                    ready_at = last_sent_at + timedelta(days=wait_days)
                    if now < ready_at:
                        continue  # not time for the next step yet

            scheduled = now + timedelta(seconds=gap_seconds * scheduled_count)
            scheduled_count += 1

            subject_template = step_cfg.get("subject_template", "Quick question for {first_name}")
            body_template = step_cfg.get(
                "body_template",
                step_cfg.get("note") or "Hi {first_name},\n\n{offer}",
            )
            # Feature #5: per-step HTML body (supports personalized image variables,
            # e.g. <img src="https://img.co/{first_name}.png">). Rendered by the adapter.
            body_html = step_cfg.get("body_html")
            from engine.adapters.email_merge import (
                copy_quality_error,
                first_name_from_payload,
                merge_email_copy,
            )
            from engine.dispatch.linkedin_adapter import normalize_voyager_step_type

            first_name = first_name_from_payload({
                "first_name": raw_fields.get("first_name"),
                "full_name": prospect.full_name or "",
                "to_name": prospect.full_name or "",
                "raw": raw_fields,
            })
            step_kind = _step_kind(step_cfg) or ("linkedin" if is_li_step else "email")
            channel = "linkedin" if is_li_step else "email"
            payload: dict = {
                "to_email": prospect.email or "",
                "to": prospect.email or "",
                "to_name": prospect.full_name or "",
                "first_name": first_name,
                "full_name": prospect.full_name or "",
                "company": prospect.company or "",
                "title": prospect.title or "",
                "step": step_number,
                "offer": engagement.offer,
                "subject_template": subject_template,
                "body_template": body_template,
                "channel": channel,
                "step_type": normalize_voyager_step_type(step_kind) if is_li_step else (step_kind or "email"),
                "linkedin_url": linkedin_url,
                "tenant_id": tenant_id,
                # Score display must not skip leftover-token / generic copy checks.
                "score_gate": False,
                "sequence_notes": list(seq_notes),
                "raw": raw_fields,
                "message_mode": message_mode,
                "splitLinkedinMessagesIntoConversation": bool(
                    agent.config.get("split_linkedin_messages")
                    or step_cfg.get("splitLinkedinMessagesIntoConversation")
                ),
            }
            if body_html:
                payload["body_html"] = body_html

            # Signal-stack evidence → ground BOTH the draft (so the AI references
            # the real trigger) and the Guardian's grounding check.
            _research = prospect.research if isinstance(prospect.research, dict) else {}
            _stack = _research.get("signal_stack") if isinstance(_research, dict) else {}
            _evidence_summaries: list[str] = []
            _grounding_terms: list[str] = []
            if isinstance(_stack, dict):
                for _e in _stack.get("evidence", []):
                    if not isinstance(_e, dict):
                        continue
                    _summary = str(_e.get("summary", "")).strip()
                    if _summary:
                        _evidence_summaries.append(_summary)
                    for _tok in str(_e.get("signal_type", "")).replace("_", " ").split():
                        if len(_tok) > 2:
                            _grounding_terms.append(_tok)
                    _dom = str(_e.get("company_domain", "")).split(".")[0]
                    if _dom:
                        _grounding_terms.append(_dom)
            _research_str = "; ".join(_evidence_summaries)
            icp_fact = ""
            if _evidence_summaries:
                icp_fact = _evidence_summaries[0][:180]
            elif (engagement.icp_description or "").strip():
                icp_fact = (engagement.icp_description or "").strip().split(".")[0][:180]
            payload["icp_fact"] = icp_fact

            if personalize_enabled:
                prospect_fields = {
                    "full_name": prospect.full_name or "",
                    "first_name": first_name,
                    "title": prospect.title or "",
                    "company": prospect.company or "",
                    "icp_fact": icp_fact,
                    "raw": raw_fields,
                }
                base_subject = subject_template.replace("{offer}", engagement.offer or "")
                base_body = body_template.replace("{offer}", engagement.offer or "")
                pres = personalize_outbound(
                    offer=engagement.offer or "",
                    subject_template=base_subject,
                    body_template=base_body,
                    research=_research_str or icp_fact,
                    prospect_fields=prospect_fields,
                    client=self._gemini,
                )
                payload["subject"] = pres.subject
                payload["body_text"] = pres.body_text
                payload["personalized"] = not pres.fallback_used
                payload["fallback_used"] = pres.fallback_used
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
                            metadata={
                                "purpose": "outbound_personalize",
                                "step": step_number,
                                "cost_basis": pres.cost_basis,
                                "cost_micro_usd": pres.cost_micro_usd,
                                "prompt_tokens": pres.prompt_tokens,
                                "output_tokens": pres.output_tokens,
                            },
                        )
                    )

            rendered_subject, rendered_body, rendered_html = merge_email_copy(payload)
            payload["subject"] = rendered_subject
            payload["body_text"] = rendered_body
            if rendered_html:
                payload["body_html"] = rendered_html

            job_requires_approval = requires_approval
            if not is_li_step:
                quality_error = copy_quality_error(payload)
                if quality_error:
                    payload["copy_quality_error"] = quality_error
                # Deliverability Guardian for email only — LinkedIn copy is short/social.
                risk = guardian.score(
                    subject=rendered_subject,
                    body=rendered_body,
                    grounded_evidence=_grounding_terms or ([icp_fact] if icp_fact else None),
                    fallback_used=bool(payload.get("fallback_used")),
                )
                payload["deliverability_risk"] = risk.as_dict()
                job_requires_approval = (
                    requires_approval or not risk.is_send_safe or bool(quality_error)
                )

            job_kind = JobKind.LINKEDIN_ACTION if is_li_step else JobKind.EMAIL_SEND
            kind_key = "linkedin.action" if is_li_step else "email.send"
            jobs.append(
                Job(
                    id=_deterministic_job_id(engagement.id, prospect.id, kind_key, step_number),
                    engagement_id=engagement.id,
                    agent_id=agent.id,
                    kind=job_kind,
                    payload=payload,
                    prospect_id=prospect.id,
                    requires_approval=job_requires_approval,
                    scheduled_for=scheduled,
                )
            )
        return jobs
