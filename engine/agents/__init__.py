"""
AgentRunner implementations.

Each runner conforms to `engine.core.protocols.AgentRunner` and implements
`plan()` — deciding which Jobs to enqueue for an Engagement on each tick.

Phase 1 plan:
    * `outbound_agent.OutboundAgentV1` — first-touch + follow-up email
      sequence with reply detection + meeting-booking handoff.

Future runners may include: support, research, account-management, etc. —
the platform thesis is that the engine is product-agnostic.
"""
