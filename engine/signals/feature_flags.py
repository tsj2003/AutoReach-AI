"""Feature flags for signal intelligence capabilities."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SignalFeatureFlags:
    """Controlled rollout flags — incomplete capabilities stay off by default."""

    signals_enabled: bool
    mcp_enabled: bool
    enrichment_enabled: bool
    reply_ai_enabled: bool
    learning_enabled: bool

    @classmethod
    def from_env(cls) -> SignalFeatureFlags:
        return cls(
            signals_enabled=_env_bool("AUTOREACH_SIGNALS_ENABLED", default=True),
            mcp_enabled=_env_bool("AUTOREACH_MCP_ENABLED", default=True),
            enrichment_enabled=_env_bool("AUTOREACH_ENRICHMENT_ENABLED", default=True),
            reply_ai_enabled=_env_bool("AUTOREACH_REPLY_AI_ENABLED", default=True),
            learning_enabled=_env_bool("AUTOREACH_LEARNING_ENABLED", default=True),
        )


signal_flags = SignalFeatureFlags.from_env()


def is_signals_enabled() -> bool:
    """Read flag at call time so tests/deploy can toggle without reimport."""

    return _env_bool("AUTOREACH_SIGNALS_ENABLED", default=True)


def is_enrichment_enabled() -> bool:
    return _env_bool("AUTOREACH_ENRICHMENT_ENABLED", default=True)


def is_mcp_enabled() -> bool:
    return _env_bool("AUTOREACH_MCP_ENABLED", default=True)


def is_reply_ai_enabled() -> bool:
    return _env_bool("AUTOREACH_REPLY_AI_ENABLED", default=True)


def is_learning_enabled() -> bool:
    return _env_bool("AUTOREACH_LEARNING_ENABLED", default=True)


def is_engine_paused() -> bool:
    """Global kill switch — stops beat tick of all active campaigns."""

    return _env_bool("AUTOREACH_ENGINE_PAUSED", default=False)
