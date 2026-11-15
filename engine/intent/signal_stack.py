"""Signal Stack policy — Attainly's differentiator.

The 2025-2026 data is blunt: generic AI outbound gets 3-5% reply rates and
burns domains within ~90 days, while outreach triggered by *multiple, fresh,
independent* buying signals ("signal stacking": funding + hiring + a champion
join) gets 15-25% and stays compliant because it is naturally low-volume.

This policy is the gate that turns Attainly from "AI writes emails" into
"Attainly only reaches out when there is real, recent, stacked evidence — and
every draft can be grounded in that evidence." It decides, per account:

  * depth      — how many DISTINCT allowed signal types stacked on the account
  * freshness  — how recent the most recent signal is (timing window matters:
                 funding ⇒ days, job change ⇒ ~30 days)
  * qualifies  — depth >= min_stack AND freshest signal within the window
  * evidence   — the concrete, cited triggers a draft may reference (and only
                 these — nothing ungrounded)

Pure and dependency-free so it is trivially testable and reusable by the intent
ingestor, the cockpit, or any future scorer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from engine.intent.models import IntentSignal

# Default "fresh enough to act on" window. Signal-based outreach decays fast;
# two weeks is a generous outer bound (funding wants <14 days, job change <30).
DEFAULT_FRESHNESS_HOURS = 24 * 14
DEFAULT_MIN_STACK = 1  # 1 = every allowed signal qualifies (backward compatible)


@dataclass(frozen=True)
class StackEvidence:
    """One cited trigger a draft is allowed to reference."""

    signal_type: str
    company_domain: str
    timestamp: str
    summary: str

    def as_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "company_domain": self.company_domain,
            "timestamp": self.timestamp,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class StackDecision:
    company_domain: str
    qualifies: bool
    depth: int                 # distinct signal types
    total_signals: int         # raw signal count (incl. duplicates of a type)
    score: int                 # 0-100, for ranking accounts
    age_hours: float           # age of the most recent signal
    reason: str
    evidence: tuple[StackEvidence, ...]
    primary: IntentSignal | None

    @property
    def allowed_signal_types(self) -> frozenset[str]:
        return frozenset(e.signal_type for e in self.evidence)


def _aware(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def _summary(sig: IntentSignal) -> str:
    return f"{sig.signal_type} detected for {sig.company_domain}"


class SignalStackPolicy:
    """Decide whether an account's stacked signals justify outreach."""

    def __init__(
        self,
        *,
        min_stack: int = DEFAULT_MIN_STACK,
        freshness_hours: float = DEFAULT_FRESHNESS_HOURS,
    ) -> None:
        self.min_stack = max(1, int(min_stack))
        self.freshness_hours = float(freshness_hours)

    def evaluate(self, signals: Sequence[IntentSignal], *, now: datetime | None = None) -> StackDecision:
        """Evaluate one account's signals (all for the same company_domain)."""
        now = now or datetime.now(timezone.utc)
        signals = list(signals)
        if not signals:
            return StackDecision(
                company_domain="", qualifies=False, depth=0, total_signals=0,
                score=0, age_hours=float("inf"), reason="no signals",
                evidence=(), primary=None,
            )

        domain = signals[0].company_domain
        # Most recent signal per distinct type → the evidence set.
        by_type: dict[str, IntentSignal] = {}
        for sig in signals:
            cur = by_type.get(sig.signal_type)
            if cur is None or _aware(sig.timestamp) > _aware(cur.timestamp):
                by_type[sig.signal_type] = sig

        primary = max(signals, key=lambda s: _aware(s.timestamp))
        age_hours = max(0.0, (now - _aware(primary.timestamp)).total_seconds() / 3600.0)
        depth = len(by_type)
        fresh = age_hours <= self.freshness_hours

        evidence = tuple(
            StackEvidence(
                signal_type=s.signal_type,
                company_domain=s.company_domain,
                timestamp=_aware(s.timestamp).isoformat(),
                summary=_summary(s),
            )
            for s in sorted(by_type.values(), key=lambda s: _aware(s.timestamp), reverse=True)
        )

        qualifies = depth >= self.min_stack and fresh
        if depth < self.min_stack:
            reason = f"stack depth {depth} < required {self.min_stack}"
        elif not fresh:
            reason = f"stale: freshest signal {age_hours:.0f}h old > {self.freshness_hours:.0f}h window"
        else:
            reason = f"qualified: {depth} stacked signal type(s), freshest {age_hours:.0f}h old"

        return StackDecision(
            company_domain=domain,
            qualifies=qualifies,
            depth=depth,
            total_signals=len(signals),
            score=self._score(depth, age_hours),
            age_hours=age_hours,
            reason=reason,
            evidence=evidence,
            primary=primary,
        )

    def _score(self, depth: int, age_hours: float) -> int:
        """0-100 rank. Depth dominates (stacking is the strongest lever); a
        recency bonus decays linearly across the freshness window."""
        depth_pts = min(depth, 4) * 20  # up to 80 for 4+ stacked types
        recency_frac = max(0.0, 1.0 - (age_hours / self.freshness_hours)) if self.freshness_hours else 0.0
        return int(min(100, depth_pts + round(recency_frac * 20)))

    @staticmethod
    def group_by_account(signals: Iterable[IntentSignal]) -> dict[str, list[IntentSignal]]:
        accounts: dict[str, list[IntentSignal]] = {}
        for sig in signals:
            accounts.setdefault(sig.company_domain, []).append(sig)
        return accounts
