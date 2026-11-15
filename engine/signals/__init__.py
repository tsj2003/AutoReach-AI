"""Attainly Signal Intelligence — normalized ingestion, dedup, and scoring."""

from engine.signals.events import (
    CanonicalSignal,
    ConnectorHealth,
    ConnectorStatus,
    SignalEvent,
    SignalFreshness,
)
from engine.signals.feature_flags import signal_flags
from engine.signals.ingestion import SignalIngestionService
from engine.signals.registry import SignalTypeRegistry, get_signal_registry
from engine.signals.repository import SignalRepository
from engine.signals.scoring import ProspectPriorityScore, ProspectPriorityScorer

__all__ = [
    "CanonicalSignal",
    "ConnectorHealth",
    "ConnectorStatus",
    "ProspectPriorityScore",
    "ProspectPriorityScorer",
    "SignalEvent",
    "SignalFreshness",
    "SignalIngestionService",
    "SignalRepository",
    "SignalTypeRegistry",
    "get_signal_registry",
    "signal_flags",
]
