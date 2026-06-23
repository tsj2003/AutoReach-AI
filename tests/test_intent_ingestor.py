from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from opentelemetry.sdk.trace import TracerProvider

from engine import Engagement, EventKind, open_storage
from engine.intent.ingestor import IntentProspectIngestor
from engine.intent.repository import DuckDBIntentRepository


def _seed_intent_db(tmp_path, rows):
    db_path = str(tmp_path / "intent.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute(
        """
        CREATE TABLE intent_signals (
            tenant_id VARCHAR,
            signal_type VARCHAR,
            company_domain VARCHAR,
            payload JSON,
            timestamp TIMESTAMP
        )
        """
    )
    for row in rows:
        conn.execute(
            """
            INSERT INTO intent_signals VALUES (?, ?, ?, ?, ?)
            """,
            [
                row["tenant_id"],
                row["signal_type"],
                row["company_domain"],
                row["payload"],
                row["timestamp"],
            ],
        )
    conn.close()
    return db_path


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path / 'engine.db'}")


def _save_engagement(store, *, tenant_id="t-123", engagement_id="eng-1", allowed=None):
    metadata = {}
    if allowed is not None:
        metadata = {"signal_matrix": {"allowed_signal_types": allowed}}
    engagement = Engagement(
        id=engagement_id,
        customer_name="ACME",
        offer="Offer",
        icp_description="ICP",
        metadata=metadata,
    )
    store.save_engagement(engagement, tenant_id=tenant_id)
    return engagement


def test_intent_ingestor_creates_account_prospect_for_allowed_signal_without_email(tmp_path, storage):
    store, events, _ = storage
    _save_engagement(store, allowed=["funding_round"])
    db_path = _seed_intent_db(
        tmp_path,
        [
            {
                "tenant_id": "t-123",
                "signal_type": "funding_round",
                "company_domain": "rich-company.com",
                "payload": '{"amount": 1000000, "company": "Rich Company"}',
                "timestamp": datetime.now(UTC).replace(tzinfo=None),
            }
        ],
    )

    result = IntentProspectIngestor(
        store=store,
        events=events,
        repository=DuckDBIntentRepository(db_path=db_path),
    ).ingest_campaign(tenant_id="t-123", engagement_id="eng-1")

    assert result.created_count == 1
    prospect = store.get_prospect(result.created_prospect_ids[0])
    assert prospect is not None
    assert prospect.email is None
    assert prospect.company == "Rich Company"
    assert prospect.raw["intent_signal"]["signal_type"] == "funding_round"
    assert prospect.research["matched_intent_signal"]["company_domain"] == "rich-company.com"


def test_intent_ingestor_skips_disallowed_signal_types(tmp_path, storage):
    store, events, _ = storage
    _save_engagement(store, allowed=["funding_round"])
    db_path = _seed_intent_db(
        tmp_path,
        [
            {
                "tenant_id": "t-123",
                "signal_type": "tech_stack_change",
                "company_domain": "stack-change.com",
                "payload": '{"added": "kafka"}',
                "timestamp": datetime.now(UTC).replace(tzinfo=None),
            }
        ],
    )

    result = IntentProspectIngestor(
        store=store,
        events=events,
        repository=DuckDBIntentRepository(db_path=db_path),
    ).ingest_campaign(tenant_id="t-123", engagement_id="eng-1")

    assert result.created_count == 0
    assert result.skipped_count == 0
    assert list(store.list_prospects("eng-1")) == []


def test_intent_ingestor_fails_closed_without_signal_matrix(tmp_path, storage):
    store, events, _ = storage
    _save_engagement(store, allowed=None)
    db_path = _seed_intent_db(
        tmp_path,
        [
            {
                "tenant_id": "t-123",
                "signal_type": "funding_round",
                "company_domain": "silent.com",
                "payload": '{"email": "buyer@silent.com"}',
                "timestamp": datetime.now(UTC).replace(tzinfo=None),
            }
        ],
    )

    result = IntentProspectIngestor(
        store=store,
        events=events,
        repository=DuckDBIntentRepository(db_path=db_path),
    ).ingest_campaign(tenant_id="t-123", engagement_id="eng-1")

    assert result.created_count == 0
    assert list(store.list_prospects("eng-1")) == []


