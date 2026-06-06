"""
AdapterRegistry: maps a Job to the Adapter that can execute it.

Adapters declare what they `handles()`. The registry asks each in turn until
one accepts. This keeps adapters independent — no central enum to update
when adding a new channel.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from engine.core.protocols import Adapter
from engine.core.types import Job


class AdapterRegistry:
    """A simple ordered list of adapters, queried by `handles(job)`."""

    def __init__(self, adapters: Optional[Iterable[Adapter]] = None) -> None:
        self._adapters: List[Adapter] = list(adapters or [])

    def register(self, adapter: Adapter) -> None:
        self._adapters.append(adapter)

    def find(self, job: Job) -> Optional[Adapter]:
        for adapter in self._adapters:
            if adapter.handles(job):
                return adapter
        return None

    def __len__(self) -> int:
        return len(self._adapters)

    def names(self) -> list[str]:
        return [a.name for a in self._adapters]
