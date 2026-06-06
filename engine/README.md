# `engine/` — the AutoReach platform engine

This package is the **product-agnostic execution layer** that powers everything
AutoReach builds. The cold-outbound product (OaaS) is the first consumer; the
public agent platform is the second.

See `docs/PLATFORM.md` for the thesis and `docs/IMPLEMENTATION_PLAN.md` for
the phased roadmap.

## Layout

```
engine/
├── __init__.py            Public API surface (re-exports)
├── core/
│   ├── types.py           Engagement, Agent, Job, Event, Prospect, CostEntry
│   ├── state.py           JobStateMachine — the only path that mutates Job.state
│   └── protocols.py       Adapter, AgentRunner, Store, EventSink, CostLedger
├── adapters/              Channel-specific executors (email, calendar, …)
└── agents/                AgentRunner implementations (outbound.v1, …)
```

## What's implemented (Phase 0)

- ✅ Core dataclasses (`engine.core.types`)
- ✅ Job state machine with guarded transitions (`engine.core.state`)
- ✅ Plug-in Protocols for Adapter / AgentRunner / Store / EventSink / CostLedger
      (`engine.core.protocols`)

## What's next (Phase 1, Days 4–10)

- ⬜ `engine.storage.sqlite` — concrete `Store` + `EventSink` + `CostLedger` impls
- ⬜ `engine.adapters.email_gmail` — Gmail send adapter (wrapping existing code)
- ⬜ `engine.agents.outbound_agent` — first concrete `AgentRunner`
- ⬜ End-to-end integration test: full Job lifecycle on a single test prospect

## Design rules (binding)

1. **No mutable shared state outside `Job`.** Engagements, Agents, Prospects,
   Events, CostEntries are frozen dataclasses. Mutate via the Store, not by
   field assignment.
2. **State changes go through `JobStateMachine.transition()`.** Setting
   `job.state = "running"` directly is a bug. Always use the state machine.
3. **Events are append-only.** Never delete an Event. If something is wrong,
   append a corrective Event. The event log is the audit trail; tampering
   with it kills the platform's value.
4. **Adapters are stateless from the engine's view.** Any external state
   (OAuth tokens, rate-limit counters) is the adapter's internal concern.
5. **Money is integer cents, never floats.** Floats drift; cents don't.
6. **Timestamps are timezone-aware UTC.** Naive datetimes are banned.
7. **Public surface is `engine/__init__.py`'s `__all__`.** Anything imported
   from elsewhere is internal and may break without notice.
