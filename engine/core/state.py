"""
Job state machine for the AutoReach engine.

A Job moves through explicit states. Transitions are guarded — illegal
transitions raise `IllegalTransition` rather than silently corrupt state.
This is the single source of truth for "what can a Job do next?"

Lifecycle
---------

    pending ─────────► awaiting_approval ─► approved ─► running
       │                       │                          │
       │                       └─► rejected (terminal)    │
       │                                                  │
       └────────────────────────────────────────────────► running
                                                          │
                              ┌───────────────────────────┤
                              ▼                           ▼
                          succeeded                    failed
                          (terminal)                      │
                                          ┌───────────────┴───────────┐
                                          ▼                           ▼
                                  retry_scheduled              dead_lettered
                                       │                       (terminal)
                                       │
                                       └─► pending (next attempt)

States that need human attention: `awaiting_approval`, `failed` (before retry decision), `dead_lettered`.

Why a state machine
-------------------
* OaaS will run thousands of Jobs concurrently across many Engagements.
  We can never debug "what state was this Job in?" by reading a log file.
* The HITL trust ramp ("first 50 actions per customer require approval")
  needs a clean way to gate execution. State machine gives us this for free.
* Replay & resume on crash need explicit transitions, not implicit booleans.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class JobState(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"           # terminal
    RUNNING = "running"
    SUCCEEDED = "succeeded"         # terminal
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"  # terminal


# Valid transitions. (from_state -> set of allowed to_states)
_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.PENDING: frozenset({
        JobState.AWAITING_APPROVAL,
        JobState.RUNNING,
    }),
    JobState.AWAITING_APPROVAL: frozenset({
        JobState.APPROVED,
        JobState.REJECTED,
    }),
    JobState.APPROVED: frozenset({
        JobState.RUNNING,
    }),
    JobState.RUNNING: frozenset({
        JobState.SUCCEEDED,
        JobState.FAILED,
    }),
    JobState.FAILED: frozenset({
        JobState.RETRY_SCHEDULED,
        JobState.DEAD_LETTERED,
    }),
    JobState.RETRY_SCHEDULED: frozenset({
        JobState.PENDING,
    }),
    # Terminal states — no transitions out.
    JobState.SUCCEEDED: frozenset(),
    JobState.REJECTED: frozenset(),
    JobState.DEAD_LETTERED: frozenset(),
}


TERMINAL_STATES: frozenset[JobState] = frozenset({
    JobState.SUCCEEDED,
    JobState.REJECTED,
    JobState.DEAD_LETTERED,
})


class IllegalTransition(ValueError):
    """Raised when a state change violates the state machine."""


class JobStateMachine:
    """
    Guards Job state transitions.

    Stateless utility — no instance state. We expose it as a class so that
    in the future we can subclass for per-product policy variations
    (e.g., a stricter machine for compliance-sensitive workloads).
    """

    @staticmethod
    def can_transition(from_state: JobState | str, to_state: JobState | str) -> bool:
        f = JobState(from_state)
        t = JobState(to_state)
        return t in _TRANSITIONS.get(f, frozenset())

    @staticmethod
    def transition(from_state: JobState | str, to_state: JobState | str) -> JobState:
        """Return `to_state` if the transition is legal; raise otherwise."""
        f = JobState(from_state)
        t = JobState(to_state)
        if not JobStateMachine.can_transition(f, t):
            raise IllegalTransition(
                f"illegal job state transition: {f.value} -> {t.value}"
            )
        return t

    @staticmethod
    def is_terminal(state: JobState | str) -> bool:
        return JobState(state) in TERMINAL_STATES

    @staticmethod
    def successors(state: JobState | str) -> Iterable[JobState]:
        return iter(_TRANSITIONS.get(JobState(state), frozenset()))
