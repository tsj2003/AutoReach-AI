"""
Protocols (interfaces) the engine exposes to plug-in implementations.

These are the platform contract. Anything in `engine.adapters/`,
`engine.agents/`, `engine.storage/` must conform to one of these.

We use `typing.Protocol` instead of ABCs so:
    * concrete classes don't need to inherit (less coupling)
    * mocks/fakes for tests are trivial
    * future external SDK consumers can implement without depending on us

These are deliberately the *narrowest* interfaces that work. Resist the urge
to add convenience methods here — they belong on concrete classes or helpers.
"""

from __future__ import annotations

from typing import Iterable, Optional, Protocol, runtime_checkable

from engine.core.types import (
    Agent,
    CostEntry,
    Engagement,
    Event,
    Job,
    Meeting,
    Prospect,
    Reply,
)
from engine.auth.mailbox_models import Mailbox


# ─────────────────────────────────────────────────────────────────────────────
# Adapter: a channel-specific executor (Email/Gmail, Calendar, LinkedIn, ...)
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class Adapter(Protocol):
    """
    Executes a Job by talking to an external system.

    Adapters are stateless from the engine's perspective. They take a Job
    and return a result; any external state (OAuth tokens, rate-limit
    counters) is held inside the adapter implementation.

    An Adapter declares which JobKinds it handles via `handles`.
    """

    name: str  # stable identifier, e.g., "email.gmail"

    def handles(self, job: Job) -> bool:
        """Return True iff this adapter can execute `job`."""

    def execute(self, job: Job, *, context: "AdapterContext") -> "AdapterResult":
        """
        Execute the job. Must not mutate the Job directly; return an
        AdapterResult and let the engine do the state transition.

        Implementations should be idempotent where possible — the engine may
        retry on transient errors.
        """


class AdapterContext(Protocol):
    """
    A read-only view into the engine that adapters can consult.

    Keeps adapters decoupled from the storage layer while letting them
    fetch related Engagement / Prospect data they need to execute.
    """

    def get_engagement(self, engagement_id: str) -> Optional[Engagement]: ...
    def get_prospect(self, prospect_id: str) -> Optional[Prospect]: ...
    def emit(self, event: Event) -> None: ...
    def debit(self, cost: CostEntry) -> None: ...


class AdapterResult(Protocol):
    """Result of an Adapter.execute() call."""

    succeeded: bool
    # Free-form, JSON-serializable. Stored on the Job's `result` field.
    output: dict
    # If failed: human-readable error.
    error: Optional[str]
    # If failed but transient (retryable): True. Engine schedules a retry.
    retryable: bool


# ─────────────────────────────────────────────────────────────────────────────
# AgentRunner: drives an Engagement by deciding what Jobs to dispatch
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class AgentRunner(Protocol):
    """
    Plans and dispatches Jobs for an Engagement.

    A runner decides:
        * which prospects to act on next
        * what kind of Job (first-touch email, follow-up, reply draft, etc.)
        * with what payload (subject, body, scheduling)

    The runner does NOT execute Jobs — that's the Adapter's job.
    """

    runner_kind: str  # matches Agent.runner_kind, e.g., "outbound.v1"

    def plan(self, agent: Agent, *, context: "AgentContext") -> Iterable[Job]:
        """
        Decide which new Jobs to create on this tick.

        Returns an iterable of Jobs the runner wants to enqueue. The engine
        will persist them and schedule them via the state machine.

        Should be idempotent within a tick — calling twice for the same
        agent state must not produce duplicate Jobs (use deterministic IDs
        derived from `engagement_id + prospect_id + job_kind`).
        """


class AgentContext(Protocol):
    """A read-only view the AgentRunner uses while planning."""

    def get_engagement(self, engagement_id: str) -> Optional[Engagement]: ...
    def list_prospects(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Prospect]: ...
    def list_recent_events(
        self,
        engagement_id: str,
        *,
        limit: int = 50,
    ) -> Iterable[Event]: ...


