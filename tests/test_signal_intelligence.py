"""Tests for Attainly Signal Intelligence platform (Phase 2 foundation)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from engine import Engagement, open_storage
from engine.intent.ingestor import IntentProspectIngestor
from engine.signals.bridge import StoreIntentRepository
from engine.signals.connectors.manual import ManualSignalConnector
from engine.signals.dedup import canonical_signal_id
from engine.signals.ingestion import SignalIngestionService
from engine.signals.registry import get_signal_registry
from engine.signals.repository import SignalRepository
from engine.signals.scoring import ProspectPriorityScorer


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path / 'engine.db'}")


def _signal_repo(storage) -> SignalRepository:
    store, _, _ = storage
    return SignalRepository(store._holder.engine)


def _save_engagement(store, *, tenant_id="t-1", engagement_id="eng-1", allowed=None):
    metadata = {}
    if allowed is not None:
        metadata = {"signal_matrix": {"allowed_signal_types": allowed}}
    engagement = Engagement(
        id=engagement_id,
        customer_name="ACME",
        offer="Offer",
        icp_description="SaaS founders",
        metadata=metadata,
    )
    store.save_engagement(engagement, tenant_id=tenant_id)
    return engagement


class TestSignalRegistry:
    def test_registry_has_eighteen_quality_types_not_inflated(self):
        registry = get_signal_registry()
        keys = registry.list_keys()
        assert len(keys) == 18
        assert "funding_round" in keys
        assert "hiring_surge" in keys

    def test_normalize_aliases(self):
        registry = get_signal_registry()
        assert registry.normalize("funding") == "funding_round"
        assert registry.normalize("tech_adoption") == "technology_adoption"
        assert registry.normalize("unknown_signal_xyz") is None

    def test_catalog_for_api_is_honest(self):
        catalog = get_signal_registry().catalog_for_api()
        assert catalog["version"] == "1.0.0"
        assert catalog["count"] == len(catalog["types"])
        assert all("label" in t for t in catalog["types"])


class TestManualConnectorAndIngestion:
    def test_manual_connector_rejects_unknown_signal_type(self):
        connector = ManualSignalConnector(source_id="src-manual")
        event = connector.normalize_payload(
            tenant_id="t-1",
            payload={"signal_type": "made_up_signal", "company_domain": "acme.com"},
        )
        assert event is None

    def test_ingestion_persists_and_deduplicates(self, storage):
        repo = _signal_repo(storage)
        service = SignalIngestionService(repository=repo)
        connector = ManualSignalConnector(source_id="src-manual")
        repo.save_source(
            source_id="src-manual",
            tenant_id="t-1",
            connector_kind="manual",
            name="Manual",
        )
        payloads = [
            {
                "signal_type": "funding_round",
                "company_domain": "acme.com",
                "company_name": "Acme Inc",
                "evidence": {"summary": "Series B announced", "source_url": "https://example.com/news"},
            }
        ]
        result = service.ingest_manual_payloads(
            tenant_id="t-1",
            source_id="src-manual",
            connector=connector,
            payloads=payloads,
        )
        assert result.events_inserted == 1
        assert result.events_rejected == 0

        # Duplicate ingest — same payload should dedupe
        result2 = service.ingest_manual_payloads(
            tenant_id="t-1",
            source_id="src-manual",
            connector=connector,
            payloads=payloads,
        )
        assert result2.events_inserted == 0
        assert result2.events_deduplicated == 1

    def test_tenant_isolation_on_signals(self, storage):
        repo = _signal_repo(storage)
        service = SignalIngestionService(repository=repo)
        connector = ManualSignalConnector(source_id="src-a")
        payloads = [{"signal_type": "funding_round", "company_domain": "a.com"}]

        service.ingest_manual_payloads(
            tenant_id="tenant-a", source_id="src-a", connector=connector, payloads=payloads,
        )

        signals_b = repo.list_recent_as_intent_signals(
            tenant_id="tenant-b", hours_back=24, signal_types=["funding_round"],
        )
        assert signals_b == []


class TestCrossTenantSourceSecurity:
    def test_cross_tenant_source_save_rejected(self, storage):
        repo = _signal_repo(storage)
        repo.save_source(
            source_id="src-x", tenant_id="tenant-a", connector_kind="manual", name="A",
        )
        with pytest.raises(PermissionError):
            repo.save_source(
                source_id="src-x", tenant_id="tenant-b", connector_kind="manual", name="B",
            )


class TestBridgeToIntentIngestor:
    def test_persisted_signals_create_prospects_via_ingestor(self, storage):
        store, events, _ = storage
        repo = _signal_repo(storage)
        service = SignalIngestionService(repository=repo)
        connector = ManualSignalConnector(source_id="src-manual")

        _save_engagement(store, allowed=["funding_round"])

        service.ingest_manual_payloads(
            tenant_id="t-1",
            source_id="src-manual",
            connector=connector,
            payloads=[
                {
                    "signal_type": "funding_round",
                    "company_domain": "rich-co.com",
                    "company_name": "Rich Co",
                    "evidence": {"summary": "Raised $10M Series B"},
                }
            ],
        )

        bridge_repo = StoreIntentRepository(repository=repo)
        result = IntentProspectIngestor(
            store=store, events=events, repository=bridge_repo,
        ).ingest_campaign(tenant_id="t-1", engagement_id="eng-1")

        assert result.created_count == 1
        prospect = store.get_prospect(result.created_prospect_ids[0])
        assert prospect is not None
        assert prospect.company == "Rich Co"
        assert prospect.research["signal_stack"]["depth"] == 1


class TestProspectPriorityScorer:
    def test_scoring_is_explainable_not_random(self):
        from engine.intent.models import IntentSignal
        from engine.intent.signal_stack import SignalStackPolicy

        now = datetime.now(UTC)
        signals = [
            IntentSignal(
                tenant_id="t-1",
                signal_type="funding_round",
                company_domain="acme.com",
                payload={"summary": "Series B for SaaS platform"},
                timestamp=now,
            ),
            IntentSignal(
                tenant_id="t-1",
                signal_type="hiring_surge",
                company_domain="acme.com",
                payload={"summary": "Hiring 5 engineers"},
                timestamp=now,
            ),
        ]
        stack = SignalStackPolicy(min_stack=2).evaluate(signals)
        score = ProspectPriorityScorer().score_account(
            stack=stack,
            icp_keywords=["saas", "platform"],
        )
        assert 0 < score.score <= 100
        assert len(score.factors) >= 2
        assert all(f.points > 0 for f in score.factors)
        assert "signal stack" in score.as_dict()["explanation"]

    def test_unqualified_stack_scores_zero(self):
        from engine.intent.models import IntentSignal
        from engine.intent.signal_stack import SignalStackPolicy

        signals = [
            IntentSignal(
                tenant_id="t-1",
                signal_type="funding_round",
                company_domain="acme.com",
                payload={},
                timestamp=datetime.now(UTC),
            ),
        ]
        stack = SignalStackPolicy(min_stack=2).evaluate(signals)
        score = ProspectPriorityScorer().score_account(stack=stack)
        assert score.score == 0


class TestDeduplication:
    def test_canonical_id_is_deterministic(self):
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        a = canonical_signal_id(
            tenant_id="t-1",
            signal_type="funding_round",
            company_domain="acme.com",
            entity_type="company",
            entity_id=None,
            occurred_at=ts,
        )
        b = canonical_signal_id(
            tenant_id="t-1",
            signal_type="funding_round",
            company_domain="acme.com",
            entity_type="company",
            entity_id=None,
            occurred_at=ts,
        )
        assert a == b
        assert a.startswith("cs_")
