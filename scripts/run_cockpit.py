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
import sys

# Ensure the repo root is importable when run as `python3 scripts/run_cockpit.py`
# (running a script puts scripts/ on sys.path, not the project root).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import uvicorn

from cockpit import create_app


def main() -> None:
    # Load .env for local development so GEMINI_API_KEY / secrets are picked up.
    # No-op in production (env comes from the platform; no .env present) and not
    # imported by the app module, so tests are unaffected.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    app = create_app()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
