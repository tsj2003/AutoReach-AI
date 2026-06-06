"""
Core domain types for the AutoReach engine.

These dataclasses are the platform's vocabulary. They're deliberately
product-agnostic: the same Engagement + Agent + Job + Event + CostEntry
model serves outbound today and any other agent workload tomorrow.

Design notes
------------
* IDs are strings, not ints. Easier to migrate to UUIDs / external systems.
* Timestamps are timezone-aware UTC (`datetime` with `tzinfo=timezone.utc`).
  Naive datetimes are a recurring source of bugs we will not pay twice for.
* Payloads are typed JSON-serializable dicts. We pay a small ergonomics cost
  here in exchange for a clean event log + future replay/debug.
* Models are frozen where possible. State changes go through the store, not
  by mutating objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional

JsonDict = Mapping[str, Any]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Engagement: a long-running customer commitment
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Engagement:
    """
    A customer commitment the platform serves.

    For OaaS, an Engagement is "we run outbound for customer X, with offer Y,
    targeting ICP Z, booking into calendar C, aiming for N qualified meetings
    per month at price P each."

    For the future platform, an Engagement is whatever a developer defines:
    "run this support agent for this end-customer with this budget."
    """

    id: str
    customer_name: str
    # The offer being sold to prospects. Plain text; agents render it.
    offer: str
    # ICP definition: free-text + structured criteria the Agent uses for
    # qualification and personalization.
    icp_description: str
    icp_filters: JsonDict = field(default_factory=dict)
    # Where booked meetings land (e.g., a Cal.com link).
    booking_url: Optional[str] = None
    # Goal & pricing for OaaS-style outcome billing. None for non-OaaS uses.
    monthly_meeting_target: Optional[int] = None
    price_per_outcome_cents: Optional[int] = None
    # Hard budget guardrails for cost ledger enforcement.
    monthly_budget_cents: Optional[int] = None
    # Operational status.
    status: str = "active"  # active | paused | completed | cancelled
    created_at: datetime = field(default_factory=_utcnow)
    metadata: JsonDict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Prospect: a target the agent acts upon (within an Engagement)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Prospect:
    """
    An individual target within an Engagement.

    For outbound, this is a person we email. For other agent workloads, it
    might be a ticket, account, or entity the agent is processing.
    """

    id: str
    engagement_id: str
    email: Optional[str]
    full_name: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    # Free-form attributes from the source list (LinkedIn, Apollo, scraped CSV).
    raw: JsonDict = field(default_factory=dict)
    # Per-prospect personalization context the agent has researched.
    research: JsonDict = field(default_factory=dict)
    # Pipeline status, distinct from any individual Job's state.
    status: str = "new"  # new | contacted | replied | booked | unsubscribed | dead
    created_at: datetime = field(default_factory=_utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Agent: the autonomous worker assigned to an Engagement
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Agent:
    """
    An autonomous worker bound to an Engagement.

    The Agent decides what Jobs to dispatch and when, based on the Engagement's
    goal and the current state of its prospects. The Agent is identified by
    `runner_kind` (which AgentRunner implementation runs it) and configured
    with `config` (runner-specific dict).

    Agents are *not* the executors. They plan and dispatch. Adapters execute.
    """

    id: str
    engagement_id: str
    runner_kind: str  # e.g., "outbound.v1", "support.v1"
    config: JsonDict = field(default_factory=dict)
    status: str = "active"  # active | paused | retired
    created_at: datetime = field(default_factory=_utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Job: a discrete unit of work
# ─────────────────────────────────────────────────────────────────────────────


class JobKind(str, Enum):
    """
    Closed-set of action kinds the engine knows about.

    New kinds are added explicitly so the state machine, observability, and
    cost ledger all stay in sync. Adapters may register sub-types via
    `payload['action']`.
    """

    EMAIL_SEND = "email.send"
    EMAIL_REPLY_DRAFT = "email.reply_draft"
    EMAIL_REPLY_SEND = "email.reply_send"
    EMAIL_REPLY_DETECT = "email.reply_detect"
    CALENDAR_INVITE = "calendar.invite"
    HITL_REVIEW = "hitl.review"
    RESEARCH_PROSPECT = "research.prospect"

@dataclass
class Job:
    """
    A discrete unit of work the engine executes.

    Jobs are the atomic schedulable item. They have explicit lifecycle states
    (see `engine.core.state.JobState`), can be retried, can require HITL
    approval, and can be cost-attributed.

    Job is the only mutable core type. It changes state during execution.
    All state changes must go through the state machine; never set `state`
    directly outside of `engine.core.state`.
    """

    id: str
    engagement_id: str
    agent_id: str
    kind: JobKind
    payload: JsonDict
    state: str = "pending"  # see JobState
    prospect_id: Optional[str] = None
    parent_job_id: Optional[str] = None  # for jobs spawned by other jobs
    # HITL: if True, job blocks at `awaiting_approval` until approved.
    requires_approval: bool = False
    # Scheduling.
    scheduled_for: datetime = field(default_factory=_utcnow)
    not_before: Optional[datetime] = None  # rate-limit / sending-window enforcement
    # Retries.
    attempt: int = 0
    max_attempts: int = 3
    last_error: Optional[str] = None
    # Result.
    result: JsonDict = field(default_factory=dict)
    # Audit timestamps.
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Event: the immutable audit log
# ─────────────────────────────────────────────────────────────────────────────


class EventKind(str, Enum):
    """All events the engine can emit. The audit log + later analytics."""

    # Engagement lifecycle
    ENGAGEMENT_CREATED = "engagement.created"
    ENGAGEMENT_PAUSED = "engagement.paused"
    ENGAGEMENT_RESUMED = "engagement.resumed"
    # Agent lifecycle
    AGENT_CREATED = "agent.created"
    AGENT_DECIDED = "agent.decided"
    # Job lifecycle
    JOB_CREATED = "job.created"
    JOB_STARTED = "job.started"
    JOB_AWAITING_APPROVAL = "job.awaiting_approval"
    JOB_APPROVED = "job.approved"
    JOB_REJECTED = "job.rejected"
    JOB_SUCCEEDED = "job.succeeded"
    JOB_FAILED = "job.failed"
    JOB_RETRY_SCHEDULED = "job.retry_scheduled"
    JOB_DEAD_LETTERED = "job.dead_lettered"
    # Adapter-emitted
    EMAIL_SENT = "email.sent"
    EMAIL_DRY_RUN = "email.dry_run"
    EMAIL_RATE_LIMITED = "email.rate_limited"
    EMAIL_BOUNCED = "email.bounced"
    EMAIL_REPLY_RECEIVED = "email.reply_received"
    REPLY_CLASSIFIED = "reply.classified"
    REPLY_DRAFT_APPROVED = "reply.draft_approved"
    REPLY_SENT = "reply.sent"
    GMAIL_TOKEN_INVALID = "gmail.token_invalid"
    MEETING_BOOKED = "meeting.booked"
    MEETING_QUALIFIED = "meeting.qualified"
    MEETING_NO_SHOW = "meeting.no_show"
    MEETING_CANCELLED = "meeting.cancelled"
    # Cost / policy
    COST_DEBITED = "cost.debited"
    BUDGET_EXCEEDED = "budget.exceeded"
    POLICY_VIOLATION = "policy.violation"


@dataclass(frozen=True)
class Event:
    """
    An immutable record of something that happened. Append-only.

    Events are the foundation of:
        - debugging ("what did the agent do at 3am?")
        - replay ("rebuild this Engagement's state from the event log")
        - billing ("how many MEETING_BOOKED events for customer X this month?")
        - analytics ("reply rate by ICP segment")

    Never mutate. Never delete. If something is wrong, append a corrective event.
    """

    id: str
    kind: EventKind
    engagement_id: Optional[str]
    agent_id: Optional[str] = None
    job_id: Optional[str] = None
    prospect_id: Optional[str] = None
    payload: JsonDict = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=_utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Cost: per-engagement spend tracking
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CostEntry:
    """
    A single cost line item attributed to an Engagement.

    Categories are intentionally coarse so the ledger stays readable.
    Sub-types live in `metadata` (e.g., model name, token counts).
    """

    id: str
    engagement_id: str
    job_id: Optional[str]
    category: str  # llm | email_send | enrichment | compute | other
    amount_cents: int  # always integer cents to avoid float drift
    metadata: JsonDict = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=_utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Reply: an inbound message from a prospect (after we've reached out)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Reply:
    """
    A captured inbound reply. The cockpit's triage queue is built on these.

    `classification` follows the existing AutoReach taxonomy:
        interested | objection | unsubscribe | auto

    `suggested_reply` is what the LLM drafted; the operator approves/edits/sends.
    """

    id: str
    engagement_id: str
    prospect_id: str
    job_id: Optional[str]  # the original send-job this is a reply to
    snippet: str
    classification: str = "objection"
    suggested_reply: str = ""
    status: str = "pending"  # pending | approved | sent | discarded
    received_at: datetime = field(default_factory=_utcnow)
    # External id (e.g., Gmail message id) so we don't double-ingest.
    external_message_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Meeting: the outcome OaaS bills against
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Meeting:
    """
    A meeting booked through the engine.

    Revenue recognition rule (OaaS): a meeting becomes `qualified` when the
    operator confirms the prospect actually showed up and was a real fit.
    Only `qualified` meetings count toward billing.

    Status lifecycle:
        booked → qualified → (terminal)
        booked → no_show   → (terminal)
        booked → cancelled → (terminal)
    """

    id: str
    engagement_id: str
    prospect_id: str
    reply_id: Optional[str]
    scheduled_for: datetime
    status: str = "booked"  # booked | qualified | no_show | cancelled
    booked_at: datetime = field(default_factory=_utcnow)
    notes: str = ""
