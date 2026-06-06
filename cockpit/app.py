"""
Cockpit FastAPI app factory.

Wires storage + services + runtime together once, mounts the route modules,
and binds Jinja2 templates. Single-file glue; logic lives in `cockpit/routes/`.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from engine import (
    AdapterRegistry,
    ConsoleEmailAdapter,
    EngineRuntime,
    JsonFileTokenStore,
    OutboundAgentV1,
    RealGmailSendAdapter,
    open_storage,
)
from engine.services import CsvIngestService, OperationsService, PnLService

PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def _format_cents(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"${cents / 100:,.2f}"


def _format_pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _build_email_adapter():
    """
    Choose the email adapter based on environment.

    AUTOREACH_GMAIL_TOKEN_PATH set      → RealGmailSendAdapter (production)
    AUTOREACH_GMAIL_DRY_RUN=1           → RealGmailSendAdapter in dry-run mode
                                          (only honored if a token path is set;
                                          we never want to "look real" without a token)
    nothing set                          → ConsoleEmailAdapter (dev/test)

    Returns: (adapter_instance, info_dict) — info is shown on the cockpit UI.
    """
    token_path = os.getenv("AUTOREACH_GMAIL_TOKEN_PATH")
    sender = os.getenv("AUTOREACH_GMAIL_SENDER", "")

    if token_path and sender:
        store = JsonFileTokenStore(token_path=token_path)
        dry_run_env = os.getenv("AUTOREACH_GMAIL_DRY_RUN", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        adapter = RealGmailSendAdapter(
            sender_email=sender,
            token_store=store,
            dry_run=dry_run_env,
        )
        info = {
            "kind": "gmail",
            "sender": sender,
            "dry_run": adapter.dry_run,
            "token_path": token_path,
            "token_invalid": store.is_invalid(),
        }
        return adapter, info

    return ConsoleEmailAdapter(), {
        "kind": "console",
        "sender": "(none — console adapter; no real emails sent)",
        "dry_run": False,
        "token_path": None,
        "token_invalid": False,
    }


def _build_reply_detector(
    *,
    info: dict,
    store,
    events,
    ledger,
    ops,
):
    """
    Build a GmailReplyDetector if Gmail is wired, else return None.

    The cockpit gates the 'Poll replies' button on this. When None, we show
    a small note in the UI explaining what env vars are missing.
    """
    if info.get("kind") != "gmail":
        return None
    from engine import JsonFileTokenStore
    from engine.llm import GeminiClient
    from engine.services import GmailReplyDetector

    token_store = JsonFileTokenStore(token_path=info["token_path"])
    sender = info["sender"]
    return GmailReplyDetector(
        store=store,
        events=events,
        ledger=ledger,
        ops=ops,
        token_store=token_store,
        sender_email=sender,
        gemini=GeminiClient(),  # picks up GEMINI_API_KEY from env
    )


def create_app(*, db_url: str | None = None) -> FastAPI:
    """
    Build the cockpit FastAPI app.

    Parameters
    ----------
    db_url : str | None
        SQLAlchemy URL for storage. Defaults to env var AUTOREACH_DB
        or ``sqlite:///autoreach_engine.db`` in the working directory.
    """
    db_url = db_url or os.getenv("AUTOREACH_DB", "sqlite:///autoreach_engine.db")

    store, events, ledger = open_storage(db_url)
    ops = OperationsService(store=store, events=events)
    pnl = PnLService(store=store, ledger=ledger)
    csv_ingest = CsvIngestService(ops)

    email_adapter, email_adapter_info = _build_email_adapter()

    # Construct the outbound agent runner. If GEMINI_API_KEY is set, plug
    # personalization in; otherwise the runner falls back to template-only.
    from engine.llm import GeminiClient

    _gemini = GeminiClient()
    runner = OutboundAgentV1(
        gemini=_gemini if _gemini.has_api_key else None,
        ledger=ledger,
    )

    runtime = EngineRuntime(
        store=store,
        events=events,
        ledger=ledger,
        adapters=AdapterRegistry([email_adapter]),
        agent_runners={OutboundAgentV1.runner_kind: runner},
    )

    # Reply detector — only wired when we have real Gmail credentials AND a
    # Gemini key. Without either, the cockpit still works in console-only mode.
    reply_detector = _build_reply_detector(
        info=email_adapter_info, store=store, events=events,
        ledger=ledger, ops=ops,
    )

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["cents"] = _format_cents
    templates.env.filters["pct"] = _format_pct

    app = FastAPI(title="AutoReach Cockpit", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # CORS — allow React dev server and same origin.
    origins = os.getenv("AUTOREACH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Session middleware — needed for OAuth PKCE state storage.
    session_secret = os.getenv("AUTOREACH_SESSION_SECRET") or os.urandom(32).hex()
    app.add_middleware(SessionMiddleware, secret_key=session_secret)

    # Make services available to route handlers via app.state.
    app.state.store = store
    app.state.events = events
    app.state.ledger = ledger
    app.state.ops = ops
    app.state.pnl = pnl
    app.state.csv_ingest = csv_ingest
    app.state.runtime = runtime
    app.state.templates = templates
    app.state.email_adapter = email_adapter
    app.state.email_adapter_info = email_adapter_info
    app.state.reply_detector = reply_detector
    app.state.last_poll_result = None

    # ─── routes ──────────────────────────────────────────────────────
    from cockpit.routes import engagements, prospects, replies, meetings, runtime_routes
    from cockpit.routes.oauth_routes import router as oauth_router
    from cockpit.routes.webhooks import router as webhooks_router
    from cockpit.api.auth import router as auth_api_router
    from cockpit.api.campaigns import router as campaigns_api_router
    from cockpit.api.contacts import router as contacts_api_router
    from cockpit.api.inbox import router as inbox_api_router
    from cockpit.api.meetings_api import router as meetings_api_router
    from cockpit.api.analytics import router as analytics_api_router
    from cockpit.api.billing import router as billing_api_router
    from cockpit.api.mailboxes import router as mailboxes_api_router

    # Jinja2 cockpit routes (operator console — no auth required)
    app.include_router(engagements.router)
    app.include_router(prospects.router)
    app.include_router(replies.router)
    app.include_router(meetings.router)
    app.include_router(runtime_routes.router)
    app.include_router(oauth_router)
    app.include_router(webhooks_router)

    # REST JSON API (M1+M2 — JWT-protected, for the React SPA)
    app.include_router(auth_api_router)
    app.include_router(campaigns_api_router)
    app.include_router(contacts_api_router)
    app.include_router(inbox_api_router)
    app.include_router(meetings_api_router)
    app.include_router(analytics_api_router)
    app.include_router(billing_api_router)
    app.include_router(mailboxes_api_router)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return RedirectResponse(url="/engagements", status_code=302)

    # Serve the React SPA (M3) at /app/* if it's been built.
    dashboard_dist = STATIC_DIR / "dashboard"
    if dashboard_dist.exists():
        app.mount(
            "/app",
            StaticFiles(directory=str(dashboard_dist), html=True),
            name="dashboard",
        )

    @app.get("/healthz")
    def healthz():
        return {
            "ok": True,
            "version": "phase3",
            "email_adapter": email_adapter_info,
        }

    @app.get("/adapter")
    def adapter_info():
        return email_adapter_info

    @app.get("/oauth/status")
    def oauth_status_page():
        import json as _json
        token_path = os.getenv("AUTOREACH_GMAIL_TOKEN_PATH", "token.json")
        from engine import JsonFileTokenStore
        from pathlib import Path as _Path
        store = JsonFileTokenStore(token_path=token_path)
        return {
            "configured": bool(os.getenv("GOOGLE_CLIENT_ID")),
            "token_exists": _Path(token_path).exists(),
            "token_invalid": store.is_invalid(),
            "sender": os.getenv("AUTOREACH_GMAIL_SENDER", ""),
        }

    return app
