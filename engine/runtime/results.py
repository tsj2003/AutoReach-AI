"""Concrete AdapterResult dataclass shared by all adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AdapterResultData:
    """
    Concrete implementation of `engine.core.protocols.AdapterResult`.

    Adapters return one of these from `execute()`. The runtime translates
    `succeeded` and `retryable` into state machine transitions.
    """

    succeeded: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retryable: bool = False

    @classmethod
    def ok(cls, **output: Any) -> "AdapterResultData":
        return cls(succeeded=True, output=output)

    @classmethod
    def fail(cls, error: str, *, retryable: bool = False, **output: Any) -> "AdapterResultData":
        return cls(succeeded=False, output=output, error=error, retryable=retryable)
