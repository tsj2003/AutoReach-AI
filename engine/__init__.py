"""
AutoReach Engine
================

The AI agent execution platform.

This package defines the core abstractions and a reference implementation for
running long-running, observable, cost-controlled AI agents that perform
real-world actions (sending emails, booking meetings, etc.).

The engine is product-agnostic. The first product on top is OaaS
(outbound-as-a-service); future products will plug in via the same
Adapter and Agent protocols.

See `docs/PLATFORM.md` for the platform thesis and `docs/IMPLEMENTATION_PLAN.md`
for the phased roadmap.

Stable public surface
---------------------
    Core types ........... Engagement, Agent, Job, Event, EventKind, Prospect, CostEntry
    State machine ........ JobState, JobStateMachine
    Protocols ............ Adapter, AgentRunner, EventSink, Store, CostLedger
    Runtime .............. EngineRuntime, AdapterRegistry, AdapterResultData
    Storage .............. SqliteStore, SqliteEventSink, SqliteCostLedger, open_storage
    Adapters ............. ConsoleEmailAdapter, GmailEmailAdapter
    Agent runners ........ OutboundAgentV1
"""

from engine.adapters.email_console import ConsoleEmailAdapter
from engine.adapters.email_gmail import GmailEmailAdapter
from engine.adapters.email_gmail_real import RealGmailSendAdapter
from engine.adapters.gmail_token_store import (
    GmailTokenStore,
    JsonFileTokenStore,
    TokenInvalid,
    TokenUnavailable,
)
from engine.agents.outbound_agent import OutboundAgentV1
from engine.core.protocols import (
    Adapter,
    AgentRunner,
    CostLedger,
    EventSink,
    Store,
)
from engine.core.state import JobState, JobStateMachine
from engine.core.types import (
    Agent,
    CostEntry,
    Engagement,
    Event,
    EventKind,
    Job,
    JobKind,
    Meeting,
    Prospect,
    Reply,
)
from engine.runtime import (
    AdapterRegistry,
    AdapterResultData,
    EngineRuntime,
)
from engine.storage import (
    SqliteCostLedger,
    SqliteEventSink,
    SqliteStore,
    open_storage,
)

__version__ = "0.1.0"

__all__ = [
    # Core types
    "Agent",
    "CostEntry",
    "Engagement",
    "Event",
    "EventKind",
    "Job",
    "JobKind",
    "Meeting",
    "Prospect",
    "Reply",
    # State
    "JobState",
    "JobStateMachine",
    # Protocols
    "Adapter",
    "AgentRunner",
    "CostLedger",
    "EventSink",
    "Store",
    # Runtime
    "AdapterRegistry",
    "AdapterResultData",
    "EngineRuntime",
    # Storage
    "SqliteStore",
    "SqliteEventSink",
    "SqliteCostLedger",
    "open_storage",
    # Adapters
    "ConsoleEmailAdapter",
    "GmailEmailAdapter",
    "RealGmailSendAdapter",
    "GmailTokenStore",
    "JsonFileTokenStore",
    "TokenInvalid",
    "TokenUnavailable",
    # Agent runners
    "OutboundAgentV1",
    # Meta
    "__version__",
]
