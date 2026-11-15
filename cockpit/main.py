"""Test-friendly FastAPI app entrypoint for the Cockpit."""

from __future__ import annotations

import os

from cockpit import create_app

_db_url = os.getenv("DATABASE_URL") or os.getenv("AUTOREACH_DB") or "sqlite:///autoreach_engine.db"

app = create_app(db_url=_db_url)
