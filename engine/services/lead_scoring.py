"""Advanced lead enrichment and scoring system similar to Gojiberry.

This provides sophisticated lead scoring based on:
- ICP fit analysis
- Intent signal strength
- Engagement potential
- Company growth indicators
- Technology stack analysis
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class LeadTier(Enum):
    """Lead quality tiers."""
    HOT = "hot"  # High intent, strong ICP fit
    WARM = "warm"  # Moderate intent, good ICP fit
    COLD = "cold"  # Low intent, weak ICP fit
    UNQUALIFIED = "unqualified"  # Doesn't meet minimum criteria


@dataclass
class LeadScore:
    """Comprehensive lead scoring result."""
    overall_score: int  # 0-100
    tier: LeadTier
    icp_fit_score: int  # 0-100
    intent_score: int  # 0-100
    engagement_score: int  # 0-100
    company_health_score: int  # 0-100
    factors: Dict[str, Any]
    recommendation: str
    priority: str  # "high", "medium", "low"


class LeadScoringEngine:
    """Advanced lead scoring engine with multiple scoring dimensions."""

    def __init__(self):
        self._icp_weights = {
            "company_size": 0.25,
            "industry": 0.20,
            "revenue": 0.20,
            "location": 0.15,
            "tech_stack": 0.10,
            "growth_signals": 0.10
        }
        self._intent_weights = {
            "recency": 0.30,
            "signal_strength": 0.25,
            "signal_diversity": 0.20,
            "decision_maker": 0.15,
            "budget_indicators": 0.10
        }

    def score_lead(
        self,
        prospect_data: Dict[str, Any],
        icp_definition: Dict[str, Any],
        intent_signals: List[Dict[str, Any]]
    ) -> LeadScore:
        """Calculate comprehensive lead score."""
        
        # Calculate individual dimension scores
        icp_score = self._calculate_icp_fit(prospect_data, icp_definition)
        intent_score = self._calculate_intent_score(intent_signals)
        engagement_score = self._calculate_engagement_potential(prospect_data)
        company_health_score = self._calculate_company_health(prospect_data)
        
        # Calculate weighted overall score
        overall_score = (
            icp_score * 0.35 +
            intent_score * 0.30 +
            engagement_score * 0.20 +
            company_health_score * 0.15
        )
        
        # Determine tier and priority
        tier = self._determine_tier(overall_score, icp_score, intent_score)
        priority = self._determine_priority(tier, overall_score)
        recommendation = self._generate_recommendation(tier, overall_score)
        
        # Collect scoring factors
        factors = {
            "icp_fit": icp_score,
            "intent": intent_score,
            "engagement": engagement_score,
            "company_health": company_health_score,
            "matched_criteria": self._get_matched_icp_criteria(prospect_data, icp_definition),
            "signal_count": len(intent_signals),
            "recent_signals": self._count_recent_signals(intent_signals)
        }
        
        return LeadScore(
            overall_score=int(overall_score),
            tier=tier,
            icp_fit_score=icp_score,
            intent_score=intent_score,
            engagement_score=int(engagement_score),
            company_health_score=int(company_health_score),
            factors=factors,
            recommendation=recommendation,
            priority=priority
        )

    def _calculate_icp_fit(
        self,
        prospect_data: Dict[str, Any],
        icp_definition: Dict[str, Any]
    ) -> int:
        """Calculate ICP fit score based on defined criteria."""
        score = 0
        
        # Company size matching
        target_sizes = icp_definition.get("company_sizes", [])
        prospect_size = prospect_data.get("company_size", "")
        if prospect_size in target_sizes or not target_sizes:
            score += self._icp_weights["company_size"] * 100
        
        # Industry matching
        target_industries = icp_definition.get("industries", [])
        prospect_industry = prospect_data.get("industry", "")
        if prospect_industry in target_industries or not target_industries:
            score += self._icp_weights["industry"] * 100
        
        # Revenue matching
        min_revenue = icp_definition.get("min_revenue", 0)
        max_revenue = icp_definition.get("max_revenue", float('inf'))
        prospect_revenue = prospect_data.get("revenue", 0)
        if min_revenue <= prospect_revenue <= max_revenue:
            score += self._icp_weights["revenue"] * 100
        
        # Location matching
        target_locations = icp_definition.get("locations", [])
        prospect_location = prospect_data.get("location", "")
        if prospect_location in target_locations or not target_locations:
            score += self._icp_weights["location"] * 100
        
        # Tech stack matching
        target_tech = icp_definition.get("tech_stack", [])
        prospect_tech = prospect_data.get("tech_stack", [])
        if any(tech in prospect_tech for tech in target_tech) or not target_tech:
            score += self._icp_weights["tech_stack"] * 100
        
        # Growth signals
        growth_indicators = ["recent_funding", "hiring_spree", "expansion"]
        prospect_growth = prospect_data.get("growth_signals", [])
        if any(signal in prospect_growth for signal in growth_indicators):
            score += self._icp_weights["growth_signals"] * 100
        
        return int(score)

    def _calculate_intent_score(self, intent_signals: List[Dict[str, Any]]) -> int:
        """Calculate intent score based on signal strength and recency."""
        if not intent_signals:
            return 0
        
        score = 0
        now = datetime.now(timezone.utc)
        
        # Recency scoring
        recent_signals = 0
        for signal in intent_signals:
            signal_time = signal.get("timestamp")
            if signal_time:
                try:
                    if isinstance(signal_time, str):
                        signal_time = datetime.fromisoformat(signal_time)
                    hours_ago = (now - signal_time).total_seconds() / 3600
                    if hours_ago < 24:
                        recent_signals += 1
                except:
                    pass
        
        recency_score = min(100, (recent_signals / max(len(intent_signals), 1)) * 100)
        score += recency_score * self._intent_weights["recency"]
        
        # Signal strength
        strong_signals = sum(1 for s in intent_signals if s.get("strength") == "high")
        strength_score = min(100, (strong_signals / max(len(intent_signals), 1)) * 100)
        score += strength_score * self._intent_weights["signal_strength"]
        
        # Signal diversity
        signal_types = set(s.get("type") for s in intent_signals)
        diversity_score = min(100, (len(signal_types) / 5) * 100)  # Max score at 5 different types
        score += diversity_score * self._intent_weights["signal_diversity"]
        
        # Decision maker detection
        decision_makers = sum(1 for s in intent_signals if s.get("is_decision_maker", False))
        decision_score = min(100, (decision_makers / max(len(intent_signals), 1)) * 100)
        score += decision_score * self._intent_weights["decision_maker"]
        
        # Budget indicators
        budget_signals = sum(1 for s in intent_signals if s.get("indicates_budget", False))
        budget_score = min(100, (budget_signals / max(len(intent_signals), 1)) * 100)
        score += budget_score * self._intent_weights["budget_indicators"]
        
        return int(score)

    def _calculate_engagement_potential(self, prospect_data: Dict[str, Any]) -> int:
        """Calculate engagement potential based on prospect characteristics."""
        score = 0
        
        # Job seniority
        senior_roles = ["CEO", "CTO", "VP", "Director", "Head"]
        title = prospect_data.get("title", "")
        if any(role in title for role in senior_roles):
            score += 30
        
        # Company growth stage
        growth_stage = prospect_data.get("growth_stage", "")
        if growth_stage in ["growth", "expansion"]:
            score += 25
        elif growth_stage in ["startup", "early"]:
            score += 15
        
        # Recent activity
        recent_activity = prospect_data.get("recent_activity", False)
        if recent_activity:
            score += 20
        
        # Email responsiveness (if known)
        email_responsiveness = prospect_data.get("email_responsiveness", "unknown")
        if email_responsiveness == "high":
            score += 25
        elif email_responsiveness == "medium":
            score += 15
        
        return min(100, score)

    def _calculate_company_health(self, prospect_data: Dict[str, Any]) -> int:
        """Calculate company health score."""
        score = 0
        
        # Funding status
        funding = prospect_data.get("funding_status", "")
        if funding in ["series_a", "series_b", "series_c"]:
            score += 30
        elif funding in ["seed", "series_a"]:
            score += 20
        
        # Employee growth
        employee_growth = prospect_data.get("employee_growth_rate", 0)
        if employee_growth > 20:
            score += 25
        elif employee_growth > 10:
            score += 15
        
        # Revenue growth
        revenue_growth = prospect_data.get("revenue_growth_rate", 0)
        if revenue_growth > 30:
            score += 25
        elif revenue_growth > 15:
            score += 15
        
        # Market position
        market_position = prospect_data.get("market_position", "")
        if market_position in ["leader", "challenger"]:
            score += 20
        
        return min(100, score)

    def _determine_tier(self, overall_score: int, icp_score: int, intent_score: int) -> LeadTier:
        """Determine lead tier based on scores."""
        if overall_score >= 80 and icp_score >= 70 and intent_score >= 70:
            return LeadTier.HOT
        elif overall_score >= 60 and icp_score >= 50 and intent_score >= 50:
            return LeadTier.WARM
        elif overall_score >= 40:
            return LeadTier.COLD
        else:
            return LeadTier.UNQUALIFIED

    def _determine_priority(self, tier: LeadTier, overall_score: int) -> str:
        """Determine outreach priority."""
        if tier == LeadTier.HOT:
            return "high"
        elif tier == LeadTier.WARM and overall_score >= 70:
            return "high"
        elif tier == LeadTier.WARM:
            return "medium"
        elif tier == LeadTier.COLD and overall_score >= 50:
            return "medium"
        else:
            return "low"

    def _generate_recommendation(self, tier: LeadTier, overall_score: int) -> str:
        """Generate outreach recommendation."""
        if tier == LeadTier.HOT:
            return "Immediate outreach with personalized message, use all available channels"
        elif tier == LeadTier.WARM:
            return "Prioritize for outreach within 24-48 hours, start with email"
        elif tier == LeadTier.COLD:
            return "Add to nurture campaign, monitor for new intent signals"
        else:
            return "Disqualify or add to long-term nurture"

    def _get_matched_icp_criteria(
        self,
        prospect_data: Dict[str, Any],
        icp_definition: Dict[str, Any]
    ) -> List[str]:
        """Get list of ICP criteria that match the prospect."""
        matched = []
        
        if prospect_data.get("company_size") in icp_definition.get("company_sizes", []):
            matched.append("company_size")
        if prospect_data.get("industry") in icp_definition.get("industries", []):
            matched.append("industry")
        if icp_definition.get("min_revenue", 0) <= prospect_data.get("revenue", 0) <= icp_definition.get("max_revenue", float('inf')):
            matched.append("revenue")
        
        return matched

    def _count_recent_signals(self, intent_signals: List[Dict[str, Any]]) -> int:
        """Count signals from the last 7 days."""
        now = datetime.now(timezone.utc)
        recent_count = 0
        
        for signal in intent_signals:
            signal_time = signal.get("timestamp")
            if signal_time:
                try:
                    if isinstance(signal_time, str):
                        signal_time = datetime.fromisoformat(signal_time)
                    days_ago = (now - signal_time).total_seconds() / 86400
                    if days_ago < 7:
                        recent_count += 1
                except:
                    pass
        
        return recent_count


class LeadEnrichmentService:
    """Service for enriching lead data from multiple sources."""

    def __init__(self):
        self._scoring_engine = LeadScoringEngine()

    async def enrich_prospect(
        self,
        basic_data: Dict[str, Any],
        enrichment_sources: List[str] = None
    ) -> Dict[str, Any]:
        """Enrich prospect data from multiple sources."""
        if enrichment_sources is None:
            enrichment_sources = ["linkedin", "company", "technographic"]
        
        enriched_data = dict(basic_data)
        
        # LinkedIn enrichment
        if "linkedin" in enrichment_sources:
            linkedin_data = await self._enrich_from_linkedin(basic_data)
            enriched_data.update(linkedin_data)
        
        # Company data enrichment
        if "company" in enrichment_sources:
            company_data = await self._enrich_company_data(basic_data)
            enriched_data.update(company_data)
        
        # Technographic enrichment
        if "technographic" in enrichment_sources:
            tech_data = await self._enrich_technographic(basic_data)
            enriched_data.update(tech_data)
        
        return enriched_data

    async def _enrich_from_linkedin(self, basic_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich data from LinkedIn."""
        # Simulated LinkedIn enrichment
        return {
            "linkedin_url": basic_data.get("linkedin_url", ""),
            "linkedin_connections": basic_data.get("connections", 0),
            "linkedin_activity": "active",
            "company_linkedin_url": f"https://linkedin.com/company/{basic_data.get('company', '').lower().replace(' ', '-')}"
        }

    async def _enrich_company_data(self, basic_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich company data."""
        # Simulated company enrichment
        return {
            "company_size": basic_data.get("company_size", "11-50"),
            "industry": basic_data.get("industry", "Technology"),
            "revenue": basic_data.get("revenue", 1000000),
            "funding_status": basic_data.get("funding", "seed"),
            "employee_growth_rate": basic_data.get("growth_rate", 15),
            "founded_year": basic_data.get("founded", 2020)
        }

    async def _enrich_technographic(self, basic_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich technographic data."""
        # Simulated technographic enrichment
        return {
            "tech_stack": basic_data.get("tech_stack", ["React", "Node.js", "AWS"]),
            "crm_system": basic_data.get("crm", "Salesforce"),
            "marketing_tools": basic_data.get("marketing_stack", ["HubSpot", "Mailchimp"])
        }

    def score_enriched_lead(
        self,
        enriched_data: Dict[str, Any],
        icp_definition: Dict[str, Any],
        intent_signals: List[Dict[str, Any]]
    ) -> LeadScore:
        """Score an enriched lead using the scoring engine."""
        return self._scoring_engine.score_lead(enriched_data, icp_definition, intent_signals)
