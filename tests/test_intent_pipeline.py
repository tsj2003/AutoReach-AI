from datetime import datetime
from unittest.mock import AsyncMock, patch

import duckdb
import pytest

from engine.intent.models import IntentSignal
from engine.intent.publisher import RedpandaPublisher
from engine.intent.repository import DuckDBIntentRepository


def test_intent_signal_schema_validation():
    """Forces Cursor to build a strict Pydantic model for incoming signals."""
    signal = IntentSignal(
        tenant_id="t-123",
        signal_type="funding_round",
        company_domain="acme.com",
        payload={"amount_raised": 50000000, "round": "Series B"},
        timestamp=datetime.utcnow(),
    )
    assert signal.signal_type == "funding_round"
    assert signal.company_domain == "acme.com"


@pytest.mark.asyncio
@patch("engine.intent.publisher.AIOKafkaProducer")
async def test_redpanda_publisher_sends_to_topic(mock_producer_class):
    """Forces Cursor to implement the Redpanda/Kafka publisher cleanly."""
    mock_producer = AsyncMock()
    mock_producer_class.return_value = mock_producer

    publisher = RedpandaPublisher(brokers="localhost:9092")

    signal = IntentSignal(
        tenant_id="t-123",
        signal_type="job_posting",
        company_domain="startup.io",
        payload={"role": "VP of Engineering"},
        timestamp=datetime.utcnow(),
    )

    await publisher.publish(signal)

    mock_producer.start.assert_called_once()
    mock_producer.send_and_wait.assert_called_once()
    call_args = mock_producer.send_and_wait.call_args.kwargs
    assert call_args["topic"] == "intent-signals"
    assert b"startup.io" in call_args["value"]
    mock_producer.stop.assert_called_once()


def test_duckdb_repository_queries_high_intent_leads(tmp_path):
    """Forces Cursor to use DuckDB to query structured intent data."""
    db_path = str(tmp_path / "test_intent.duckdb")
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
    conn.execute(
        """
        INSERT INTO intent_signals VALUES
        ('t-123', 'funding_round', 'rich-company.com', '{"amount": 1000000}', CURRENT_TIMESTAMP),
        ('t-123', 'tech_stack_change', 'poor-company.com', '{"added": "react"}', CURRENT_TIMESTAMP - INTERVAL 2 DAY)
        """
    )
    conn.close()

    repo = DuckDBIntentRepository(db_path=db_path)

    leads = repo.get_recent_signals(tenant_id="t-123", hours_back=24)

    assert len(leads) == 1
    assert leads[0].company_domain == "rich-company.com"
    assert leads[0].signal_type == "funding_round"
