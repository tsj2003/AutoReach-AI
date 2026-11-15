"""Strict schemas for real-time buyer intent signals."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

try:  # Pydantic v2
    from pydantic import ConfigDict, StrictStr
except ImportError:  # pragma: no cover - only used on older environments
    ConfigDict = None  # type: ignore[assignment]
    StrictStr = str  # type: ignore[assignment,misc]


class IntentSignal(BaseModel):
    """Tenant-scoped signal loaded from Redpanda/dlt into DuckDB."""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", strict=True)
    else:  # pragma: no cover
        class Config:
            extra = "forbid"

    tenant_id: StrictStr
    signal_type: StrictStr
    company_domain: StrictStr
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

    def to_payload_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict for Kafka/Redpanda publishing."""

        if hasattr(self, "model_dump"):
            return self.model_dump(mode="json")
        data = self.dict()  # pragma: no cover - pydantic v1 fallback
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def to_json_bytes(self) -> bytes:
        """Serialize this signal as compact UTF-8 JSON bytes."""

        return json.dumps(
            self.to_payload_dict(),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


class IntentIngestionResult(BaseModel):
    """Summary of an intent-to-prospect ingestion pass."""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", strict=True)
    else:  # pragma: no cover
        class Config:
            extra = "forbid"

    created_count: int = 0
    skipped_count: int = 0
    created_prospect_ids: list[StrictStr] = Field(default_factory=list)
    openinference_trace_id: StrictStr
