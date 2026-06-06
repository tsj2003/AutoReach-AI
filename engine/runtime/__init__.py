"""
The runtime layer: glue between agents, adapters, storage, and the state machine.

Public API:
    AdapterRegistry     → maps Job → Adapter
    AdapterResultData   → typed result returned by adapters
    EngineRuntime       → the main orchestrator (plan → dispatch → execute → record)
    DefaultAgentContext → AgentContext implementation backed by Store + EventSink
    DefaultAdapterContext → AdapterContext implementation backed by Store + EventSink + CostLedger
"""

from engine.runtime.contexts import DefaultAdapterContext, DefaultAgentContext  # noqa: F401
from engine.runtime.registry import AdapterRegistry  # noqa: F401
from engine.runtime.results import AdapterResultData  # noqa: F401
from engine.runtime.runtime import EngineRuntime  # noqa: F401

__all__ = [
    "AdapterRegistry",
    "AdapterResultData",
    "EngineRuntime",
    "DefaultAgentContext",
    "DefaultAdapterContext",
]
