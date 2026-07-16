"""
Cockpit FastAPI app factory.

Wires storage + services + runtime together once, mounts the route modules,
and binds Jinja2 templates. Single-file glue; logic lives in `cockpit/routes/`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("cockpit.app")

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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


def _console_enabled_from_env(db_url: str) -> bool:
    """Whether the unauthenticated legacy Jinja console should be mounted.

    Secure by default: the console is OFF unless AUTOREACH_ENABLE_CONSOLE is
    explicitly truthy, with ONE exception — a local sqlite database is treated
    as a developer machine where the console is a convenience, so it defaults
    ON there. Any real (non-sqlite) database defaults the console OFF even if
    the flag is forgotten; production additionally sets the flag to 0 explicitly.
    """
    raw = os.getenv("AUTOREACH_ENABLE_CONSOLE")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return db_url.strip().lower().startswith("sqlite")


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


def _smart_runtime_dispatch_enabled() -> bool:
    return os.getenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _build_reply_detector(
    *,
    info: dict,
    store,
    events,
    ledger,
    ops,
):
    """
    Build a reply detector if Gmail is wired, else return None.

    The cockpit gates the 'Poll replies' button on this. When None, we show
    a small note in the UI explaining what env vars are missing.
    """
    from engine.llm import GeminiClient

    if info.get("kind") == "smart_router":
        from engine.services import TenantMailboxReplyDetector

        return TenantMailboxReplyDetector(
            store=store,
            events=events,
            ledger=ledger,
            ops=ops,
            gemini=GeminiClient(),
        )

    if info.get("kind") != "gmail":
        return None
    from engine import JsonFileTokenStore
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
        SQLAlchemy URL for storage. Defaults to env var DATABASE_URL,
        then AUTOREACH_DB, then ``sqlite:///autoreach_engine.db``.
    """
    db_url = db_url or os.getenv("DATABASE_URL") or os.getenv("AUTOREACH_DB", "sqlite:///autoreach_engine.db")

    # Surface misconfigured credential encryption LOUDLY, but do not crash the
    # whole web service — that would take down auth, dashboard, and health
    # checks (a crash-loop), which is worse than the mailbox feature failing.
    # Credential writes fail closed at the point of use instead (see
    # engine.security.secrets.encrypt_*), so plaintext secrets are never stored.
    from engine.auth.jwt_handler import is_production_like
    from engine.security.secrets import assert_encryption_ready

    try:
        assert_encryption_ready(production=is_production_like())
    except RuntimeError as exc:
        logger.critical(
            "Credential encryption is not ready: %s — mailbox credential storage "
            "will fail closed until AUTOREACH_CREDENTIAL_ENCRYPTION_KEY is set to a "
            "valid Fernet key.",
            exc,
        )

    store, events, ledger = open_storage(db_url)
    ops = OperationsService(store=store, events=events)
    pnl = PnLService(store=store, ledger=ledger)
    csv_ingest = CsvIngestService(ops)

    email_adapter, email_adapter_info = _build_email_adapter()
    if _smart_runtime_dispatch_enabled():
        from engine.dispatch import SmartRoutedEmailAdapter

        email_adapter = SmartRoutedEmailAdapter(store=store, events=events, ledger=ledger)
        email_adapter_info = {
            "kind": "smart_router",
            "sender": "tenant mailbox router",
            "dry_run": False,
            "token_path": None,
            "token_invalid": False,
        }

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
        # Multi-tenant web app: refuse accidental unscoped all-tenant sweeps.
        require_tenant_scope=True,
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

    from engine.telemetry.provider import setup_phoenix_telemetry_from_env

    telemetry_provider = setup_phoenix_telemetry_from_env()

    app = FastAPI(title="AutoReach Cockpit", docs_url=None, redoc_url=None, openapi_url=None)
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
    app.state.telemetry_provider = telemetry_provider
    app.state.db_url = db_url
    app.state.last_poll_result = None

    # ─── routes ──────────────────────────────────────────────────────
    from cockpit.routes import engagements, prospects, replies, meetings, runtime_routes
    from cockpit.routes.webhooks import router as webhooks_router
    from cockpit.api.auth import router as auth_api_router
    from cockpit.api.campaigns import router as campaigns_api_router
    from cockpit.api.contacts import router as contacts_api_router
    from cockpit.api.inbox import router as inbox_api_router
    from cockpit.api.meetings_api import router as meetings_api_router
    from cockpit.api.analytics import router as analytics_api_router
    from cockpit.api.billing import router as billing_api_router
    from cockpit.api.dashboard import router as dashboard_api_router
    from cockpit.api.mailboxes import router as mailboxes_api_router
    from cockpit.api.orphaned import router as orphaned_api_router
    from cockpit.api.outbox import router as outbox_api_router
    from cockpit.api.operations import router as operations_api_router
    from cockpit.api.onboarding import router as onboarding_api_router

    # The legacy Jinja operator console has NO authentication and is not
    # tenant-scoped, so it must never be exposed publicly. Secure by default:
    # OFF for any real (non-sqlite) database, ON only for local sqlite dev,
    # unless AUTOREACH_ENABLE_CONSOLE is set explicitly. See
    # _console_enabled_from_env; production also sets the flag to 0.
    console_enabled = _console_enabled_from_env(db_url)
    legacy_oauth_enabled = os.getenv(
        "AUTOREACH_ENABLE_LEGACY_OAUTH",
        "1" if console_enabled else "0",
    ).strip().lower() in ("1", "true", "yes", "on")
    app.state.console_enabled = console_enabled
    app.state.legacy_oauth_enabled = legacy_oauth_enabled

    if console_enabled:
        # Jinja2 cockpit routes (operator console — dev only, no auth)
        app.include_router(engagements.router)
        app.include_router(prospects.router)
        app.include_router(replies.router)
        app.include_router(meetings.router)
        app.include_router(runtime_routes.router)

    # Legacy token-file OAuth belongs to the unauthenticated Jinja console.
    # Production mailbox connect uses the JWT-protected /api/mailboxes routes.
    if legacy_oauth_enabled:
        from cockpit.routes.oauth_routes import router as oauth_router
        app.include_router(oauth_router)

        @app.get("/oauth/status")
        def oauth_status_page():
            token_path = os.getenv("AUTOREACH_GMAIL_TOKEN_PATH", "token.json")
            from engine import JsonFileTokenStore
            from pathlib import Path as _Path
            token_store = JsonFileTokenStore(token_path=token_path)
            return {
                "configured": bool(os.getenv("GOOGLE_CLIENT_ID")),
                "token_exists": _Path(token_path).exists(),
                "token_invalid": token_store.is_invalid(),
                "sender": os.getenv("AUTOREACH_GMAIL_SENDER", ""),
            }

    # Webhooks are needed in all environments (Cal.com).
    app.include_router(webhooks_router)

    # REST JSON API (M1+M2 — JWT-protected, for the React SPA)
    app.include_router(auth_api_router)
    app.include_router(campaigns_api_router)
    app.include_router(contacts_api_router)
    app.include_router(inbox_api_router)
    app.include_router(meetings_api_router)
    app.include_router(analytics_api_router)
    app.include_router(billing_api_router)
    app.include_router(dashboard_api_router)
    app.include_router(mailboxes_api_router)
    app.include_router(orphaned_api_router)
    app.include_router(outbox_api_router)
    app.include_router(operations_api_router)
    app.include_router(onboarding_api_router)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        # The front door is always the customer-facing React app. The legacy
        # operator console (when enabled) lives at /engagements.
        return RedirectResponse(url="/app/", status_code=302)

    # Serve the React SPA (M3). Static assets are returned directly, and
    # client-side routes like /app/login fall back to index.html.
    dashboard_dist = STATIC_DIR / "dashboard"
    if dashboard_dist.exists():
        dashboard_root = dashboard_dist.resolve()
        dashboard_index = dashboard_root / "index.html"

        @app.get("/app", include_in_schema=False)
        @app.get("/app/", include_in_schema=False)
        def dashboard_index_route():
            return FileResponse(dashboard_index)

        @app.get("/app/{path:path}", include_in_schema=False)
        def dashboard_spa_route(path: str):
            requested = (dashboard_root / path).resolve()
            if requested.is_file() and dashboard_root in requested.parents:
                return FileResponse(requested)
            return FileResponse(dashboard_index)

        @app.get("/favicon.ico", include_in_schema=False)
        def favicon():
            icon = dashboard_root / "brand" / "attainlly-icon.png"
            return FileResponse(icon if icon.exists() else dashboard_index)

    @app.get("/healthz")
    def healthz():
        return {
            "ok": True,
            "version": "phase3",
            "email_adapter": email_adapter_info,
        }

    @app.get("/readyz")
    def readyz(deep: bool = False):
        from cockpit.services.readiness import ProductionReadiness, runtime_dependency_checks

        extra_checks = runtime_dependency_checks(store=store, env=os.environ) if deep else None
        report = ProductionReadiness(env=os.environ).evaluate(extra_checks=extra_checks)
        return {
            "ok": report.is_production_ready,
            "missing_required": report.missing_required,
            "warning_count": report.warning_count,
        }

    @app.get("/adapter")
    def adapter_info():
        return email_adapter_info

    return app
