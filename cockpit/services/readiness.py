"""Production readiness checks for pilot operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text

Status = Literal["PASS", "WARN", "FAIL"]


class ReadinessCheck(BaseModel):
    key: str
    label: str
    status: Status
    required: bool
    detail: str
    env_vars: list[str] = Field(default_factory=list)


class ReadinessReport(BaseModel):
    is_production_ready: bool
    checks: list[ReadinessCheck]
    missing_required: list[str]
    warning_count: int


class ProductionReadiness:
    """Evaluates deploy-time configuration without exposing secret values."""

    _DEV_JWT_SECRET = "CHANGE_ME_SET_AUTOREACH_JWT_SECRET_IN_ENV"

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = env

    def evaluate(self, *, extra_checks: Iterable[ReadinessCheck] | None = None) -> ReadinessReport:
        checks = [
            self._database_check(),
            self._redis_check(),
            self._jwt_secret_check(),
            self._session_secret_check(),
            self._credential_encryption_check(),
            self._console_check(),
            self._smart_runtime_dispatch_check(),
            self._gemini_check(),
            self._google_oauth_check(),
            self._celery_agent_queue_check(),
            self._phoenix_check(),
            self._intent_store_check(),
            self._razorpay_check(),
            self._calcom_check(),
            self._sentry_check(),
        ]
        if extra_checks:
            checks.extend(extra_checks)
        missing_required = [
            check.key for check in checks
            if check.required and check.status == "FAIL"
        ]
        return ReadinessReport(
            is_production_ready=not missing_required,
            checks=checks,
            missing_required=missing_required,
            warning_count=sum(1 for check in checks if check.status == "WARN"),
        )

    def _database_check(self) -> ReadinessCheck:
        value = self._get("DATABASE_URL")
        return self._check(
            key="database_url",
            label="Postgres database",
            required=True,
            env_vars=["DATABASE_URL"],
            ok=bool(value) and not value.startswith("sqlite:"),
            ok_detail="Postgres DATABASE_URL is configured.",
            fail_detail="Set DATABASE_URL to a production Postgres connection string.",
        )

    def _redis_check(self) -> ReadinessCheck:
        return self._check(
            key="redis_url",
            label="Redis broker",
            required=True,
            env_vars=["REDIS_URL"],
            ok=bool(self._get("REDIS_URL")),
            ok_detail="Redis broker/result backend is configured.",
            fail_detail="Set REDIS_URL so Celery workers can receive production work.",
        )

    def _jwt_secret_check(self) -> ReadinessCheck:
        secret = self._get("AUTOREACH_JWT_SECRET")
        return self._check(
            key="jwt_secret",
            label="JWT signing secret",
            required=True,
            env_vars=["AUTOREACH_JWT_SECRET"],
            ok=bool(secret) and secret != self._DEV_JWT_SECRET and len(secret) >= 32,
            ok_detail="JWT signing secret is present and non-default.",
            fail_detail="Set AUTOREACH_JWT_SECRET to a strong random value.",
        )

    def _session_secret_check(self) -> ReadinessCheck:
        secret = self._get("AUTOREACH_SESSION_SECRET")
        return self._check(
            key="session_secret",
            label="Session secret",
            required=True,
            env_vars=["AUTOREACH_SESSION_SECRET"],
            ok=bool(secret) and len(secret) >= 32,
            ok_detail="Session secret is configured.",
            fail_detail="Set AUTOREACH_SESSION_SECRET to a strong random value.",
        )

    def _credential_encryption_check(self) -> ReadinessCheck:
        key = self._get("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY")
        try:
            if key:
                from cryptography.fernet import Fernet  # type: ignore
                Fernet(key.encode("utf-8"))
            valid = bool(key)
        except Exception:
            valid = False
        return self._check(
            key="credential_encryption_key",
            label="Mailbox credential encryption key",
            required=True,
            env_vars=["AUTOREACH_CREDENTIAL_ENCRYPTION_KEY"],
            ok=valid,
            ok_detail="Mailbox credential encryption key is configured.",
            fail_detail="Set AUTOREACH_CREDENTIAL_ENCRYPTION_KEY to a Fernet key before connecting production mailboxes.",
        )

    def _console_check(self) -> ReadinessCheck:
        disabled = self._get("AUTOREACH_ENABLE_CONSOLE").lower() in {"0", "false", "no", "off"}
        return self._check(
            key="legacy_console_disabled",
            label="Legacy console disabled",
            required=True,
            env_vars=["AUTOREACH_ENABLE_CONSOLE"],
            ok=disabled,
            ok_detail="Unauthenticated legacy console is disabled.",
            fail_detail="Set AUTOREACH_ENABLE_CONSOLE=0 before exposing production.",
        )

    def _smart_runtime_dispatch_check(self) -> ReadinessCheck:
        enabled = self._get("AUTOREACH_RUNTIME_SMART_DISPATCH").lower() in {"1", "true", "yes", "on"}
        return self._check(
            key="smart_runtime_dispatch",
            label="Smart runtime dispatch",
            required=True,
            env_vars=["AUTOREACH_RUNTIME_SMART_DISPATCH"],
            ok=enabled,
            ok_detail="Legacy runtime email jobs use the smart inbox router.",
            fail_detail="Set AUTOREACH_RUNTIME_SMART_DISPATCH=1 so approved sends cannot bypass mailbox health routing.",
        )

    def _gemini_check(self) -> ReadinessCheck:
        return self._check(
            key="gemini_api_key",
            label="Gemini AI key",
            required=True,
            env_vars=["GEMINI_API_KEY"],
            ok=bool(self._get("GEMINI_API_KEY")),
            ok_detail="Gemini API key is configured.",
            fail_detail="Set GEMINI_API_KEY for classification and personalization.",
        )

    def _google_oauth_check(self) -> ReadinessCheck:
        return self._check(
            key="google_oauth",
            label="Google OAuth",
            required=True,
            env_vars=["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
            ok=bool(self._get("GOOGLE_CLIENT_ID")) and bool(self._get("GOOGLE_CLIENT_SECRET")),
            ok_detail="Google OAuth client credentials are configured.",
            fail_detail="Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET for mailbox connection.",
        )

    def _celery_agent_queue_check(self) -> ReadinessCheck:
        queues = self._get("AUTOREACH_WORKER_QUEUES") or "engine,maintenance,standard-agents"
        has_standard = "standard-agents" in {queue.strip() for queue in queues.split(",")}
        return self._check(
            key="standard_agent_queue",
            label="Agent dispatch queue",
            required=True,
            env_vars=["AUTOREACH_WORKER_QUEUES"],
            ok=has_standard,
            ok_detail="Worker queue set includes standard-agents.",
            fail_detail="Run at least one worker that consumes the standard-agents queue.",
        )

    def _phoenix_check(self) -> ReadinessCheck:
        return self._optional(
            key="phoenix_endpoint",
            label="Phoenix reasoning ledger",
            env_vars=["AUTOREACH_PHOENIX_ENDPOINT"],
            ok=bool(self._get("AUTOREACH_PHOENIX_ENDPOINT")),
            ok_detail="Phoenix OTLP endpoint is configured.",
            warn_detail="Set AUTOREACH_PHOENIX_ENDPOINT to capture OpenInference traces.",
        )

    def _intent_store_check(self) -> ReadinessCheck:
        return self._optional(
            key="intent_duckdb_path",
            label="Intent DuckDB path",
            env_vars=["AUTOREACH_INTENT_DUCKDB_PATH"],
            ok=bool(self._get("AUTOREACH_INTENT_DUCKDB_PATH")),
            ok_detail="Intent DuckDB path is configured.",
            warn_detail="Set AUTOREACH_INTENT_DUCKDB_PATH before scheduling intent ingestion.",
        )

    def _razorpay_check(self) -> ReadinessCheck:
        return self._optional(
            key="razorpay",
            label="Razorpay billing",
            env_vars=["RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"],
            ok=bool(self._get("RAZORPAY_KEY_ID")) and bool(self._get("RAZORPAY_KEY_SECRET")),
            ok_detail="Razorpay credentials are configured.",
            warn_detail="Razorpay is not configured; collect pilot payments manually or set keys.",
        )

    def _calcom_check(self) -> ReadinessCheck:
        return self._check(
            key="calcom_webhook_secret",
            label="Cal.com webhook secret",
            required=True,
            env_vars=["CALCOM_WEBHOOK_SECRET"],
            ok=bool(self._get("CALCOM_WEBHOOK_SECRET")),
            ok_detail="Cal.com webhook signing secret is configured.",
            fail_detail="Set CALCOM_WEBHOOK_SECRET so public booking webhooks are authenticated.",
        )

    def _sentry_check(self) -> ReadinessCheck:
        return self._optional(
            key="sentry",
            label="Sentry monitoring",
            env_vars=["SENTRY_DSN"],
            ok=bool(self._get("SENTRY_DSN")),
            ok_detail="Sentry DSN is configured.",
            warn_detail="Set SENTRY_DSN before pilots so runtime errors are captured.",
        )

    def _get(self, key: str) -> str:
        return str(self._env.get(key, "") or "").strip()

    @staticmethod
    def _check(
        *,
        key: str,
        label: str,
        required: bool,
        env_vars: list[str],
        ok: bool,
        ok_detail: str,
        fail_detail: str,
    ) -> ReadinessCheck:
        return ReadinessCheck(
            key=key,
            label=label,
            required=required,
            env_vars=env_vars,
            status="PASS" if ok else "FAIL",
            detail=ok_detail if ok else fail_detail,
        )

    @staticmethod
    def _optional(
        *,
        key: str,
        label: str,
        env_vars: list[str],
        ok: bool,
        ok_detail: str,
        warn_detail: str,
    ) -> ReadinessCheck:
        return ReadinessCheck(
            key=key,
            label=label,
            required=False,
            env_vars=env_vars,
            status="PASS" if ok else "WARN",
            detail=ok_detail if ok else warn_detail,
        )


def runtime_dependency_checks(*, store: Any, env: Mapping[str, str]) -> list[ReadinessCheck]:
    """Run live dependency probes without leaking connection strings or secrets."""

    return [
        database_connectivity_check(store),
        redis_connectivity_check(env),
        celery_worker_queue_check(env),
    ]


def database_connectivity_check(store: Any) -> ReadinessCheck:
    holder = getattr(store, "_holder", None)
    conn_factory = getattr(holder, "conn", None)
    if not callable(conn_factory):
        return ReadinessCheck(
            key="database_connectivity",
            label="Database connectivity",
            status="FAIL",
            required=True,
            detail="Database connection probe is unavailable in this runtime.",
        )

    try:
        with conn_factory() as conn:
            conn.execute(text("SELECT 1")).scalar()
    except Exception as exc:
        return ReadinessCheck(
            key="database_connectivity",
            label="Database connectivity",
            status="FAIL",
            required=True,
            detail=f"Database SELECT 1 probe failed ({exc.__class__.__name__}).",
        )

    return ReadinessCheck(
        key="database_connectivity",
        label="Database connectivity",
        status="PASS",
        required=True,
        detail="Database connection accepted a SELECT 1 probe.",
    )


def redis_connectivity_check(env: Mapping[str, str]) -> ReadinessCheck:
    redis_url = str(env.get("REDIS_URL", "") or "").strip()
    if not redis_url:
        return ReadinessCheck(
            key="redis_connectivity",
            label="Redis connectivity",
            status="FAIL",
            required=True,
            env_vars=["REDIS_URL"],
            detail="REDIS_URL is not configured, so Redis cannot be pinged.",
        )

    client: Any | None = None
    try:
        import redis

        client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
    except Exception as exc:
        return ReadinessCheck(
            key="redis_connectivity",
            label="Redis connectivity",
            status="FAIL",
            required=True,
            env_vars=["REDIS_URL"],
            detail=f"Redis PING probe failed ({exc.__class__.__name__}).",
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    return ReadinessCheck(
        key="redis_connectivity",
        label="Redis connectivity",
        status="PASS",
        required=True,
        env_vars=["REDIS_URL"],
        detail="Redis accepted a PING probe.",
    )


def celery_worker_queue_check(
    env: Mapping[str, str],
    *,
    celery_app: Any | None = None,
) -> ReadinessCheck:
    required_queues = _required_worker_queues(env)
    try:
        if celery_app is None:
            from engine.worker.celery_app import celery_app as resolved_app
        else:
            resolved_app = celery_app
        inspector = resolved_app.control.inspect(timeout=1.0)
        active = inspector.active_queues() or {}
    except Exception as exc:
        return ReadinessCheck(
            key="celery_worker_queues",
            label="Celery worker queues",
            status="FAIL",
            required=True,
            env_vars=["REDIS_URL", "AUTOREACH_WORKER_QUEUES"],
            detail=f"Celery worker inspection failed ({exc.__class__.__name__}).",
        )

    if not active:
        return ReadinessCheck(
            key="celery_worker_queues",
            label="Celery worker queues",
            status="FAIL",
            required=True,
            env_vars=["REDIS_URL", "AUTOREACH_WORKER_QUEUES"],
            detail="No Celery workers responded to queue inspection.",
        )

    observed = _observed_worker_queues(active)
    missing = sorted(required_queues - observed)
    if missing:
        return ReadinessCheck(
            key="celery_worker_queues",
            label="Celery worker queues",
            status="FAIL",
            required=True,
            env_vars=["REDIS_URL", "AUTOREACH_WORKER_QUEUES"],
            detail=f"Celery workers are missing required queue(s): {', '.join(missing)}.",
        )

    return ReadinessCheck(
        key="celery_worker_queues",
        label="Celery worker queues",
        status="PASS",
        required=True,
        env_vars=["REDIS_URL", "AUTOREACH_WORKER_QUEUES"],
        detail=f"Celery workers consume required queue(s): {', '.join(sorted(required_queues))}.",
    )


def _required_worker_queues(env: Mapping[str, str]) -> set[str]:
    configured = str(
        env.get("AUTOREACH_WORKER_QUEUES", "engine,maintenance,standard-agents") or ""
    )
    queues = {queue.strip() for queue in configured.split(",") if queue.strip()}
    return queues or {"engine", "maintenance", "standard-agents"}


def _observed_worker_queues(active_queues: Mapping[str, Any]) -> set[str]:
    observed: set[str] = set()
    for queues in active_queues.values():
        if not isinstance(queues, list):
            continue
        for queue in queues:
            if isinstance(queue, Mapping):
                name = queue.get("name")
            else:
                name = getattr(queue, "name", None)
            if name:
                observed.add(str(name))
    return observed
