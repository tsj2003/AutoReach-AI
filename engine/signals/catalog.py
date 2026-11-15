"""Gojiberry 21 Buying & Social Signal Types catalog, 10 ContactRejectReason codes, and dual-axis scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.signals.registry import get_signal_registry


@dataclass(frozen=True)
class GojiberrySignalSpec:
    """Specification for one of the 21 Gojiberry AI buying & social signal types."""

    code: str  # Gojiberry enum code (e.g. SEARCH_KEYWORD, WEBSITE_VISITOR)
    canonical_key: str  # Attainly/AutoReach canonical registry key
    label: str
    category: str  # "social_intent" | "company_trigger" | "job_change" | "first_party" | "ai_lookalike"
    description: str
    base_warmth: float  # 0.5 - 3.0 intent_scoring baseline
    intent_points: int = 2
    requires_value: bool = False
    placeholder: str = ""

    @property
    def name(self) -> str:
        return self.label

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "type": self.code,
            "canonical_key": self.canonical_key,
            "label": self.label,
            "name": self.label,
            "category": self.category,
            "description": self.description,
            "base_warmth": self.base_warmth,
            "intent_points": self.intent_points,
            "requires_value": self.requires_value,
            "placeholder": self.placeholder,
        }


GOJIBERRY_SIGNAL_CATALOG: tuple[GojiberrySignalSpec, ...] = (
    # 1. Social & Topic Intent Signals
    GojiberrySignalSpec(
        code="SEARCH_KEYWORD",
        canonical_key="problem_discussion",
        label="LinkedIn Keyword & Topic Engagement",
        category="social_intent",
        description="Prospects posting, commenting, or engaging with specific buying-intent keywords on LinkedIn.",
        base_warmth=2.2,
        intent_points=2,
        requires_value=True,
        placeholder="e.g. outbound automation, pipeline generation, AI SDR",
    ),
    GojiberrySignalSpec(
        code="COMPETITOR_PAGE_URL",
        canonical_key="competitor_engagement",
        label="Competitor Page Engagers",
        category="social_intent",
        description="Decision-makers liking, commenting on, or following a competitor's LinkedIn company page.",
        base_warmth=2.6,
        intent_points=3,
        requires_value=True,
        placeholder="https://www.linkedin.com/company/competitor",
    ),
    GojiberrySignalSpec(
        code="INFLUENCER_PAGE_URL",
        canonical_key="relevant_public_post",
        label="Industry Influencer Engagers",
        category="social_intent",
        description="Prospects engaging with posts from thought leaders and influencers in your category.",
        base_warmth=1.9,
        intent_points=2,
        requires_value=True,
        placeholder="https://www.linkedin.com/in/industry-leader",
    ),
    GojiberrySignalSpec(
        code="RECENT_ACTIVITY",
        canonical_key="relevant_public_post",
        label="Recent LinkedIn Post Activity",
        category="social_intent",
        description="Decision-makers who published or interacted with relevant industry posts in the last 7 days.",
        base_warmth=1.8,
        intent_points=2,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="EVENT_PARTICIPATION",
        canonical_key="event_participation",
        label="LinkedIn Event & Webinar Attendees",
        category="social_intent",
        description="Prospects registered for relevant LinkedIn Live events, webinars, or trade conferences.",
        base_warmth=2.1,
        intent_points=2,
        requires_value=True,
        placeholder="e.g. SaaStr Annual, RevOps Summit",
    ),
    GojiberrySignalSpec(
        code="GITHUB_ENGAGEMENT",
        canonical_key="technology_adoption",
        label="GitHub Repo Stargazer & Developer Activity",
        category="social_intent",
        description="Developers or engineering leaders starring, forking, or contributing to relevant open-source repos.",
        base_warmth=2.2,
        intent_points=2,
        requires_value=True,
        placeholder="e.g. posthog/posthog, supabase/supabase",
    ),
    # 2. First-Party Social Signals
    GojiberrySignalSpec(
        code="YOUR_PROFILE",
        canonical_key="relevant_public_post",
        label="Engaged With Your LinkedIn Posts",
        category="first_party",
        description="Prospects who liked, commented on, or shared your personal LinkedIn posts.",
        base_warmth=2.7,
        intent_points=3,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="VISITED_PROFILE",
        canonical_key="relevant_public_post",
        label="Visited Your LinkedIn Profile",
        category="first_party",
        description="Prospects who viewed your personal LinkedIn profile recently.",
        base_warmth=2.5,
        intent_points=3,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="YOUR_COMPANY",
        canonical_key="competitor_engagement",
        label="Engaged With Your Company Page",
        category="first_party",
        description="Prospects who interacted with your company's LinkedIn posts or product updates.",
        base_warmth=2.7,
        intent_points=3,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="YOUR_COMPANY_FOLLOWERS",
        canonical_key="competitor_engagement",
        label="Follows Your Company Page",
        category="first_party",
        description="ICP decision-makers who recently followed your company on LinkedIn.",
        base_warmth=2.4,
        intent_points=2,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="WEBSITE_VISITOR",
        canonical_key="product_launch",
        label="De-Anonymized Website Visitor",
        category="first_party",
        description="Companies and decision-makers identified visiting high-intent pages (pricing, demo, docs) on your site.",
        base_warmth=2.9,
        intent_points=3,
        requires_value=False,
    ),
    # 3. Job Change & Champion Tracking Signals
    GojiberrySignalSpec(
        code="RECENTLY_CHANGED_JOB",
        canonical_key="leadership_change",
        label="Recently Changed Jobs (<90 Days)",
        category="job_change",
        description="Decision-makers who started a new role in the last 90 days and are actively evaluating vendors.",
        base_warmth=2.5,
        intent_points=3,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="NEW_DECISION_MAKER",
        canonical_key="senior_role_opening",
        label="New Executive / VP Appointment",
        category="job_change",
        description="Newly promoted or hired C-level, VP, or Head of Department with fresh budget authority.",
        base_warmth=2.6,
        intent_points=3,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="CHAMPION_MOVED",
        canonical_key="leadership_change",
        label="Past Champion Joined New Account",
        category="job_change",
        description="Former customer or champion moved to a new ICP-fit company.",
        base_warmth=2.8,
        intent_points=3,
        requires_value=False,
    ),
    # 4. Company & Growth Triggers
    GojiberrySignalSpec(
        code="RECENT_FUNDING_EVENT",
        canonical_key="funding_round",
        label="Recent Funding Round (Seed - Series D)",
        category="company_trigger",
        description="Company raised venture or growth capital in the last 6 months to scale operations.",
        base_warmth=2.8,
        intent_points=3,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="HIRING",
        canonical_key="job_posting",
        label="Actively Hiring Target Roles",
        category="company_trigger",
        description="Company has active job postings for roles directly related to your solution.",
        base_warmth=2.2,
        intent_points=2,
        requires_value=True,
        placeholder="e.g. Account Executive, SDR, DevOps Engineer",
    ),
    GojiberrySignalSpec(
        code="HIRING_SURGE",
        canonical_key="hiring_surge",
        label="Department Hiring Surge",
        category="company_trigger",
        description="Rapid expansion in sales, engineering, or operations headcount over the past 60 days.",
        base_warmth=2.5,
        intent_points=3,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="TECHNOLOGY",
        canonical_key="technology_adoption",
        label="Tech Stack / Tool Adoption",
        category="company_trigger",
        description="Company uses or recently adopted a complementary or competing technology in their stack.",
        base_warmth=2.0,
        intent_points=2,
        requires_value=True,
        placeholder="e.g. HubSpot, Salesforce, Snowflake, Stripe",
    ),
    GojiberrySignalSpec(
        code="TECHNOLOGY_MIGRATION",
        canonical_key="technology_migration",
        label="Technology Stack Migration",
        category="company_trigger",
        description="Signals that an account is replacing legacy tooling or migrating infrastructure.",
        base_warmth=2.4,
        intent_points=2,
        requires_value=False,
    ),
    GojiberrySignalSpec(
        code="GEOGRAPHIC_EXPANSION",
        canonical_key="geographic_expansion",
        label="Market or Geographic Expansion",
        category="company_trigger",
        description="Company opening new regional offices or entering new enterprise segments.",
        base_warmth=1.9,
        intent_points=2,
        requires_value=False,
    ),
    # 5. AI Lookalike & Intent Graph
    GojiberrySignalSpec(
        code="LOOKALIKE",
        canonical_key="employee_growth",
        label="AI Lookalike of Best Customers",
        category="ai_lookalike",
        description="Account matches the firmographic, technographic, and hiring DNA of your highest-LTV customers.",
        base_warmth=2.3,
        intent_points=2,
        requires_value=True,
        placeholder="e.g. stripe.com, linear.app, figma.com",
    ),
)

CONTACT_REJECT_REASONS: list[dict[str, str]] = [
    {"code": "wrong_job_title", "label": "Wrong job title / seniority"},
    {"code": "wrong_department", "label": "Wrong department"},
    {"code": "wrong_industry", "label": "Company industry out of ICP"},
    {"code": "wrong_company_size", "label": "Company headcount out of range"},
    {"code": "wrong_location", "label": "Geographic location out of scope"},
    {"code": "company_competitor", "label": "Direct competitor"},
    {"code": "existing_customer", "label": "Already a customer or active opportunity"},
    {"code": "weak_intent_signal", "label": "Buying signal too weak or irrelevant"},
    {"code": "b2c_or_agency", "label": "B2C or agency / consulting firm"},
    {"code": "other", "label": "Other reason"},
]

VALID_REJECT_REASON_CODES: frozenset[str] = frozenset(r["code"] for r in CONTACT_REJECT_REASONS)

_BY_CODE: dict[str, GojiberrySignalSpec] = {
    spec.code.upper(): spec for spec in GOJIBERRY_SIGNAL_CATALOG
}

_CANONICAL_TO_GOJIBERRY: dict[str, GojiberrySignalSpec] = {}
for _spec in GOJIBERRY_SIGNAL_CATALOG:
    if _spec.canonical_key not in _CANONICAL_TO_GOJIBERRY:
        _CANONICAL_TO_GOJIBERRY[_spec.canonical_key] = _spec


def get_gojiberry_signal_catalog() -> list[dict[str, Any]]:
    """Return all 21 Gojiberry signal definitions as serializable dicts."""
    return [spec.as_dict() for spec in GOJIBERRY_SIGNAL_CATALOG]


def get_reject_reasons() -> list[dict[str, str]]:
    """Return all 10 Gojiberry ContactRejectReason definitions."""
    return list(CONTACT_REJECT_REASONS)


def get_gojiberry_spec(raw_type: str | None) -> GojiberrySignalSpec | None:
    """Resolve either a Gojiberry code (e.g. SEARCH_KEYWORD) or canonical key to a GojiberrySignalSpec."""
    if not raw_type:
        return None
    cleaned_upper = raw_type.strip().upper().replace("-", "_").replace(" ", "_")
    if cleaned_upper in _BY_CODE:
        return _BY_CODE[cleaned_upper]
    reg = get_signal_registry()
    canonical = reg.normalize(raw_type)
    if canonical and canonical in _CANONICAL_TO_GOJIBERRY:
        return _CANONICAL_TO_GOJIBERRY[canonical]
    return None


def resolve_signal_type(raw_type: str | None) -> GojiberrySignalSpec | None:
    """Alias for get_gojiberry_spec used by contacts and signals APIs."""
    return get_gojiberry_spec(raw_type)


def map_to_canonical_type(raw_type: str) -> str | None:
    """Map any Gojiberry or canonical signal type to its canonical registry key."""
    if not raw_type:
        return None
    cleaned_upper = raw_type.strip().upper().replace("-", "_").replace(" ", "_")
    if cleaned_upper in _BY_CODE:
        return _BY_CODE[cleaned_upper].canonical_key
    return get_signal_registry().normalize(raw_type)


def map_to_gojiberry_type(raw_type: str | None) -> str:
    """Return the Gojiberry uppercase signal code (e.g. SEARCH_KEYWORD, HIRING, WEBSITE_VISITOR)."""
    spec = get_gojiberry_spec(raw_type)
    if spec is not None:
        return spec.code
    if not raw_type:
        return "SEARCH_KEYWORD"
    return raw_type.strip().upper().replace("-", "_").replace(" ", "_")


def get_signal_warmth(raw_type: str | None, confidence: float = 0.8) -> float:
    """Compute Gojiberry intent_scoring warmth (0.0 - 3.0) from signal type and confidence."""
    spec = get_gojiberry_spec(raw_type)
    base = spec.base_warmth if spec is not None else 1.8
    conf = max(0.2, min(1.0, float(confidence or 0.8)))
    return round(min(3.0, max(0.0, base * (0.65 + 0.35 * conf))), 2)


def compute_gojiberry_scores(
    prospect: object | None = None,
    *,
    lead_score: float | None = None,
    fit_status: str | None = None,
    title: str | None = None,
    company_name: str | None = None,
    signals: list[dict[str, Any]] | None = None,
    intent_type: str | None = None,
    engagement: object | None = None,
) -> dict[str, Any]:
    """Compute dual-axis Gojiberry lead scoring & buying signal warmth fields.

    Supports both calling styles:
      1) Keyword args (`lead_score=..., fit_status=..., title=..., company_name=..., signals=..., intent_type=...`)
      2) Prospect object (`compute_gojiberry_scores(prospect, engagement=...)`)
    """
    if prospect is not None and not isinstance(prospect, (int, float, str)):
        research = dict(getattr(prospect, "research", None) or {})
        title = title or getattr(prospect, "title", None)
        company_name = company_name or getattr(prospect, "company", None)
        if lead_score is None:
            lead_score = research.get("lead_score") or research.get("priority_score")
        if fit_status is None:
            fit_status = research.get("fit")
        if signals is None:
            signals = list(research.get("signals") or [])
        if intent_type is None:
            intent_type = research.get("intent_type")

    title_str = (title or "").strip()
    comp_str = (company_name or "").strip()
    sig_list = list(signals or [])
    first_sig = sig_list[-1] if sig_list and isinstance(sig_list[-1], dict) else {}

    # 1. ICP Fit Score (1..3 integer tier for Gojiberry UI + 0.0..1.0 normalized)
    if fit_status == "bad_fit" or fit_status == "out-of-scope":
        scoring = 1
        icp_fit_ratio = 0.25
    elif lead_score is not None:
        try:
            ls = float(lead_score)
            if ls <= 1.0:
                icp_fit_ratio = round(max(0.0, min(1.0, ls)), 2)
                scoring = 3 if ls >= 0.75 else (2 if ls >= 0.45 else 1)
            elif ls <= 3.0:
                scoring = max(1, min(3, int(round(ls))))
                icp_fit_ratio = round(scoring / 3.0, 2)
            else:
                icp_fit_ratio = round(max(0.0, min(1.0, ls / 100.0)), 2)
                scoring = 3 if ls >= 75 else (2 if ls >= 45 else 1)
        except (TypeError, ValueError):
            scoring = 2
            icp_fit_ratio = 0.72
    else:
        t_low = title_str.lower()
        if any(k in t_low for k in ("vp", "vice president", "chief", "cro", "cmo", "cto", "ceo", "founder", "head", "director", "coo")):
            scoring = 3
            icp_fit_ratio = 0.90
        elif any(k in t_low for k in ("manager", "lead", "revops", "growth", "sales")):
            scoring = 2
            icp_fit_ratio = 0.72
        else:
            scoring = 2
            icp_fit_ratio = 0.65

    # 2. Signal Warmth / Intent Score (1..3 integer tier)
    raw_sig = (
        intent_type
        or first_sig.get("signal_type")
        or first_sig.get("type")
        or "SEARCH_KEYWORD"
    )
    resolved_spec = get_gojiberry_spec(str(raw_sig))
    canonical_code = resolved_spec.code if resolved_spec else map_to_gojiberry_type(str(raw_sig))

    if sig_list:
        pts = first_sig.get("intent_points")
        if pts is not None:
            intent_scoring = max(1, min(3, int(pts)))
        elif resolved_spec is not None:
            intent_scoring = resolved_spec.intent_points
        else:
            intent_scoring = 2
    elif intent_type and resolved_spec is not None:
        intent_scoring = resolved_spec.intent_points
    else:
        intent_scoring = 1

    total_scoring = scoring + intent_scoring

    intent_kw = str(
        first_sig.get("intent_keyword")
        or first_sig.get("keyword")
        or first_sig.get("title")
        or (resolved_spec.label if resolved_spec else "Active B2B Intent")
    )
    intent_label = (
        f"{resolved_spec.label}: {intent_kw}"
        if resolved_spec and intent_kw and intent_kw != resolved_spec.label
        else (resolved_spec.label if resolved_spec else intent_kw)
    )

    score_reasoning = (
        f"{title_str or 'Decision-maker'} at {comp_str or 'target account'} scored {scoring}/3 on ICP fit "
        f"({int(icp_fit_ratio * 100)}%) + {intent_scoring}/3 on {canonical_code} buying intent ({intent_label})."
    )

    return {
        "scoring": scoring,
        "icp_fit_score": icp_fit_ratio,
        "intent_scoring": intent_scoring,
        "total_scoring": total_scoring,
        "score_reasoning": score_reasoning,
        "intent": intent_label,
        "intent_type": canonical_code,
        "intent_keyword": intent_kw,
        "fit": fit_status or ("qualified" if scoring >= 2 else "unknown"),
    }
