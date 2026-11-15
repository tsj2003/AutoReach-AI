"""Provider-independent signal connector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from engine.signals.events import ConnectorHealth, ConnectorStatus, SignalEvent, SignalFreshness


@dataclass
class ConnectorCursor:
    """Incremental ingestion state for polling connectors."""

    last_cursor: str | None = None
    last_success_at: datetime | None = None
    last_event_at: datetime | None = None
    error_state: str | None = None
    retry_count: int = 0


@dataclass(frozen=True)
class ConnectorCapabilities:
    connector_kind: str
    label: str
    freshness: SignalFreshness
    polling_interval_seconds: int | None
    supports_webhook: bool
    requires_credentials: bool
    configured: bool
    supported_signal_types: tuple[str, ...] = ()


class SignalConnector(ABC):
    """Every external signal source implements this contract."""

    @property
    @abstractmethod
    def connector_kind(self) -> str:
        """Stable identifier, e.g. manual, rss, webhook."""

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities:
        """Describe what this connector can do and whether it is configured."""

    @abstractmethod
    def health(self) -> ConnectorHealth:
        """Current connector health — honest about NOT_CONFIGURED."""

    @abstractmethod
    def fetch_events(
        self,
        *,
        tenant_id: str,
        cursor: ConnectorCursor,
        limit: int = 100,
    ) -> tuple[list[SignalEvent], ConnectorCursor]:
        """Fetch new events incrementally. Must be idempotent for same cursor."""

    def authenticate(self) -> bool:
        """Optional auth step. Return True if ready or not required."""

        return True

    def shutdown(self) -> None:
        """Release resources."""

    def rate_limit_delay_seconds(self) -> float:
        return 0.0


@dataclass
class SignalSourceConfig:
    """Tenant-scoped connector configuration."""

    id: str
    tenant_id: str
    connector_kind: str
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime | None = None


class NotConfiguredConnector(SignalConnector):
    """Placeholder for sources without credentials — never fakes data."""

    def __init__(self, *, connector_kind: str, label: str, message: str = "NOT CONFIGURED") -> None:
        self._kind = connector_kind
        self._label = label
        self._message = message

    @property
    def connector_kind(self) -> str:
        return self._kind

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector_kind=self._kind,
            label=self._label,
            freshness=SignalFreshness.NEAR_REAL_TIME,
            polling_interval_seconds=None,
            supports_webhook=False,
            requires_credentials=True,
            configured=False,
        )

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            source_id=self._kind,
            connector_kind=self._kind,
            status=ConnectorStatus.NOT_CONFIGURED,
            message=self._message,
        )

    def fetch_events(
        self,
        *,
        tenant_id: str,
        cursor: ConnectorCursor,
        limit: int = 100,
    ) -> tuple[list[SignalEvent], ConnectorCursor]:
        return [], cursor
