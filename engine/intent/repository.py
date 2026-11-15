"""DuckDB-backed query access for intent signals."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

import duckdb

from engine.intent.models import IntentSignal


class DuckDBIntentRepository:
    """Query structured intent signals loaded into a local DuckDB database."""

    def __init__(self, *, db_path: str) -> None:
        self.db_path = db_path

    def get_recent_signals(
        self,
        *,
        tenant_id: str,
        hours_back: int,
        signal_types: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> list[IntentSignal]:
        """Return tenant-scoped signals newer than the requested lookback window."""

        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours_back)
        params: list[Any] = [tenant_id, cutoff]
        type_filter = ""
        normalized_signal_types = sorted({str(signal_type) for signal_type in signal_types or []})
        if normalized_signal_types:
            placeholders = ", ".join("?" for _ in normalized_signal_types)
            type_filter = f" AND signal_type IN ({placeholders})"
            params.extend(normalized_signal_types)
        limit_clause = ""
        if limit is not None:
            limit_clause = " LIMIT ?"
            params.append(int(limit))

        with duckdb.connect(self.db_path, read_only=True) as conn:
            rows = conn.execute(
                f"""
                SELECT tenant_id, signal_type, company_domain, payload, timestamp
                FROM intent_signals
                WHERE tenant_id = ? AND timestamp >= ?{type_filter}
                ORDER BY timestamp DESC
                {limit_clause}
                """,
                params,
            ).fetchall()

        return [
            IntentSignal(
                tenant_id=row[0],
                signal_type=row[1],
                company_domain=row[2],
                payload=self._coerce_payload(row[3]),
                timestamp=row[4],
            )
            for row in rows
        ]

    @staticmethod
    def _coerce_payload(payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            decoded = json.loads(payload)
            if isinstance(decoded, dict):
                return decoded
        raise TypeError("intent signal payload must be a JSON object")
