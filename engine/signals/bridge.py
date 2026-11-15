"""Bridge SignalRepository to IntentProspectIngestor."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from engine.intent.models import IntentSignal
from engine.signals.repository import SignalRepository


class StoreIntentRepository:
    """Same contract as DuckDBIntentRepository / MemoryIntentRepository.

    Reads canonical signals from the main SQL store so IntentProspectIngestor
    can run against persisted signal intelligence without DuckDB.
    """

    def __init__(self, *, repository: SignalRepository) -> None:
        self._repository = repository

    def get_recent_signals(
        self,
        *,
        tenant_id: str,
        hours_back: int,
        signal_types: Iterable[str] | None = None,
        limit: Optional[int] = None,
    ) -> list[IntentSignal]:
        return self._repository.list_recent_as_intent_signals(
            tenant_id=tenant_id,
            hours_back=hours_back,
            signal_types=signal_types,
            limit=limit,
        )
