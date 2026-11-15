"""
ASGI entrypoint for production (gunicorn + uvicorn worker).

    gunicorn asgi:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT

The cockpit app factory reads DATABASE_URL / AUTOREACH_* env vars.
"""

import os

from cockpit import create_app

# DATABASE_URL is the Render/Heroku standard; fall back to AUTOREACH_DB then SQLite.
_db_url = os.getenv("DATABASE_URL") or os.getenv("AUTOREACH_DB") or "sqlite:///autoreach_engine.db"

app = create_app(db_url=_db_url)
