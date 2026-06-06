#!/usr/bin/env python3
"""Run the AutoReach Cockpit locally.

Usage:
    .venv/bin/python scripts/run_cockpit.py

Environment:
    AUTOREACH_DB   SQLAlchemy URL (defaults to sqlite:///autoreach_engine.db)
    HOST           bind host (default 127.0.0.1)
    PORT           bind port (default 8765)
"""

from __future__ import annotations

import os

import uvicorn

from cockpit import create_app


def main() -> None:
    app = create_app()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
