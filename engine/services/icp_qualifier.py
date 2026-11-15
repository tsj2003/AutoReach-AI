"""Enhanced ICP-based lead qualification system.

This implements Gojiberry-style ICP analysis:
- Dynamic ICP refinement based on conversion data
- Real-time ICP scoring
- Industry-specific ICP templates
- Company size and growth stage analysis
- Technographic matching
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class CompanySize(Enum):
    """Company size categories."""
    MICRO = "1-10"
    SMALL = "11-50"
    MEDIUM = "51-200"
    LARGE = "201-500"
    ENTERPRISE = "501-1000"
    LARGE_ENTERPRISE = "1000+"


class GrowthStage(Enum):
    """Company growth stages."""
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    SERIES_C = "series_c"
    GROWTH = "growth"
    MATURE = "mature"


@dataclass
class ICPDefinition:
    """Comprehensive ICP definition."""
    name: str
    industries: List[str]
    company_sizes: List[CompanySize]
    growth_stages: List[GrowthStage]
    job_functions: List[str]
    seniority_levels: List[str]
    geographies: List[str]
    tech_stack: List[str]
    business_models: List[str]
    min_revenue: Optional[int] = None
    max_revenue: Optional[int] = None
    min_employee_count: Optional[int] = None
    max_employee_count: Optional[int] = None
    custom_criteria: Dict[str, Any] = None


@dataclass
class ICPMatchResult:
    """Result of ICP matching for a prospect."""
    prospect_id: str
    icp_name: str
    match_score: float  # 0-1
    matched_criteria: List[str]
    missing_criteria: List[str]
    disqualifying_factors: List[str]
    recommendation: str
    priority: str  # "high", "medium", "low"


class DynamicICPQualifier:
    """Dynamic ICP qualifier that learns and refines ICP definitions."""

    def __init__(self):
        self._icp_definitions: Dict[str, ICPDefinition] = {}
        self._conversion_data: List[Dict[str, Any]] = []
        self._industry_templates: Dict[str, Dict[str, Any]] = {}
        self._initialize_industry_templates()

    def _initialize_industry_templates(self) -> None:
        """Initialize industry-specific ICP templates."""
        self._industry_templates = {
            "technology": {
                "industries": ["Software", "SaaS", "Technology", "IT Services"],
                "company_sizes": [CompanySize.SMALL, CompanySize.MEDIUM, CompanySize.LARGE],
                "growth_stages": [GrowthStage.SEED, GrowthStage.SERIES_A, GrowthStage.SERIES_B],
                "job_functions": ["Engineering", "Product", "CTO", "VP Engineering", "Technology"],
                "tech_stack": ["AWS", "Azure", "GCP", "React", "Node.js", "Python", "Kubernetes"],
                "business_models": ["B2B SaaS", "Platform", "Marketplace"]
            },
            "healthcare": {
                "industries": ["Healthcare", "Health Tech", "Medical Devices", "Pharmaceutical"],
                "company_sizes": [CompanySize.MEDIUM, CompanySize.LARGE, CompanySize.ENTERPRISE],
                "growth_stages": [GrowthStage.SERIES_A, GrowthStage.SERIES_B, GrowthStage.SERIES_C],
                "job_functions": ["CMO", "VP Marketing", "Chief Medical Officer", "Healthcare IT"],
                "tech_stack": ["HIPAA compliant", "EHR systems", "Health Cloud"],
                "business_models": ["B2B", "Enterprise", "Compliance solutions"]
            },
            "finance": {
                "industries": ["Financial Services", "FinTech", "Banking", "Insurance"],
                "company_sizes": [CompanySize.LARGE, CompanySize.ENTERPRISE, CompanySize.LARGE_ENTERPRISE],
                "growth_stages": [GrowthStage.SERIES_B, GrowthStage.SERIES_C, GrowthStage.GROWTH],
                "job_functions": ["CFO", "VP Finance", "Risk Management", "Compliance"],
                "tech_stack": ["Core banking", "Blockchain", "Security", "Compliance tools"],
                "business_models": ["B2B", "Enterprise", "Regulated"]
            },
            "retail": {
                "industries": ["Retail", "E-commerce", "Consumer Goods"],
                "company_sizes": [CompanySize.SMALL, CompanySize.MEDIUM, CompanySize.LARGE],
                "growth_stages": [GrowthStage.SEED, GrowthStage.SERIES_A, GrowthStage.SERIES_B],
                "job_functions": ["CMO", "VP Marketing", "E-commerce", "Operations"],
                "tech_stack": ["Shopify", "Magento", "Analytics", "CRM"],
                "business_models": ["B2C", "B2B", "Marketplace"]
            }
        }

    def create_icp_definition(
        self,
        name: str,
        industry: str,
        base_criteria: Dict[str, Any]
    ) -> ICPDefinition:
        """Create an ICP definition from industry template and custom criteria."""
        template = self._industry_templates.get(industry.lower(), {})
        
        icp = ICPDefinition(
            name=name,
            industries=base_criteria.get("industries", template.get("industries", [])),
            company_sizes=[
                CompanySize(size) for size in base_criteria.get("company_sizes", template.get("company_sizes", []))
            ],
            growth_stages=[
                GrowthStage(stage) for stage in base_criteria.get("growth_stages", template.get("growth_stages", []))
            ],
            job_functions=base_criteria.get("job_functions", template.get("job_functions", [])),
            seniority_levels=base_criteria.get("seniority_levels", ["Director", "VP", "C-level"]),
            geographies=base_criteria.get("geographies", []),
            tech_stack=base_criteria.get("tech_stack", template.get("tech_stack", [])),
            business_models=base_criteria.get("business_models", template.get("business_models", [])),
            min_revenue=base_criteria.get("min_revenue"),
            max_revenue=base_criteria.get("max_revenue"),
            min_employee_count=base_criteria.get("min_employee_count"),
            max_employee_count=base_criteria.get("max_employee_count"),
            custom_criteria=base_criteria.get("custom_criteria", {})
        )
        
        self._icp_definitions[name] = icp
        logger.info(f"Created ICP definition: {name}")
        
        return icp

    def qualify_prospect(
        self,
        prospect_data: Dict[str, Any],
        icp_name: str
    ) -> ICPMatchResult:
        """Qualify a prospect against an ICP definition."""
        if icp_name not in self._icp_definitions:
            logger.warning(f"ICP definition {icp_name} not found")
            return ICPMatchResult(
                prospect_id=prospect_data.get("id", ""),
                icp_name=icp_name,
                match_score=0.0,
                matched_criteria=[],
                missing_criteria=[],
                disqualifying_factors=["ICP definition not found"],
                recommendation="Cannot qualify - ICP not defined",
                priority="low"
            )
        
        icp = self._icp_definitions[icp_name]
        
        matched_criteria = []
        missing_criteria = []
        disqualifying_factors = []
        
        # Check industry match
        if prospect_data.get("industry") in icp.industries:
            matched_criteria.append("industry")
        else:
            missing_criteria.append("industry")
        
        # Check company size match
        prospect_size = self._map_company_size(prospect_data.get("company_size"))
        if prospect_size in icp.company_sizes:
            matched_criteria.append("company_size")
        else:
            missing_criteria.append("company_size")
        
        # Check growth stage match
        prospect_stage = self._map_growth_stage(prospect_data.get("growth_stage"))
        if prospect_stage in icp.growth_stages:
            matched_criteria.append("growth_stage")
        else:
            missing_criteria.append("growth_stage")
        
        # Check job function match
        if any(func in prospect_data.get("title", "") for func in icp.job_functions):
            matched_criteria.append("job_function")
        else:
            missing_criteria.append("job_function")
        
        # Check seniority match
        if any(level in prospect_data.get("title", "") for level in icp.seniority_levels):
            matched_criteria.append("seniority")
        else:
            missing_criteria.append("seniority")
        
        # Check geography match
        if not icp.geographies or prospect_data.get("location") in icp.geographies:
            matched_criteria.append("geography")
        else:
            missing_criteria.append("geography")
        
        # Check tech stack match
        if not icp.tech_stack or any(tech in prospect_data.get("tech_stack", []) for tech in icp.tech_stack):
            matched_criteria.append("tech_stack")
        else:
            missing_criteria.append("tech_stack")
        
        # Check revenue range
        if icp.min_revenue and icp.max_revenue:
            revenue = prospect_data.get("revenue", 0)
            if icp.min_revenue <= revenue <= icp.max_revenue:
                matched_criteria.append("revenue")
            else:
                disqualifying_factors.append("revenue_out_of_range")
        
        # Check employee count range
        if icp.min_employee_count and icp.max_employee_count:
            employees = prospect_data.get("employee_count", 0)
            if icp.min_employee_count <= employees <= icp.max_employee_count:
                matched_criteria.append("employee_count")
            else:
                disqualifying_factors.append("employee_count_out_of_range")
        
        # Calculate match score
        total_criteria = 8  # industry, company_size, growth_stage, job_function, seniority, geography, tech_stack, revenue/employees
        match_score = len(matched_criteria) / total_criteria
        
        # Check for disqualifying factors
        if disqualifying_factors:
            match_score *= 0.5  # Penalty for disqualifying factors
        
        # Generate recommendation
        if match_score >= 0.8:
            recommendation = "Strong fit - prioritize immediately"
            priority = "high"
        elif match_score >= 0.6:
            recommendation = "Good fit - include in campaign"
            priority = "medium"
        elif match_score >= 0.4:
            recommendation = "Moderate fit - consider with additional research"
            priority = "medium"
        else:
            recommendation = "Poor fit - exclude or nurture"
            priority = "low"
        
        return ICPMatchResult(
            prospect_id=prospect_data.get("id", ""),
            icp_name=icp_name,
            match_score=match_score,
            matched_criteria=matched_criteria,
            missing_criteria=missing_criteria,
            disqualifying_factors=disqualifying_factors,
            recommendation=recommendation,
            priority=priority
        )

    def _map_company_size(self, size_str: str) -> Optional[CompanySize]:
        """Map company size string to enum."""
        size_mapping = {
            "1-10": CompanySize.MICRO,
            "11-50": CompanySize.SMALL,
            "51-200": CompanySize.MEDIUM,
            "201-500": CompanySize.LARGE,
            "501-1000": CompanySize.ENTERPRISE,
            "1000+": CompanySize.LARGE_ENTERPRISE
        }
        return size_mapping.get(size_str)

    def _map_growth_stage(self, stage_str: str) -> Optional[GrowthStage]:
        """Map growth stage string to enum."""
        stage_mapping = {
            "pre_seed": GrowthStage.PRE_SEED,
            "seed": GrowthStage.SEED,
            "series_a": GrowthStage.SERIES_A,
            "series_b": GrowthStage.SERIES_B,
            "series_c": GrowthStage.SERIES_C,
            "growth": GrowthStage.GROWTH,
            "mature": GrowthStage.MATURE
        }
        return stage_mapping.get(stage_str.lower() if stage_str else "")

    def refine_icp_from_conversions(
        self,
        icp_name: str,
        conversion_data: List[Dict[str, Any]]
    ) -> ICPDefinition:
        """Refine ICP definition based on successful conversions."""
        if icp_name not in self._icp_definitions:
            logger.warning(f"Cannot refine non-existent ICP: {icp_name}")
            return self._icp_definitions.get(icp_name)
        
        icp = self._icp_definitions[icp_name]
        
        # Analyze common characteristics in conversions
        common_industries = self._get_most_common(conversion_data, "industry")
        common_sizes = self._get_most_common(conversion_data, "company_size")
        common_stages = self._get_most_common(conversion_data, "growth_stage")
        
        # Update ICP with successful patterns
        if common_industries:
            icp.industries = list(set(icp.industries + common_industries))
        
        if common_sizes:
            icp.company_sizes = [
                CompanySize(size) for size in common_sizes
                if self._map_company_size(size) in CompanySize
            ]
        
        if common_stages:
            icp.growth_stages = [
                GrowthStage(stage) for stage in common_stages
                if self._map_growth_stage(stage) in GrowthStage
            ]
        
        logger.info(f"Refined ICP {icp_name} based on {len(conversion_data)} conversions")
        
        return icp

    def _get_most_common(self, data: List[Dict[str, Any]], field: str) -> List[str]:
        """Get most common values for a field from conversion data."""
        values = [item.get(field) for item in data if item.get(field)]
        if not values:
            return []
        
        from collections import Counter
        counter = Counter(values)
        
        # Return top 3 most common
        return [item for item, count in counter.most_common(3)]

    def get_icp_suggestions(
        self,
        prospect_data: Dict[str, Any]
    ) -> List[ICPMatchResult]:
        """Get ICP match results for all defined ICPs."""
        results = []
        
        for icp_name in self._icp_definitions:
            result = self.qualify_prospect(prospect_data, icp_name)
            results.append(result)
        
        # Sort by match score
        results.sort(key=lambda x: x.match_score, reverse=True)
        
        return results

    def auto_create_icp_from_campaign(
        self,
        campaign_name: str,
        industry: str,
        successful_prospects: List[Dict[str, Any]]
    ) -> ICPDefinition:
        """Automatically create an ICP definition from successful campaign prospects."""
        # Analyze successful prospects to find patterns
        common_criteria = {
            "industries": self._get_most_common(successful_prospects, "industry"),
            "company_sizes": self._get_most_common(successful_prospects, "company_size"),
            "growth_stages": self._get_most_common(successful_prospects, "growth_stage"),
            "job_functions": self._extract_job_functions(successful_prospects)
        }
        
        icp_name = f"{campaign_name}_auto_icp"
        icp = self.create_icp_definition(icp_name, industry, common_criteria)
        
        logger.info(f"Auto-created ICP {icp_name} from {len(successful_prospects)} successful prospects")
        
        return icp

    def _extract_job_functions(self, prospects: List[Dict[str, Any]]) -> List[str]:
        """Extract common job functions from prospect titles."""
        job_functions = []
        
        for prospect in prospects:
            title = prospect.get("title", "")
            # Simple keyword extraction from titles
            if "CEO" in title or "Chief" in title:
                job_functions.append("C-level")
            elif "VP" in title or "Vice President" in title:
                job_functions.append("VP")
            elif "Director" in title:
                job_functions.append("Director")
            elif "Manager" in title:
                job_functions.append("Manager")
        
        return list(set(job_functions))
