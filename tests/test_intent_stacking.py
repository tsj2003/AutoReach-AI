"""Signal Stack gate end-to-end: accounts below the stack threshold are skipped,
and stacked signals converge into ONE evidence-bearing prospect."""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from engine import Engagement, open_storage
from engine.intent.ingestor import IntentProspectIngestor
from engine.intent.repository import DuckDBIntentRepository


def _seed(tmp_path, rows):
    db_path = str(tmp_path / "intent.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute(
        "CREATE TABLE intent_signals (tenant_id VARCHAR, signal_type VARCHAR, "
        "company_domain VARCHAR, payload JSON, timestamp TIMESTAMP)"
    )
    for r in rows:
        conn.execute(
            "INSERT INTO intent_signals VALUES (?, ?, ?, ?, ?)",
            [r["tenant_id"], r["signal_type"], r["company_domain"], r["payload"], r["timestamp"]],
        )
    conn.close()
    return db_path


def _engagement(store, *, min_stack):
    store.save_engagement(
        Engagement(
            id="eng-1", customer_name="ACME", offer="Offer", icp_description="ICP",
            metadata={"signal_matrix": {
                "allowed_signal_types": ["funding_round", "hiring_surge"],
                "min_signal_stack": min_stack,
            }},
        ),
        tenant_id="t-123",
    )


def test_stack_gate_skips_shallow_accounts_and_keeps_stacked(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'e.db'}")
    _engagement(store, min_stack=2)
    now = datetime.now(UTC).replace(tzinfo=None)
    db = _seed(tmp_path, [
        # solo.com: only ONE distinct type → below stack 2 → skipped
        {"tenant_id": "t-123", "signal_type": "funding_round", "company_domain": "solo.com",
         "payload": '{"company": "Solo"}', "timestamp": now},
        # hot.com: TWO distinct types → qualifies
        {"tenant_id": "t-123", "signal_type": "funding_round", "company_domain": "hot.com",
         "payload": '{"company": "Hot Co", "contact_email": "ceo@hot.com"}', "timestamp": now},
        {"tenant_id": "t-123", "signal_type": "hiring_surge", "company_domain": "hot.com",
         "payload": '{"company": "Hot Co"}', "timestamp": now},
    ])

    result = IntentProspectIngestor(
        store=store, events=events, repository=DuckDBIntentRepository(db_path=db),
    ).ingest_campaign(tenant_id="t-123", engagement_id="eng-1")

    assert result.created_count == 1  # only hot.com
    p = store.get_prospect(result.created_prospect_ids[0])
    assert p.company == "Hot Co"
    stack = p.research["signal_stack"]
    assert stack["depth"] == 2
    assert {e["signal_type"] for e in stack["evidence"]} == {"funding_round", "hiring_surge"}
    assert stack["score"] > 0


def test_stack_gate_default_min_1_is_backward_compatible(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'e2.db'}")
    # No min_signal_stack set → defaults to 1 → a single signal still qualifies.
    store.save_engagement(
        Engagement(
            id="eng-1", customer_name="ACME", offer="Offer", icp_description="ICP",
            metadata={"signal_matrix": {"allowed_signal_types": ["funding_round"]}},
        ),
        tenant_id="t-123",
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    db = _seed(tmp_path, [
        {"tenant_id": "t-123", "signal_type": "funding_round", "company_domain": "one.com",
         "payload": '{"company": "One"}', "timestamp": now},
    ])
    result = IntentProspectIngestor(
        store=store, events=events, repository=DuckDBIntentRepository(db_path=db),
    ).ingest_campaign(tenant_id="t-123", engagement_id="eng-1")
    assert result.created_count == 1
