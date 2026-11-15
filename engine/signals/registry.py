"""Versioned SignalType registry — canonical taxonomy for Attainly Signal Intelligence.

Do NOT hard-code marketing counts like "30+ signals". This registry lists only
signal types Attainly understands and can enforce via campaign signal_matrix.
Connectors may emit additional raw types; unknown types are rejected at ingest.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


REGISTRY_VERSION = "1.0.0"


class SignalCategory(str, Enum):
    COMPANY_EVENT = "company_event"
    HIRING = "hiring"
    CONTENT_ACTIVITY = "content_activity"
    COMPETITIVE = "competitive"
    TECHNOLOGY = "technology"
    WEBSITE_PRODUCT = "website_product"


@dataclass(frozen=True)
class SignalTypeDefinition:
    """One supported signal type in the Attainly registry."""

    key: str
    category: SignalCategory
    label: str
    description: str
    aliases: frozenset[str] = frozenset()
    default_freshness_hours: int = 336  # 14 days


# Quality-first catalog — 17 well-defined types, not inflated marketing numbers.
_SIGNAL_TYPES: tuple[SignalTypeDefinition, ...] = (
    # Company events
    SignalTypeDefinition(
        key="funding_round",
        category=SignalCategory.COMPANY_EVENT,
        label="Funding round",
        description="Company announced or closed a funding round.",
        aliases=frozenset({"funding", "funding_announcement", "recent_funding_event"}),
        default_freshness_hours=336,
    ),
    SignalTypeDefinition(
        key="acquisition",
        category=SignalCategory.COMPANY_EVENT,
        label="Acquisition",
        description="Company acquired or was acquired.",
        default_freshness_hours=720,
    ),
    SignalTypeDefinition(
        key="leadership_change",
        category=SignalCategory.COMPANY_EVENT,
        label="Leadership change",
        description="Executive hire, departure, or role change.",
        aliases=frozenset({
            "executive_hire",
            "executive_departure",
            "recently_changed_job",
            "job_change",
            "champion_moved",
        }),
        default_freshness_hours=720,
    ),
    SignalTypeDefinition(
        key="product_launch",
        category=SignalCategory.COMPANY_EVENT,
        label="Product launch",
        description="New product or major feature launch.",
        aliases=frozenset({"website_visitor", "pricing_page_visit", "high_intent_page_visit"}),
        default_freshness_hours=336,
    ),
    SignalTypeDefinition(
        key="geographic_expansion",
        category=SignalCategory.COMPANY_EVENT,
        label="Geographic expansion",
        description="New market, office, or regional expansion.",
        aliases=frozenset({"new_office"}),
        default_freshness_hours=720,
    ),
    SignalTypeDefinition(
        key="major_partnership",
        category=SignalCategory.COMPANY_EVENT,
        label="Major partnership",
        description="Strategic partnership or alliance announced.",
        default_freshness_hours=720,
    ),
    # Hiring
    SignalTypeDefinition(
        key="hiring_surge",
        category=SignalCategory.HIRING,
        label="Hiring surge",
        description="Sudden increase in relevant hiring activity.",
        aliases=frozenset({"hiring", "hiring_acceleration"}),
        default_freshness_hours=336,
    ),
    SignalTypeDefinition(
        key="job_posting",
        category=SignalCategory.HIRING,
        label="Relevant job posting",
        description="Open role matching campaign ICP or cure.",
        default_freshness_hours=336,
    ),
    SignalTypeDefinition(
        key="senior_role_opening",
        category=SignalCategory.HIRING,
        label="Senior role opening",
        description="VP/C-level or senior IC role posted.",
        aliases=frozenset({"new_decision_maker"}),
        default_freshness_hours=336,
    ),
    SignalTypeDefinition(
        key="sales_hiring",
        category=SignalCategory.HIRING,
        label="Sales hiring",
        description="Sales or revenue team hiring activity.",
        default_freshness_hours=336,
    ),
    SignalTypeDefinition(
        key="engineering_hiring",
        category=SignalCategory.HIRING,
        label="Engineering hiring",
        description="Engineering or product engineering hiring.",
        default_freshness_hours=336,
    ),
    # Content / public activity
    SignalTypeDefinition(
        key="relevant_public_post",
        category=SignalCategory.CONTENT_ACTIVITY,
        label="Relevant public post",
        description="Public post indicating a relevant need or topic.",
        aliases=frozenset({
            "influencer_page_url",
            "your_profile",
            "visited_profile",
            "recent_activity",
            "linkedin_post_engagement",
        }),
        default_freshness_hours=168,
    ),
    SignalTypeDefinition(
        key="problem_discussion",
        category=SignalCategory.CONTENT_ACTIVITY,
        label="Problem-related discussion",
        description="Public discussion of a problem the offer addresses.",
        aliases=frozenset({"search_keyword", "keyword_intent"}),
        default_freshness_hours=168,
    ),
    SignalTypeDefinition(
        key="event_participation",
        category=SignalCategory.CONTENT_ACTIVITY,
        label="Event participation",
        description="Webinar, conference, or industry event participation.",
        aliases=frozenset({"webinar_participation"}),
        default_freshness_hours=336,
    ),
    # Competitive / market
    SignalTypeDefinition(
        key="competitor_engagement",
        category=SignalCategory.COMPETITIVE,
        label="Competitor engagement",
        description="Prospect engaged with a competitor publicly.",
        aliases=frozenset({
            "competitor_page_url",
            "your_company",
            "your_company_followers",
        }),
        default_freshness_hours=168,
    ),
    SignalTypeDefinition(
        key="technology_migration",
        category=SignalCategory.COMPETITIVE,
        label="Technology migration",
        description="Signals of stack change or migration intent.",
        aliases=frozenset({"tech_stack_change", "migration_intent"}),
        default_freshness_hours=720,
    ),
    # Technology / firmographic
    SignalTypeDefinition(
        key="technology_adoption",
        category=SignalCategory.TECHNOLOGY,
        label="Technology adoption",
        description="Adoption of a relevant technology or platform.",
        aliases=frozenset({"tech_adoption", "tech_stack_change", "technology"}),
        default_freshness_hours=720,
    ),
    SignalTypeDefinition(
        key="employee_growth",
        category=SignalCategory.TECHNOLOGY,
        label="Employee growth",
        description="Material headcount or department growth signal.",
        aliases=frozenset({"lookalike", "lookalike_match"}),
        default_freshness_hours=720,
    ),
)


class SignalTypeRegistry:
    """Lookup and normalize signal types against the versioned registry."""

    def __init__(self, definitions: Iterable[SignalTypeDefinition] = _SIGNAL_TYPES) -> None:
        self.version = REGISTRY_VERSION
        self._by_key: dict[str, SignalTypeDefinition] = {}
        self._alias_to_key: dict[str, str] = {}
        for definition in definitions:
            self._by_key[definition.key] = definition
            for alias in definition.aliases:
                self._alias_to_key[alias] = definition.key

    def normalize(self, raw_type: str) -> str | None:
        """Return canonical registry key or None if unknown."""

        cleaned = raw_type.strip().lower().replace("-", "_").replace(" ", "_")
        if not cleaned:
            return None
        if cleaned in self._by_key:
            return cleaned
        return self._alias_to_key.get(cleaned)

    def is_known(self, raw_type: str) -> bool:
        return self.normalize(raw_type) is not None

    def get(self, key: str) -> SignalTypeDefinition | None:
        canonical = self.normalize(key)
        if canonical is None:
            return None
        return self._by_key.get(canonical)

    def list_types(self) -> list[SignalTypeDefinition]:
        return list(self._by_key.values())

    def list_keys(self) -> list[str]:
        return sorted(self._by_key.keys())

    def catalog_for_api(self) -> dict:
        """Tenant-safe catalog payload for API/UI."""

        return {
            "version": self.version,
            "count": len(self._by_key),
            "types": [
                {
                    "key": d.key,
                    "category": d.category.value,
                    "label": d.label,
                    "description": d.description,
                    "default_freshness_hours": d.default_freshness_hours,
                    "aliases": sorted(d.aliases),
                }
                for d in sorted(self._by_key.values(), key=lambda x: x.key)
            ],
        }


_registry: SignalTypeRegistry | None = None


def get_signal_registry() -> SignalTypeRegistry:
    global _registry
    if _registry is None:
        _registry = SignalTypeRegistry()
    return _registry
