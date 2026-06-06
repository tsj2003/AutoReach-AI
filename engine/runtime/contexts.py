"""
Default AgentContext and AdapterContext implementations.

These satisfy the Protocols in `engine.core.protocols` so AgentRunners and
Adapters can stay decoupled from the storage/event-sink concrete classes.
"""

from __future__ import annotations

from typing import Iterable, Optional

from engine.core.protocols import CostLedger, EventSink, Store
from engine.core.types import (
    CostEntry,
    Engagement,
    Event,
    Prospect,
)


class DefaultAgentContext:
    """Read-only view passed to AgentRunner.plan()."""

    def __init__(self, store: Store, events: EventSink) -> None:
        self._store = store
        self._events = events

    def get_engagement(self, engagement_id: str) -> Optional[Engagement]:
        return self._store.get_engagement(engagement_id)

    def list_prospects(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Prospect]:
        return self._store.list_prospects(engagement_id, status=status, limit=limit)

    def list_recent_events(
        self,
        engagement_id: str,
        *,
        limit: int = 50,
    ) -> Iterable[Event]:
        return self._events.list_recent(engagement_id=engagement_id, limit=limit)


class DefaultAdapterContext:
    """Read+write view passed to Adapter.execute()."""

    def __init__(self, store: Store, events: EventSink, ledger: CostLedger) -> None:
        self._store = store
        self._events = events
        self._ledger = ledger

    def get_engagement(self, engagement_id: str) -> Optional[Engagement]:
        return self._store.get_engagement(engagement_id)

    def get_prospect(self, prospect_id: str) -> Optional[Prospect]:
        return self._store.get_prospect(prospect_id)

    def emit(self, event: Event) -> None:
        self._events.emit(event)

    def debit(self, cost: CostEntry) -> None:
        self._ledger.debit(cost)