def test_intent_ingestor_is_idempotent_for_same_signal(tmp_path, storage):
    store, events, _ = storage
    _save_engagement(store, allowed=["funding_round"])
    now = datetime.now(UTC).replace(tzinfo=None)
    db_path = _seed_intent_db(
        tmp_path,
        [
            {
                "tenant_id": "t-123",
                "signal_type": "funding_round",
                "company_domain": "repeat.com",
                "payload": '{"contact_email": "founder@repeat.com"}',
                "timestamp": now,
            }
        ],
    )
    ingestor = IntentProspectIngestor(
        store=store,
        events=events,
        repository=DuckDBIntentRepository(db_path=db_path),
    )

    first = ingestor.ingest_campaign(tenant_id="t-123", engagement_id="eng-1")
    second = ingestor.ingest_campaign(tenant_id="t-123", engagement_id="eng-1")

    assert first.created_count == 1
    assert second.created_count == 0
    assert second.skipped_count == 1
    assert len(list(store.list_prospects("eng-1"))) == 1


def test_intent_ingestor_refuses_cross_tenant_engagement(tmp_path, storage):
    store, events, _ = storage
    _save_engagement(store, tenant_id="tenant-a", allowed=["funding_round"])
    db_path = _seed_intent_db(tmp_path, [])

    with pytest.raises(PermissionError):
        IntentProspectIngestor(
            store=store,
            events=events,
            repository=DuckDBIntentRepository(db_path=db_path),
        ).ingest_campaign(tenant_id="tenant-b", engagement_id="eng-1")


def test_intent_ingestor_stamps_trace_id_on_prospect_and_event(tmp_path, storage):
    store, events, _ = storage
    _save_engagement(store, allowed=["funding_round"])
    db_path = _seed_intent_db(
        tmp_path,
        [
            {
                "tenant_id": "t-123",
                "signal_type": "funding_round",
                "company_domain": "trace.com",
                "payload": '{"email": "cto@trace.com"}',
                "timestamp": datetime.now(UTC).replace(tzinfo=None),
            }
        ],
    )
    provider = TracerProvider()

    with patch("engine.intent.ingestor.trace.get_tracer", return_value=provider.get_tracer("test")):
        result = IntentProspectIngestor(
            store=store,
            events=events,
            repository=DuckDBIntentRepository(db_path=db_path),
        ).ingest_campaign(tenant_id="t-123", engagement_id="eng-1")

    prospect = store.get_prospect(result.created_prospect_ids[0])
    recent_events = list(events.list_recent(engagement_id="eng-1", kind=EventKind.INTENT_PROSPECT_CREATED.value))
    assert prospect.raw["intent_signal"]["openinference_trace_id"] == result.openinference_trace_id
    assert recent_events[0].payload["openinference_trace_id"] == result.openinference_trace_id


def test_intent_ingest_campaign_celery_task_passes_tenant_scope(monkeypatch):
    import importlib

    celery_module = importlib.import_module("engine.worker.celery_app")
    intent_ingest_campaign = celery_module.intent_ingest_campaign

    store = object()
    events = object()
    repo = object()
    result = MagicMock()
    result.model_dump.return_value = {"created_count": 1}
    ingestor = MagicMock()
    ingestor.ingest_campaign.return_value = result

    monkeypatch.setenv("AUTOREACH_INTENT_DUCKDB_PATH", "/tmp/intent.duckdb")
    monkeypatch.setenv("AUTOREACH_INTENT_HOURS_BACK", "48")
    monkeypatch.setattr(celery_module, "_build_runtime", lambda: (None, store, events, None))
    with patch("engine.intent.repository.DuckDBIntentRepository", return_value=repo) as mock_repo:
        with patch("engine.intent.ingestor.IntentProspectIngestor", return_value=ingestor) as mock_ingestor:
            output = intent_ingest_campaign.run(
                tenant_id="t-scope",
                engagement_id="eng-scope",
            )

    mock_repo.assert_called_once_with(db_path="/tmp/intent.duckdb")
    mock_ingestor.assert_called_once_with(store=store, events=events, repository=repo)
    ingestor.ingest_campaign.assert_called_once_with(
        tenant_id="t-scope",
        engagement_id="eng-scope",
        hours_back=48,
    )
    assert output == {"created_count": 1}
