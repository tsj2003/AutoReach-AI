from cockpit.services.readiness import (
    ProductionReadiness,
    celery_worker_queue_check,
    database_connectivity_check,
    redis_connectivity_check,
)

FERNET_KEY = "EFONWtQiHXh-5vpx9TVH0qCuVCkqUgJutdYjRM3J_iE="


def _status_by_key(report):
    return {check.key: check.status for check in report.checks}


def test_readiness_fails_closed_for_missing_required_env():
    report = ProductionReadiness(env={}).evaluate()

    assert report.is_production_ready is False
    statuses = _status_by_key(report)
    assert statuses["database_url"] == "FAIL"
    assert statuses["redis_url"] == "FAIL"
    assert statuses["jwt_secret"] == "FAIL"
    assert statuses["credential_encryption_key"] == "FAIL"
    assert statuses["legacy_console_disabled"] == "FAIL"
    assert statuses["smart_runtime_dispatch"] == "FAIL"
    assert "database_url" in report.missing_required


def test_readiness_passes_required_env_and_warns_optional():
    report = ProductionReadiness(
        env={
            "DATABASE_URL": "postgresql://user:pass@host/db",
            "REDIS_URL": "redis://redis:6379/0",
            "AUTOREACH_JWT_SECRET": "x" * 40,
            "AUTOREACH_SESSION_SECRET": "y" * 40,
            "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY": FERNET_KEY,
            "AUTOREACH_ENABLE_CONSOLE": "0",
            "AUTOREACH_RUNTIME_SMART_DISPATCH": "1",
            "GEMINI_API_KEY": "gemini-secret",
            "GOOGLE_CLIENT_ID": "google-client",
            "GOOGLE_CLIENT_SECRET": "google-secret",
            "CALCOM_WEBHOOK_SECRET": "cal-secret",
            "AUTOREACH_WORKER_QUEUES": "engine,maintenance,standard-agents",
        }
    ).evaluate()

    assert report.is_production_ready is True
    assert report.missing_required == []
    statuses = _status_by_key(report)
    assert statuses["standard_agent_queue"] == "PASS"
    assert statuses["smart_runtime_dispatch"] == "PASS"
    assert statuses["phoenix_endpoint"] == "WARN"


def test_readiness_does_not_expose_secret_values():
    secret = "super-secret-value-that-must-not-render"
    report = ProductionReadiness(
        env={
            "DATABASE_URL": "postgresql://user:pass@host/db",
            "REDIS_URL": "redis://redis:6379/0",
            "AUTOREACH_JWT_SECRET": secret,
            "AUTOREACH_SESSION_SECRET": secret,
            "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY": FERNET_KEY,
            "AUTOREACH_ENABLE_CONSOLE": "0",
            "AUTOREACH_RUNTIME_SMART_DISPATCH": "1",
            "GEMINI_API_KEY": secret,
            "GOOGLE_CLIENT_ID": secret,
            "GOOGLE_CLIENT_SECRET": secret,
            "CALCOM_WEBHOOK_SECRET": secret,
        }
    ).evaluate()

    rendered = report.model_dump_json()
    assert secret not in rendered


def test_database_connectivity_check_passes_for_live_store(tmp_path):
    from engine import open_storage

    store, _events, _ledger = open_storage(f"sqlite:///{tmp_path / 'probe.db'}")

    check = database_connectivity_check(store)

    assert check.key == "database_connectivity"
    assert check.status == "PASS"
    assert "SELECT 1" in check.detail


def test_redis_connectivity_check_uses_ping_without_leaking_url(monkeypatch):
    import redis

    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            return None

    secret_url = "redis://:super-secret-password@redis.example.com:6379/0"
    monkeypatch.setattr(redis.Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())

    check = redis_connectivity_check({"REDIS_URL": secret_url})

    assert check.key == "redis_connectivity"
    assert check.status == "PASS"
    assert secret_url not in check.model_dump_json()


def test_readiness_can_include_required_runtime_failures():
    report = ProductionReadiness(
        env={
            "DATABASE_URL": "postgresql://user:pass@host/db",
            "REDIS_URL": "redis://redis:6379/0",
            "AUTOREACH_JWT_SECRET": "x" * 40,
            "AUTOREACH_SESSION_SECRET": "y" * 40,
            "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY": FERNET_KEY,
            "AUTOREACH_ENABLE_CONSOLE": "0",
            "AUTOREACH_RUNTIME_SMART_DISPATCH": "1",
            "GEMINI_API_KEY": "gemini-secret",
            "GOOGLE_CLIENT_ID": "google-client",
            "GOOGLE_CLIENT_SECRET": "google-secret",
            "CALCOM_WEBHOOK_SECRET": "cal-secret",
            "AUTOREACH_WORKER_QUEUES": "engine,maintenance,standard-agents",
        }
    ).evaluate(extra_checks=[
        redis_connectivity_check({"REDIS_URL": ""}),
    ])

    assert report.is_production_ready is False
    assert "redis_connectivity" in report.missing_required


class _FakeCeleryControl:
    def __init__(self, active_queues):
        self._active_queues = active_queues

    def inspect(self, timeout=1.0):
        return self

    def active_queues(self):
        return self._active_queues


class _FakeCeleryApp:
    def __init__(self, active_queues):
        self.control = _FakeCeleryControl(active_queues)


def test_celery_worker_queue_check_passes_for_required_queues():
    check = celery_worker_queue_check(
        {"AUTOREACH_WORKER_QUEUES": "engine,maintenance,standard-agents"},
        celery_app=_FakeCeleryApp({
            "worker-1": [
                {"name": "engine"},
                {"name": "maintenance"},
                {"name": "standard-agents"},
            ],
        }),
    )

    assert check.key == "celery_worker_queues"
    assert check.status == "PASS"
    assert "standard-agents" in check.detail


def test_celery_worker_queue_check_fails_when_queue_missing():
    check = celery_worker_queue_check(
        {"AUTOREACH_WORKER_QUEUES": "engine,maintenance,standard-agents"},
        celery_app=_FakeCeleryApp({
            "worker-1": [
                {"name": "engine"},
                {"name": "maintenance"},
            ],
        }),
    )

    assert check.status == "FAIL"
    assert "standard-agents" in check.detail
