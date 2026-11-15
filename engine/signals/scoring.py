"""Transparent, explainable prospect priority scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from engine.intent.models import IntentSignal
from engine.intent.signal_stack import StackDecision
from engine.signals.registry import SignalTypeRegistry, get_signal_registry


@dataclass(frozen=True)
class ScoreFactor:
    label: str
    points: int
    reason: str

    def as_dict(self) -> dict:
        return {"label": self.label, "points": self.points, "reason": self.reason}


@dataclass(frozen=True)
class ProspectPriorityScore:
    score: int  # 0–100
    factors: tuple[ScoreFactor, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "factors": [f.as_dict() for f in self.factors],
            "explanation": "; ".join(f"+{f.points} {f.label}" for f in self.factors),
        }


class ProspectPriorityScorer:
    """Explainable scoring — never random, never hard-coded 87."""

    def __init__(self, registry: SignalTypeRegistry | None = None) -> None:
        self._registry = registry or get_signal_registry()

    def score_account(
        self,
        *,
        stack: StackDecision,
        icp_keywords: list[str] | None = None,
        campaign_outcomes: dict[str, float] | None = None,
    ) -> ProspectPriorityScore:
        factors: list[ScoreFactor] = []

        if stack.qualifies:
            factors.append(ScoreFactor(
                label="signal stack",
                points=min(25, stack.depth * 8),
                reason=f"{stack.depth} distinct fresh signal type(s)",
            ))
        else:
            return ProspectPriorityScore(score=0, factors=tuple(factors))

        # Recency bonus from stack decision age
        if stack.age_hours is not None:
            if stack.age_hours <= 48:
                recency_pts = 20
            elif stack.age_hours <= 168:
                recency_pts = 15
            elif stack.age_hours <= 336:
                recency_pts = 10
            else:
                recency_pts = 5
            factors.append(ScoreFactor(
                label="signal freshness",
                points=recency_pts,
                reason=f"most recent signal {stack.age_hours:.0f}h ago",
            ))

        # Stack score from SignalStackPolicy (already 0–100 internal)
        stack_pts = min(20, stack.score // 5)
        if stack_pts > 0:
            factors.append(ScoreFactor(
                label="stack strength",
                points=stack_pts,
                reason=f"stack score {stack.score}/100",
            ))

        # ICP keyword match against evidence summaries
        if icp_keywords and stack.evidence:
            joined = " ".join(e.summary.lower() for e in stack.evidence)
            matches = sum(1 for kw in icp_keywords if kw.lower() in joined)
            if matches:
                icp_pts = min(20, matches * 7)
                factors.append(ScoreFactor(
                    label="ICP match",
                    points=icp_pts,
                    reason=f"{matches} ICP keyword(s) in evidence",
                ))

        # Corroboration: multiple evidence items
        if len(stack.evidence) >= 2:
            factors.append(ScoreFactor(
                label="corroboration",
                points=min(10, (len(stack.evidence) - 1) * 5),
                reason=f"{len(stack.evidence)} corroborating signals",
            ))

        # Historical conversion pattern (only when sufficient data exists)
        if campaign_outcomes:
            rate = campaign_outcomes.get(stack.evidence[0].signal_type if stack.evidence else "")
            if rate is not None and rate > 0:
                hist_pts = min(5, int(rate * 10))
                if hist_pts > 0:
                    factors.append(ScoreFactor(
                        label="historical pattern",
                        points=hist_pts,
                        reason=f"signal type historical positive rate {rate:.0%}",
                    ))

        total = min(100, sum(f.points for f in factors))
        return ProspectPriorityScore(score=total, factors=tuple(factors))

    def score_signals(
        self,
        signals: list[IntentSignal],
        *,
        min_stack: int = 1,
        icp_keywords: list[str] | None = None,
    ) -> ProspectPriorityScore:
        """Score from raw IntentSignal list using SignalStackPolicy."""

        from engine.intent.signal_stack import SignalStackPolicy

        if not signals:
            return ProspectPriorityScore(score=0, factors=())

        domain = signals[0].company_domain
        policy = SignalStackPolicy(min_stack=min_stack)
        stack = policy.evaluate(signals)
        if stack.company_domain != domain:
            grouped = SignalStackPolicy.group_by_account(signals)
            account_signals = grouped.get(domain, signals)
            stack = policy.evaluate(account_signals)
        return self.score_account(stack=stack, icp_keywords=icp_keywords)


def compute_gojiberry_scores(
    prospect: object,
    *,
    engagement: object | None = None,
) -> dict[str, object]:
    """Compute dual-axis Gojiberry AI lead scoring & buying signal warmth fields for a prospect.

    Returns:
      - scoring: float (0.0 - 1.0 ICP fit score)
      - score_reasoning: str (natural language explanation)
      - intent: str (human-readable signal summary)
      - intent_type: str (Gojiberry uppercase signal code, e.g. SEARCH_KEYWORD, HIRING, WEBSITE_VISITOR)
      - intent_keyword: str (trigger keyword, role, domain, or topic)
      - intent_scoring: float (0.0 - 3.0 signal warmth)
      - total_scoring: float (scoring + intent_scoring, 0.0 - 4.0)
      - fit: "qualified" | "unknown" | "out-of-scope"
    """
    from engine.signals.catalog import get_gojiberry_spec, get_signal_warmth, map_to_gojiberry_type

    research = dict(getattr(prospect, "research", None) or {})
    title = (getattr(prospect, "title", None) or "").strip()
    company = (getattr(prospect, "company", None) or "").strip()
    email = (getattr(prospect, "email", None) or "").strip()

    # 1. Determine ICP fit score (0.0 - 1.0)
    explicit_scoring = research.get("scoring")
    if explicit_scoring is not None:
        try:
            scoring = round(max(0.0, min(1.0, float(explicit_scoring))), 2)
        except (TypeError, ValueError):
            scoring = 0.0
    elif "priority_score" in research and research.get("priority_score") is not None:
        try:
            p_score = float(research["priority_score"])
            scoring = round(max(0.0, min(1.0, p_score / 100.0 if p_score > 1.0 else p_score)), 2)
        except (TypeError, ValueError):
            scoring = 0.72
    else:
        base_icp = 0.55
        title_lower = title.lower()
        if any(
            k in title_lower
            for k in ("vp", "vice president", "chief", "cro", "cmo", "cto", "ceo", "founder", "head of", "director")
        ):
            base_icp += 0.25
        elif any(k in title_lower for k in ("manager", "lead", "principal", "revops", "growth", "sales")):
            base_icp += 0.14
        if company:
            base_icp += 0.08
        if email and "@" in email:
            base_icp += 0.05
        scoring = round(max(0.0, min(0.98, base_icp)), 2)

    # 2. Extract signal evidence & intent metadata
    signals_list = research.get("signals")
    custom_signals = research.get("custom_signals")
    first_sig: dict[str, object] = {}
    if isinstance(custom_signals, list) and custom_signals and isinstance(custom_signals[-1], dict):
        first_sig = custom_signals[-1]
    elif isinstance(signals_list, list) and signals_list and isinstance(signals_list[0], dict):
        first_sig = signals_list[0]

    raw_sig_type = (
        research.get("intent_type")
        or first_sig.get("signal_type")
        or first_sig.get("type")
        or research.get("signal_type")
        or ("HIRING" if "hiring" in str(research).lower() else "SEARCH_KEYWORD")
    )
    intent_type = map_to_gojiberry_type(str(raw_sig_type))
    spec = get_gojiberry_spec(intent_type)

    intent_keyword = str(
        research.get("intent_keyword")
        or first_sig.get("intent_keyword")
        or first_sig.get("keyword")
        or first_sig.get("topic")
        or (title if title else company or "B2B Outbound")
    )

    intent_summary = str(
        research.get("intent")
        or first_sig.get("intent")
        or first_sig.get("summary")
        or (
            f"{spec.label}: {intent_keyword}"
            if spec is not None
            else f"Active buying signal detected around {intent_keyword}"
        )
    )

    # 3. Compute intent_scoring (0.0 - 3.0 signal warmth)
    explicit_intent_scoring = research.get("intent_scoring")
    if explicit_intent_scoring is not None:
        try:
            intent_scoring = round(max(0.0, min(3.0, float(explicit_intent_scoring))), 2)
        except (TypeError, ValueError):
            intent_scoring = get_signal_warmth(intent_type, confidence=0.82)
    else:
        sig_conf = float(first_sig.get("confidence", 0.82) or 0.82)
        corroboration_bonus = 0.0
        if isinstance(signals_list, list) and len(signals_list) > 1:
            corroboration_bonus += min(0.45, (len(signals_list) - 1) * 0.15)
        if isinstance(custom_signals, list) and len(custom_signals) > 0:
            corroboration_bonus += min(0.35, len(custom_signals) * 0.18)
        intent_scoring = round(
            min(3.0, get_signal_warmth(intent_type, confidence=sig_conf) + corroboration_bonus),
            2,
        )

    total_scoring = round(scoring + intent_scoring, 2)

    # 4. Determine fit classification & natural-language score reasoning
    explicit_fit = research.get("fit")
    if explicit_fit in ("qualified", "unknown", "out-of-scope"):
        fit = str(explicit_fit)
    else:
        min_threshold = 0.6
        if engagement is not None:
            meta = getattr(engagement, "metadata", None) or {}
            try:
                min_threshold = float(meta.get("min_lead_score", 0.6))
            except (TypeError, ValueError):
                min_threshold = 0.6
        if scoring >= min_threshold:
            fit = "qualified"
        elif scoring >= 0.35:
            fit = "unknown"
        else:
            fit = "out-of-scope"

    score_reasoning = str(
        research.get("score_reasoning")
        or research.get("score_explanation")
        or (
            f"{title or 'Decision-maker'} at {company or 'target account'} matches ICP criteria "
            f"(fit score {int(scoring * 100)}%) with {intent_type} buying warmth ({intent_scoring:.1f}/3.0): "
            f"{intent_summary}."
        )
    )

    return {
        "scoring": scoring,
        "score_reasoning": score_reasoning,
        "intent": intent_summary,
        "intent_type": intent_type,
        "intent_keyword": intent_keyword,
        "intent_scoring": intent_scoring,
        "total_scoring": total_scoring,
        "fit": fit,
    }
