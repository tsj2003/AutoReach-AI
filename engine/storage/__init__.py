"""
Storage backends for the engine.

Phase 1: SQLite via SQLAlchemy Core (`engine.storage.sqlite`). Schema is
designed to lift cleanly to Postgres in Phase 5 with no model changes —
only the engine URL and dialect-specific tweaks.

Public API:
    SqliteStore  → conforms to engine.core.protocols.Store
    SqliteEventSink → conforms to engine.core.protocols.EventSink
    SqliteCostLedger → conforms to engine.core.protocols.CostLedger
    open_storage(url) → convenience opener returning all three
"""

from engine.storage.sqlite import (  # noqa: F401
    SqliteCostLedger,
    SqliteEventSink,
    SqliteStore,
    open_storage,
)

__all__ = [
    "SqliteStore",
    "SqliteEventSink",
    "SqliteCostLedger",
    "open_storage",
]