# ─────────────────────────────────────────────────────────────────────────────
# Store: persistence
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class Store(Protocol):
    """
    Persistence for Engagements, Agents, Jobs, Prospects.

    Phase 1 implementation: SQLite via SQLAlchemy. Phase 5: shared Postgres.
    The Protocol means we can swap without touching consumers.
    """

    # Engagements
    def save_engagement(self, engagement: Engagement, *, tenant_id: Optional[str] = None) -> None: ...
    def get_engagement(self, engagement_id: str, *, tenant_id: Optional[str] = None) -> Optional[Engagement]: ...
    def get_engagement_tenant_id(self, engagement_id: str) -> Optional[str]: ...
    def list_engagements(
        self,
        *,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Iterable[Engagement]: ...

    # Agents
    def save_agent(self, agent: Agent, *, tenant_id: Optional[str] = None) -> None: ...
    def get_agent(self, agent_id: str) -> Optional[Agent]: ...
    def list_agents(self, engagement_id: str) -> Iterable[Agent]: ...

    # Prospects
    def save_prospect(self, prospect: Prospect, *, tenant_id: Optional[str] = None) -> None: ...
    def get_prospect(self, prospect_id: str) -> Optional[Prospect]: ...
    def list_prospects(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Prospect]: ...

    # Jobs
    def save_job(self, job: Job) -> None: ...
    def get_job(self, job_id: str) -> Optional[Job]: ...
    def list_due_jobs(
        self,
        *,
        limit: int = 100,
        engagement_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Iterable[Job]: ...
    def list_jobs_by_state(
        self,
        state: str,
        *,
        engagement_id: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Job]: ...

    # Mailboxes
    def list_all_mailboxes(self, *, status: Optional[str] = None) -> Iterable[Mailbox]: ...

    # Replies
    def save_reply(self, reply: Reply) -> None: ...
    def get_reply(self, reply_id: str) -> Optional[Reply]: ...
    def list_replies(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Reply]: ...
    def get_reply_by_external_id(self, external_message_id: str) -> Optional[Reply]: ...

    # Meetings
    def save_meeting(self, meeting: Meeting) -> None: ...
    def get_meeting(self, meeting_id: str) -> Optional[Meeting]: ...
    def list_meetings(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Meeting]: ...


# ─────────────────────────────────────────────────────────────────────────────
# EventSink: where events go
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class EventSink(Protocol):
    """
    Append-only sink for Events.

    Phase 1: same SQLite/Postgres database as the Store, in an `events` table.
    Phase 5+: optionally fan out to ClickHouse/Kafka for analytics. The
    Protocol lets us add sinks without changing emitters.
    """

    def emit(self, event: Event) -> None: ...

    def list_recent(
        self,
        *,
        engagement_id: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Event]: ...


# ─────────────────────────────────────────────────────────────────────────────
# CostLedger: per-engagement spend tracking and budget enforcement
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class CostLedger(Protocol):
    """
    Tracks per-Engagement spend. The platform's margin enforcement.

    The ledger is the single answer to: "is this Engagement still profitable?"
    Adapters debit it on every paid action; agents consult it before
    dispatching expensive Jobs.
    """

    def debit(self, entry: CostEntry) -> None: ...

    def total_spent_cents(
        self,
        engagement_id: str,
        *,
        category: Optional[str] = None,
    ) -> int: ...

    def remaining_budget_cents(self, engagement_id: str) -> Optional[int]:
        """
        Returns the remaining monthly budget for the Engagement, or None
        if the Engagement has no budget set.

        A return value of 0 means the budget is exhausted; consumers should
        block further paid Jobs until next billing cycle or budget extension.
        """
        ...

    def list_recent(
        self,
        engagement_id: str,
        *,
        limit: int = 100,
    ) -> Iterable[CostEntry]: ...
