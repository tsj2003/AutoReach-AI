"""
AutoReach Cockpit — the operator's web UI.

This is *not* a customer-facing SaaS. It's the internal operations console
the operator (you) drives daily during the OaaS phase. By design:

    * One operator, no auth (run on localhost or behind a tunnel)
    * Server-rendered HTML (Jinja2), forms over HTMX-style replaces
    * Reads/writes the same engine DB — no separate state, no sync issues
    * All actions go through engine.services.OperationsService

Layout:
    cockpit/app.py        FastAPI app factory
    cockpit/routes/       view modules (engagements, prospects, replies, ...)
    cockpit/templates/    Jinja2 templates
    cockpit/static/       CSS only — no JS framework
"""

from cockpit.app import create_app  # noqa: F401

__all__ = ["create_app"]
