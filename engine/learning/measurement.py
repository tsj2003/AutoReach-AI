"""Learning measurement from real event outcomes — no fabricated benchmarks."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from engine.core.types import EventKind


@dataclass
class LearningInsight:
    category: str
    message: str
    evidence_count: int
    confidence: str  # "high" | "medium" | "low" | "insufficient"


@dataclass
class WeeklyLearningReport:
    tenant_id: str
    period_start: datetime
    period_end: datetime
    campaigns_analyzed: int
    replies_total: int
    positive_replies: int
    meetings_booked: int
    insights: list[LearningInsight] = field(default_factory=list)
    recommendations: list[LearningInsight] = field(default_factory=list)
    enough_data: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "campaigns_analyzed": self.campaigns_analyzed,
            "replies_total": self.replies_total,
            "positive_replies": self.positive_replies,
            "meetings_booked": self.meetings_booked,
            "enough_data": self.enough_data,
            "insights": [
                {"category": i.category, "message": i.message, "evidence_count": i.evidence_count, "confidence": i.confidence}
                for i in self.insights
            ],
            "recommendations": [
                {
                    "category": i.category,
                    "message": i.message,
                    "evidence_count": i.evidence_count,
                    "confidence": i.confidence,
                    "applies_automatically": False,
                }
                for i in self.recommendations
            ],
            "note": "Recommendations are advisory only — they never mutate prompts, campaigns, or send policy automatically.",
        }


POSITIVE_CLASSIFICATIONS = frozenset({"interested", "referral", "meeting_request"})


class LearningMeasurementService:
    """Aggregate tenant events into honest weekly insights."""

    def __init__(self, *, store, events) -> None:
        self._store = store
        self._events = events

    def weekly_report(self, *, tenant_id: str, days: int = 7) -> WeeklyLearningReport:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        campaigns = list(self._store.list_engagements(tenant_id=tenant_id))
        campaign_ids = {c.id for c in campaigns}

        replies_total = 0
        positive_replies = 0
        meetings_booked = 0
        signal_type_outcomes: dict[str, dict[str, int]] = defaultdict(lambda: {"positive": 0, "total": 0})

        for ev in self._events.list_recent(limit=5000):
            if ev.occurred_at and ev.occurred_at < start:
                continue
            if ev.engagement_id and ev.engagement_id not in campaign_ids:
                continue

            if ev.kind == EventKind.REPLY_CLASSIFIED:
                replies_total += 1
                cls = (ev.payload or {}).get("classification", "")
                if cls in POSITIVE_CLASSIFICATIONS:
                    positive_replies += 1
                sig = (ev.payload or {}).get("signal_type")
                if sig:
                    signal_type_outcomes[sig]["total"] += 1
                    if cls in POSITIVE_CLASSIFICATIONS:
                        signal_type_outcomes[sig]["positive"] += 1

            if ev.kind == EventKind.MEETING_BOOKED:
                meetings_booked += 1

        enough = replies_total >= 20
        insights: list[LearningInsight] = []

        if enough and replies_total:
            rate = positive_replies / replies_total
            insights.append(LearningInsight(
                category="reply_rate",
                message=f"Positive reply rate was {rate:.0%} across {replies_total} classified replies this period.",
                evidence_count=replies_total,
                confidence="medium" if replies_total >= 50 else "low",
            ))
        else:
            insights.append(LearningInsight(
                category="reply_rate",
                message="Not enough data yet to determine reply-rate trends (need ≥20 classified replies).",
                evidence_count=replies_total,
                confidence="insufficient",
            ))

        best_sig = None
        best_rate = 0.0
        for sig, counts in signal_type_outcomes.items():
            if counts["total"] >= 5:
                r = counts["positive"] / counts["total"]
                if r > best_rate:
                    best_rate = r
                    best_sig = sig
        if best_sig:
            insights.append(LearningInsight(
                category="signal_performance",
                message=f"Signal type '{best_sig}' had the highest positive-reply rate ({best_rate:.0%}) among types with ≥5 samples.",
                evidence_count=signal_type_outcomes[best_sig]["total"],
                confidence="low",
            ))

        recommendations: list[LearningInsight] = []
        if enough and replies_total and (positive_replies / replies_total) < 0.05:
            recommendations.append(LearningInsight(
                category="recommendation",
                message="Positive reply rate is under 5%. Review ICP and first-email templates before increasing volume.",
                evidence_count=replies_total,
                confidence="medium",
            ))
        if best_sig:
            recommendations.append(LearningInsight(
                category="recommendation",
                message=f"Consider prioritizing '{best_sig}' in the signal matrix (advisory only — not applied automatically).",
                evidence_count=signal_type_outcomes[best_sig]["total"],
                confidence="low",
            ))
        if not recommendations:
            recommendations.append(LearningInsight(
                category="recommendation",
                message="Keep collecting outcomes. Automated policy changes stay disabled until evidence thresholds are met.",
                evidence_count=replies_total,
                confidence="insufficient",
            ))

        return WeeklyLearningReport(
            tenant_id=tenant_id,
            period_start=start,
            period_end=end,
            campaigns_analyzed=len(campaigns),
            replies_total=replies_total,
            positive_replies=positive_replies,
            meetings_booked=meetings_booked,
            insights=insights,
            recommendations=recommendations,
            enough_data=enough,
        )
