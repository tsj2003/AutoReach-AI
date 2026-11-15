"""5 Free AI Lead-Magnet Tools API (`/api/free-tools`).

Implements Gojiberry's 5 public/in-app AI outbound utilities:
1. `POST /api/free-tools/sales-nav-filters` — LinkedIn Sales Navigator filter + Boolean string generator
2. `POST /api/free-tools/icp-generator` — B2B Ideal Customer Profile & Buying Trigger generator
3. `POST /api/free-tools/subject-lines` — Signal-aware Cold Email Subject Line generator
4. `POST /api/free-tools/persona-generator` — Deep Buyer Persona & Objection Playbook generator
5. `POST /api/free-tools/message-analyser` — Cold Email / LinkedIn Message Scorer & AI Rewriter
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engine.services.deliverability_guardian import DeliverabilityGuardian

router = APIRouter(prefix="/api/free-tools", tags=["free-tools"])


class SalesNavFilterRequest(BaseModel):
    product_description: str = ""
    company_description: Optional[str] = None
    offer: Optional[str] = None
    target_role: Optional[str] = None
    industry: Optional[str] = None
    target_roles: List[str] = Field(default_factory=list)
    excluded_roles: List[str] = Field(default_factory=list)
    industries: List[str] = Field(default_factory=list)
    company_sizes: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class ICPGeneratorRequest(BaseModel):
    company_name: str = "Your Company"
    website_url: Optional[str] = None
    product_description: str = ""
    target_market: str = "B2B SaaS"


class SubjectLinesRequest(BaseModel):
    offer: str = ""
    target_role: str = "VP of Sales"
    signal_type: str = "RECENT_FUNDING_EVENT"
    company_name: str = "{company_name}"
    tone: str = "Direct"


class PersonaGeneratorRequest(BaseModel):
    job_title: str = "VP of Sales"
    industry: str = "B2B SaaS"
    company_size: str = "51-200"
    product_offer: str = ""


class MessageAnalyserRequest(BaseModel):
    subject: str = ""
    message: str = ""
    body: Optional[str] = None
    channel: str = "email"  # "email" | "linkedin"


def _build_boolean_string(include_terms: List[str], exclude_terms: List[str]) -> str:
    inc = [f'"{t.strip()}"' if " " in t.strip() else t.strip() for t in include_terms if t.strip()]
    exc = [f'"{t.strip()}"' if " " in t.strip() else t.strip() for t in exclude_terms if t.strip()]
    if not inc:
        inc = ['"VP of Sales"', '"Head of Growth"', '"Chief Revenue Officer"', '"Director of Sales"']
    expr = "(" + " OR ".join(inc) + ")"
    if exc:
        expr += " NOT (" + " OR ".join(exc) + ")"
    return expr


@router.post("/sales-nav-filters")
def generate_sales_nav_filters(payload: SalesNavFilterRequest) -> Dict[str, Any]:
    roles = list(payload.target_roles or [])
    if payload.target_role and payload.target_role.strip():
        roles.append(payload.target_role.strip())
    if not roles:
        roles = [
            "VP of Sales",
            "Head of Growth",
            "Chief Revenue Officer",
            "Director of Revenue Operations",
            "Head of Business Development",
        ]
    industries = list(payload.industries or [])
    if payload.industry and payload.industry.strip():
        industries.append(payload.industry.strip())
    if not industries:
        industries = ["Software Development", "IT Services and IT Consulting", "Financial Services"]
    excluded = payload.excluded_roles or ["Intern", "Assistant", "Consultant", "Student", "Recruiter"]
    title_boolean = _build_boolean_string(roles, excluded)

    kw_list = payload.keywords or ["outbound", "pipeline", "revenue operations", "B2B SaaS", "demand generation"]
    keyword_boolean = _build_boolean_string(kw_list, ["agency", "freelance"])
    boolean_search_string = f"{title_boolean} AND {keyword_boolean}"

    return {
        "title_boolean": title_boolean,
        "keyword_boolean": keyword_boolean,
        "combined_boolean": boolean_search_string,
        "boolean_search_string": boolean_search_string,
        "lead_filters": {
            "current_job_title": {"include": roles, "exclude": excluded},
            "seniority_level": {"include": ["CXO", "Vice President", "Director"], "exclude": ["Entry", "Training"]},
            "function": {"include": ["Sales", "Business Development", "Marketing", "Operations"], "exclude": []},
            "geography": {"include": payload.locations or ["United States", "United Kingdom", "Canada"], "exclude": []},
            "keywords": kw_list,
        },
        "account_filters": {
            "industry": {"include": industries, "exclude": ["Non-Profit", "Government Administration"]},
            "company_headcount": {"include": payload.company_sizes or ["11-50", "51-200", "201-500"], "exclude": ["Self-employed"]},
            "activities": [
                "Changed jobs in the past 90 days",
                "Posted on LinkedIn in past 30 days",
                "Senior leadership changes in past 3 months",
            ],
        },
        "filters": {
            "current_job_titles": roles,
            "excluded_job_titles": excluded,
            "seniority_levels": ["CXO", "Vice President", "Director", "Owner / Partner"],
            "functions": ["Sales", "Business Development", "Marketing", "Operations"],
            "company_headcount": payload.company_sizes or ["11-50", "51-200", "201-500"],
            "industries": industries,
            "geographies": payload.locations or ["United States", "United Kingdom", "Canada", "Western Europe"],
            "spotlights": [
                "Changed jobs in the past 90 days (JOB_CHANGES)",
                "Posted on LinkedIn in past 30 days (POSTS_FROM_PROSPECT)",
                "Company headcount growth > 10% (HIRING_SURGE)",
            ],
        },
    }


@router.post("/icp-generator")
def generate_icp_profile(payload: ICPGeneratorRequest) -> Dict[str, Any]:
    offer_desc = payload.product_description.strip() or f"{payload.company_name} automates signal-driven B2B outbound."
    return {
        "company_name": payload.company_name,
        "target_market": payload.target_market,
        "ideal_firmographics": {
            "industries": [payload.target_market, "Computer Software", "Developer Tools", "FinTech"],
            "employee_ranges": ["11-50", "51-200", "201-500"],
            "revenue_range": "$2M - $50M ARR",
            "geographies": ["United States", "United Kingdom", "Canada", "DACH & Western Europe"],
            "funding_stages": ["Seed", "Series A", "Series B", "Bootstrapped Profitable"],
        },
        "buying_committee": [
            {"role": "Economic Buyer", "titles": ["Chief Revenue Officer", "VP of Sales", "Founder / CEO"]},
            {"role": "Champion", "titles": ["Head of Growth", "Director of Sales Development", "Head of RevOps"]},
            {"role": "Technical Evaluator", "titles": ["RevOps Manager", "GTM Engineer", "Marketing Operations Lead"]},
        ],
        "core_pain_points": [
            "SDRs spend 60%+ of their week researching accounts manually across 5+ tabs",
            "Generic cold spray-and-pray sequences suffer <1% reply rates and burn domain reputation",
            "High-intent website visitors and LinkedIn post engagers go uncontacted while intent is hot",
        ],
        "top_buying_signals": [
            {"type": "HIRING_SURGE", "reason": "Scaling GTM or engineering headcount creates immediate tooling urgency"},
            {"type": "RECENT_FUNDING_EVENT", "reason": "New capital requires aggressive pipeline targets within 90 days"},
            {"type": "NEW_DECISION_MAKER", "reason": "New VPs audit and replace legacy workflows in their first quarter"},
            {"type": "WEBSITE_VISITOR", "reason": "Active evaluation of pricing or documentation pages"},
        ],
        "disqualifiers": [
            "B2C-only companies with low ACV (<$1,000/yr)",
            "Solo consultants or agencies without an active outbound motion",
        ],
        "value_proposition": offer_desc,
    }


@router.post("/subject-lines")
def generate_subject_lines(payload: SubjectLinesRequest) -> Dict[str, Any]:
    sig = (payload.signal_type or "RECENT_FUNDING_EVENT").upper()
    role = payload.target_role or "VP of Sales"
    items = [
        {"subject": "quick question re: {company_name}'s growth", "angle": "Signal Hook", "predicted_open_rate": 64},
        {"subject": "saw {company_name} is hiring — quick thought", "angle": "Hiring Trigger", "predicted_open_rate": 61},
        {"subject": "{first_name} — outbound signals at {company_name}", "angle": "Peer-to-Peer", "predicted_open_rate": 58},
        {"subject": "how peer {industry} teams 3x reply rates", "angle": "Social Proof", "predicted_open_rate": 56},
        {"subject": "idea for {company_name}'s GTM team", "angle": "Value Drop", "predicted_open_rate": 55},
        {"subject": "congrats on the momentum at {company_name}", "angle": "Trigger Event", "predicted_open_rate": 59},
        {"subject": f"question for {role} at {{company_name}}", "angle": "Role Specific", "predicted_open_rate": 54},
        {"subject": "eliminating manual lead research at {company_name}", "angle": "Pain Point", "predicted_open_rate": 53},
        {"subject": "loved your recent LinkedIn post, {first_name}", "angle": "First-Party Social", "predicted_open_rate": 66},
        {"subject": "{first_name} / {sender_name}", "angle": "Ultra-Short", "predicted_open_rate": 60},
    ]
    return {
        "signal_type": sig,
        "target_role": role,
        "tone": payload.tone,
        "count": len(items),
        "items": items,
    }


@router.post("/persona-generator")
def generate_buyer_persona(payload: PersonaGeneratorRequest) -> Dict[str, Any]:
    title = payload.job_title or "VP of Sales"
    industry = payload.industry or "B2B SaaS"
    return {
        "job_title": title,
        "industry": industry,
        "company_size": payload.company_size,
        "kpis_owned": [
            "Net-new qualified pipeline generated ($ ARR)",
            "Meetings booked per SDR / AE per month",
            "Outbound reply rate and positive-reply conversion %",
            "CAC payback period and sales cycle velocity",
        ],
        "daily_frustrations": [
            "Reps reaching out to low-fit accounts with zero buying intent",
            "Data decay and bounced emails hurting primary sending domains",
            "Disconnected point solutions across LinkedIn, email, enrichment, and CRM",
        ],
        "common_objections": [
            {
                "objection": "We already use Apollo / ZoomInfo for data.",
                "rebuttal": "Static databases tell you who exists; real-time buying signals tell you who is ready to buy this week.",
            },
            {
                "objection": "Our team doesn't have bandwidth to manage another tool.",
                "rebuttal": "The Full-Cycle AI Agent runs autonomously from signal detection to 15-provider waterfall enrichment and multichannel sequencing.",
            },
        ],
        "messaging_dos": [
            "Lead with the exact buying signal (hiring, funding, post interaction) in sentence one",
            "Keep cold emails under 85 words and LinkedIn DMs under 300 characters",
            "Use a low-friction interest CTA ('Worth exploring?' vs 'Book 30 mins Tuesday at 2pm')",
        ],
        "messaging_donts": [
            "Never open with 'I hope this email finds you well'",
            "Avoid feature-dumping or attaching PDFs in touch #1",
        ],
    }


@router.post("/message-analyser")
def analyse_outreach_message(payload: MessageAnalyserRequest) -> Dict[str, Any]:
    body = (payload.message or payload.body or "").strip()
    subject = (payload.subject or "").strip()
    words = re.findall(r"\S+", body)
    word_count = len(words)
    sentences = [s.strip() for s in re.split(r"[.!?]+", body) if s.strip()]
    sentence_count = max(1, len(sentences))

    guardian = DeliverabilityGuardian()
    report = guardian.score(subject=subject or "quick question", body=body)

    # Compute 5 sub-scores (0..100)
    brevity_score = 95 if 35 <= word_count <= 95 else max(35, 95 - abs(word_count - 65))
    has_signal_tokens = any(
        tok in body.lower()
        for tok in ("{first_name}", "{company_name}", "saw ", "noticed ", "post", "hiring", "funding", "congrats")
    )
    personalization_score = 90 if has_signal_tokens else 52
    deliverability_score = max(20, 100 - len(report.issues) * 18)
    has_soft_cta = body.rstrip().endswith("?")
    cta_score = 92 if has_soft_cta else 58
    you_count = len(re.findall(r"\b(you|your)\b", body.lower()))
    i_we_count = len(re.findall(r"\b(i|we|our|my)\b", body.lower()))
    ratio_score = 90 if you_count >= i_we_count else 62

    overall_score = round(
        (brevity_score * 0.22)
        + (personalization_score * 0.25)
        + (deliverability_score * 0.23)
        + (cta_score * 0.15)
        + (ratio_score * 0.15)
    )
    grade = (
        "A" if overall_score >= 85
        else "B" if overall_score >= 72
        else "C" if overall_score >= 58
        else "D"
    )

    feedback: List[str] = []
    if word_count > 100:
        feedback.append(f"Trim word count from {word_count} to under 85 words for mobile readability.")
    elif word_count < 25:
        feedback.append("Add one concrete proof point or signal reference so the message has clear context.")
    if not has_signal_tokens:
        feedback.append("Anchor the first sentence to a real buying signal (post interaction, hiring surge, or funding).")
    if not has_soft_cta:
        feedback.append("Close with a low-friction question mark CTA (e.g., 'Open to a quick look?').")
    if i_we_count > you_count:
        feedback.append(f"Shift focus from 'I/we' ({i_we_count}x) to 'you/your' ({you_count}x).")
    for issue in report.issues:
        feedback.append(f"Deliverability warning ({issue.severity}): {issue.detail} — {issue.fix}")

    improved_version = (
        "Hi {first_name},\n\n"
        "Saw {company_name}'s recent growth signal and noticed you're scaling the GTM team.\n\n"
        "We help B2B teams turn real-time buying signals into verified decision-maker conversations "
        "without manual list building.\n\n"
        "Worth a quick 10-minute look this week?"
    )

    return {
        "overall_score": overall_score,
        "grade": grade,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "reading_time_seconds": max(3, round(word_count / 3.5)),
        "breakdown": {
            "brevity": brevity_score,
            "signal_personalization": personalization_score,
            "deliverability_safety": deliverability_score,
            "cta_clarity": cta_score,
            "buyer_centric_ratio": ratio_score,
        },
        "deliverability_issues": [
            {"code": i.code, "severity": i.severity, "detail": i.detail, "fix": i.fix}
            for i in report.issues
        ],
        "feedback": feedback or ["Strong signal-first message with clean deliverability and a low-friction CTA."],
        "improved_subject": subject or "quick question about {company_name}, {first_name}",
        "improved_message": improved_version,
    }
