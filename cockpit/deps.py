"""Re-export dependencies from cockpit.api.deps for backwards compatibility."""

from __future__ import annotations

from cockpit.api.deps import (
    get_csv_ingest,
    get_current_user,
    get_events,
    get_ledger,
    get_ops,
    get_pnl,
    get_reply_detector,
    get_runtime,
    get_store,
)

__all__ = [
    "get_current_user",
    "get_store",
    "get_ops",
    "get_pnl",
    "get_events",
    "get_ledger",
    "get_runtime",
    "get_csv_ingest",
    "get_reply_detector",
]
