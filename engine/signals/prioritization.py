"""Prospect ordering by signal priority score."""

from __future__ import annotations

from engine.core.types import Prospect
from engine.intent.signal_stack import SignalStackPolicy, StackDecision
from engine.signals.scoring import ProspectPriorityScorer


def prospect_priority_score(prospect: Prospect, *, icp_keywords: list[str] | None = None) -> int:
    """Return 0–100 priority score from persisted research metadata."""

    research = prospect.research if isinstance(prospect.research, dict) else {}
    priority = research.get("priority_score")
    if isinstance(priority, (int, float)):
        return max(0, min(100, int(priority)))

    stack_data = research.get("signal_stack")
    if not isinstance(stack_data, dict):
        return 0

    # Reconstruct minimal StackDecision for scorer when evidence present
    evidence_raw = stack_data.get("evidence") or []
    if evidence_raw and stack_data.get("depth"):
        from engine.intent.signal_stack import StackEvidence

        evidence = tuple(
            StackEvidence(
                signal_type=str(e.get("signal_type", "")),
                company_domain=str(e.get("company_domain", prospect.company or "")),
                timestamp=str(e.get("timestamp", "")),
                summary=str(e.get("summary", "")),
            )
            for e in evidence_raw
            if isinstance(e, dict)
        )
        decision = StackDecision(
            company_domain=prospect.company or "",
            qualifies=True,
            depth=int(stack_data.get("depth") or 0),
            total_signals=len(evidence),
            score=int(stack_data.get("score") or 0),
            age_hours=float(stack_data.get("age_hours") or 9999),
            reason="from prospect research",
            evidence=evidence,
            primary=None,
        )
        scored = ProspectPriorityScorer().score_account(stack=decision, icp_keywords=icp_keywords)
        return scored.score

    score = stack_data.get("score")
    if isinstance(score, (int, float)):
        return max(0, min(100, int(score)))
    return 0


def sort_prospects_by_priority(
    prospects: list[Prospect],
    *,
    icp_keywords: list[str] | None = None,
) -> list[Prospect]:
    """Sort prospects highest-priority first (stable for ties)."""

    return sorted(
        prospects,
        key=lambda p: (-prospect_priority_score(p, icp_keywords=icp_keywords), p.id),
    )
