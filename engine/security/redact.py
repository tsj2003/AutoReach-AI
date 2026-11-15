"""Centralized secret redaction for logs, audits, and API responses."""

from __future__ import annotations

import re
from typing import Any

_REDACT_PATTERNS = (
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"), "Bearer ***"),
    (re.compile(
        r"(?i)(api[_-]?key|secret|password|token|authorization)\s*=\s*['\"]?([^\s'\",}{]+)"
    ), r"\1=***"),
    (re.compile(r"sha256=[a-f0-9]{32,}"), "sha256=***"),
)

_SENSITIVE_KEYS = frozenset({
    "password", "secret", "token", "api_key", "apikey", "authorization",
    "webhook_secret", "refresh_token", "access_token", "credentials",
    "client_secret", "private_key",
})


def redact_string(value: str) -> str:
    out = value
    for pattern, repl in _REDACT_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_value(key: str, value: Any) -> Any:
    if key.lower() in _SENSITIVE_KEYS:
        return "***"
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, dict):
        return redact_dict(value)
    if isinstance(value, list):
        return [redact_value("", v) if isinstance(v, (dict, str)) else v for v in value]
    return value


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {k: redact_value(k, v) for k, v in data.items()}
