"""
Adapter implementations.

Each adapter handles a specific channel (Email/Gmail, Calendar/Cal.com, etc.)
and conforms to `engine.core.protocols.Adapter`.

Phase 1 plan:
    * `email_gmail`  — wraps existing Gmail OAuth + MIME build code from
                       `app/worker.py` behind the Adapter protocol.
    * `calendar_cal` — Cal.com booking link generator + booked-meeting webhook
                       receiver (Phase 2).

Adapters are loaded via a registry (TBD in Phase 1.5); for now, the engine
imports them directly.
"""
