"""
EngineRuntime: the main orchestrator.

Responsibilities
----------------
1. **Plan**: ask each active Agent for new Jobs; persist them.
2. **Dispatch**: pick due Jobs, transition them through the state machine,
   and hand off to the matching Adapter.
3. **Execute**: call Adapter.execute(); apply success / failure semantics.
4. **Retry**: on retryable failures, schedule another attempt with backoff.
5. **Record**: emit Events at every meaningful boundary.

This is intentionally a pull-based loop, not an event-driven framework.
A pull loop is trivially restartable: kill the process mid-run, restart,
and the runtime resumes from whatever state the DB has. That's the
single most important property for a system that runs unattended.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from engine.core.protocols import (
    AgentRunner,
    CostLedger,
    EventSink,
    Store,
)
from engine.core.state import IllegalTransition, JobState, JobStateMachine
from engine.core.types import Agent, Event, EventKind, Job, JobKind
from engine.runtime.contexts import DefaultAdapterContext, DefaultAgentContext
from engine.runtime.registry import AdapterRegistry
from engine.runtime.results import AdapterResultData

logger = logging.getLogger(__name__)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EngineRuntime:
    """
    The orchestrator. Wire it up once with stores + adapters + agent runners,
    then call `tick()` (or `run_once()`) repeatedly.

    `tick()` is one cycle: plan + dispatch one batch.
    `run_once()` runs `tick()` until no due jobs remain (single-shot drain).
    """

    def __init__(
        self,
        *,
        store: Store,
        events: EventSink,
        ledger: CostLedger,
        adapters: AdapterRegistry,
        agent_runners: dict[str, AgentRunner],
    ) -> None:
        self._store = store
        self._events = events
        self._ledger = ledger
        self._adapters = adapters
        # Map of runner_kind -> AgentRunner instance
        self._agent_runners = agent_runners

    # ───────────────────── Public API ─────────────────────

    def plan_for_agent(self, agent: Agent) -> int:
        """Ask the runner to plan; persist any new jobs. Returns count."""
        runner = self._agent_runners.get(agent.runner_kind)
        if runner is None:
            logger.warning(
                "no runner registered for kind=%s; agent=%s skipped",
                agent.runner_kind,
                agent.id,
            )
            return 0

        ctx = DefaultAgentContext(self._store, self._events)
        proposed = list(runner.plan(agent, context=ctx))
        new_count = 0
        for job in proposed:
            existing = self._store.get_job(job.id)
            if existing is not None:
                # Idempotent planning — runner returned a deterministic ID
                # that already exists. Skip.
                continue
            self._store.save_job(job)
            self._emit(
                EventKind.JOB_CREATED,
                engagement_id=job.engagement_id,
                agent_id=job.agent_id,
                job_id=job.id,
                prospect_id=job.prospect_id,
                payload={"kind": job.kind.value, "requires_approval": job.requires_approval},
            )
            new_count += 1
        return new_count

    def plan_all(self) -> int:
        """Run plan() for every active agent across every active engagement."""
        total = 0
        for engagement in self._store.list_engagements(status="active"):
            for agent in self._store.list_agents(engagement.id):
                if agent.status != "active":
                    continue
                total += self.plan_for_agent(agent)
        return total

    def execute_due_jobs(self, *, limit: int = 50) -> int:
        """Pick due jobs and execute them. Returns count of jobs executed."""
        executed = 0
        for job in list(self._store.list_due_jobs(limit=limit)):
            try:
                self._execute_one(job)
            except Exception:
                logger.exception("unexpected error executing job %s", job.id)
                # Don't let a single bad job stop the loop.
                continue
            executed += 1
        return executed

    def tick(self) -> dict[str, int]:
        """One full cycle: plan + execute one batch."""
        planned = self.plan_all()
        executed = self.execute_due_jobs()
        return {"planned": planned, "executed": executed}

    def run_once(self, *, max_iters: int = 50) -> dict[str, int]:
        """
        Drain: keep ticking until no jobs are executed in a tick.
        Bounded by max_iters as a safety against infinite planning loops.
        """
        totals = {"planned": 0, "executed": 0, "iterations": 0}
        for _ in range(max_iters):
            r = self.tick()
            totals["planned"] += r["planned"]
            totals["executed"] += r["executed"]
            totals["iterations"] += 1
            if r["executed"] == 0 and r["planned"] == 0:
                break
        return totals

    def approve_job(self, job_id: str) -> bool:
        """HITL gate: move a job from awaiting_approval to approved."""
        job = self._store.get_job(job_id)
        if job is None or job.state != JobState.AWAITING_APPROVAL.value:
            return False
        job.state = JobStateMachine.transition(job.state, JobState.APPROVED).value
        self._store.save_job(job)
        self._emit(
            EventKind.JOB_APPROVED,
            engagement_id=job.engagement_id,
            agent_id=job.agent_id,
            job_id=job.id,
            prospect_id=job.prospect_id,
        )
        return True

    def reject_job(self, job_id: str, *, reason: str = "") -> bool:
        """HITL gate: terminally reject a job awaiting approval."""
        job = self._store.get_job(job_id)
        if job is None or job.state != JobState.AWAITING_APPROVAL.value:
            return False
        job.state = JobStateMachine.transition(job.state, JobState.REJECTED).value
        job.last_error = reason or "rejected by operator"
        self._store.save_job(job)
        self._emit(
            EventKind.JOB_REJECTED,
            engagement_id=job.engagement_id,
            agent_id=job.agent_id,
            job_id=job.id,
            prospect_id=job.prospect_id,
            payload={"reason": reason},
        )
        return True

    # ───────────────────── Internals ─────────────────────

    def _execute_one(self, job: Job) -> None:
        # 1. HITL gate — if the job needs approval and is still pending, park it.
        if job.requires_approval and job.state == JobState.PENDING.value:
            job.state = JobStateMachine.transition(
                job.state, JobState.AWAITING_APPROVAL
            ).value
            self._store.save_job(job)
            self._emit(
                EventKind.JOB_AWAITING_APPROVAL,
                engagement_id=job.engagement_id,
                agent_id=job.agent_id,
                job_id=job.id,
                prospect_id=job.prospect_id,
            )
            return

        # 2. Find an adapter.
        adapter = self._adapters.find(job)
        if adapter is None:
            self._fail_job(
                job,
                error=f"no adapter handles job kind={job.kind.value}",
                retryable=False,
            )
            return

        # 3. Transition to running.
        try:
            job.state = JobStateMachine.transition(job.state, JobState.RUNNING).value
        except IllegalTransition as exc:
            logger.warning("job %s in unexpected state %s: %s", job.id, job.state, exc)
            return
        job.attempt += 1
        self._store.save_job(job)
        self._emit(
            EventKind.JOB_STARTED,
            engagement_id=job.engagement_id,
            agent_id=job.agent_id,
            job_id=job.id,
            prospect_id=job.prospect_id,
            payload={"adapter": adapter.name, "attempt": job.attempt},
        )

        # 4. Execute.
        ctx = DefaultAdapterContext(self._store, self._events, self._ledger)
        try:
            result = adapter.execute(job, context=ctx)
        except Exception as exc:  # adapter blew up — treat as retryable
            logger.exception("adapter %s raised on job %s", adapter.name, job.id)
            result = AdapterResultData.fail(
                error=f"adapter exception: {exc}",
                retryable=True,
            )

        # 5. Apply result.
        if result.succeeded:
            self._succeed_job(job, output=dict(result.output))
        else:
            self._fail_job(
                job,
                error=result.error or "unknown error",
                retryable=bool(result.retryable),
                output=dict(result.output),
            )

    def _succeed_job(self, job: Job, *, output: dict) -> None:
        job.state = JobStateMachine.transition(job.state, JobState.SUCCEEDED).value
        job.result = output
        job.last_error = None
        self._store.save_job(job)
        self._emit(
            EventKind.JOB_SUCCEEDED,
            engagement_id=job.engagement_id,
            agent_id=job.agent_id,
            job_id=job.id,
            prospect_id=job.prospect_id,
            payload={"output_keys": sorted(output.keys())},
        )
        # Advance the prospect to 'contacted' after a successful email send,
        # so multi-step sequence planning treats them as mid-sequence (not new).
        # Only advance a 'new' prospect — never override replied/booked/unsubscribed.
        if job.kind == JobKind.EMAIL_SEND and job.prospect_id:
            self._advance_prospect_to_contacted(job.prospect_id)

    def _advance_prospect_to_contacted(self, prospect_id: str) -> None:
        prospect = self._store.get_prospect(prospect_id)
        if prospect is None or prospect.status != "new":
            return
        from engine.core.types import Prospect
        self._store.save_prospect(Prospect(
            id=prospect.id, engagement_id=prospect.engagement_id, email=prospect.email,
            full_name=prospect.full_name, company=prospect.company, title=prospect.title,
            raw=prospect.raw, research=prospect.research, status="contacted",
            created_at=prospect.created_at,
        ))

    def _fail_job(
        self,
        job: Job,
        *,
        error: str,
        retryable: bool,
        output: Optional[dict] = None,
    ) -> None:
        # If the job hasn't been transitioned to RUNNING yet (early failure
        # path: no adapter), we go pending → failed via a synthetic detour.
        if job.state == JobState.PENDING.value:
            # Force into running so the legal pending → running → failed path
            # holds; this also bumps the attempt counter consistently.
            job.state = JobStateMachine.transition(job.state, JobState.RUNNING).value
            job.attempt += 1

        job.state = JobStateMachine.transition(job.state, JobState.FAILED).value
        job.last_error = error
        if output is not None:
            job.result = output
        self._store.save_job(job)
        self._emit(
            EventKind.JOB_FAILED,
            engagement_id=job.engagement_id,
            agent_id=job.agent_id,
            job_id=job.id,
            prospect_id=job.prospect_id,
            payload={"error": error[:500], "retryable": retryable, "attempt": job.attempt},
        )

        if retryable and job.attempt < job.max_attempts:
            # Schedule a retry with simple exponential backoff (60s * 2^attempt).
            delay = 60 * (2 ** (job.attempt - 1))
            job.state = JobStateMachine.transition(
                job.state, JobState.RETRY_SCHEDULED
            ).value
            job.scheduled_for = _utcnow() + timedelta(seconds=delay)
            self._store.save_job(job)
            self._emit(
                EventKind.JOB_RETRY_SCHEDULED,
                engagement_id=job.engagement_id,
                agent_id=job.agent_id,
                job_id=job.id,
                prospect_id=job.prospect_id,
                payload={"delay_seconds": delay, "next_attempt": job.attempt + 1},
            )
            # Move retry_scheduled → pending so the next tick picks it up.
            job.state = JobStateMachine.transition(
                job.state, JobState.PENDING
            ).value
            self._store.save_job(job)
        else:
            # Either non-retryable or out of attempts: dead-letter.
            job.state = JobStateMachine.transition(
                job.state, JobState.DEAD_LETTERED
            ).value
            self._store.save_job(job)
            self._emit(
                EventKind.JOB_DEAD_LETTERED,
                engagement_id=job.engagement_id,
                agent_id=job.agent_id,
                job_id=job.id,
                prospect_id=job.prospect_id,
                payload={"final_error": error[:500], "attempts": job.attempt},
            )

    def _emit(
        self,
        kind: EventKind,
        *,
        engagement_id: Optional[str],
        agent_id: Optional[str] = None,
        job_id: Optional[str] = None,
        prospect_id: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        self._events.emit(
            Event(
                id=_new_id("ev"),
                kind=kind,
                engagement_id=engagement_id,
                agent_id=agent_id,
                job_id=job_id,
                prospect_id=prospect_id,
                payload=payload or {},
            )
        )
