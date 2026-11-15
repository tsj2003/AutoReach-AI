"""In-memory intent repository — same interface as DuckDBIntentRepository.

Lets the ingestor run against an explicit set of signals (simulation endpoint,
demos, tests) without standing up Redpanda/DuckDB. It runs the REAL
IntentProspectIngestor + SignalStackPolicy, so it exercises genuine stacking
logic — not a mock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from engine.intent.models import IntentSignal


class MemoryIntentRepository:
    def __init__(self, signals: Optional[Iterable[IntentSignal]] = None) -> None:
        self._signals: list[IntentSignal] = list(signals or [])

    def add(self, signal: IntentSignal) -> None:
        self._signals.append(signal)

    def get_recent_signals(
        self,
        *,
        tenant_id: str,
        hours_back: int = 24,
        signal_types: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> list[IntentSignal]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        allowed = {str(s) for s in signal_types} if signal_types else None
        out: list[IntentSignal] = []
        for sig in self._signals:
            if sig.tenant_id != tenant_id:
                continue
            ts = sig.timestamp if sig.timestamp.tzinfo else sig.timestamp.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                continue
            if allowed is not None and sig.signal_type not in allowed:
                continue
            out.append(sig)
        if limit is not None:
            out = out[:limit]
        return out
