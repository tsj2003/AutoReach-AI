"""Production wiring: Postgres URL handling, ASGI entrypoint, Celery tasks."""

from __future__ import annotations

import os

FERNET_KEY = "EFONWtQiHXh-5vpx9TVH0qCuVCkqUgJutdYjRM3J_iE="


def test_postgres_scheme_rewrite(monkeypatch):
    """open_storage rewrites postgres:// → postgresql:// (Render/Heroku quirk).
    We can't connect to a real PG here, so we assert the engine URL is rewritten
    by intercepting create_engine."""
    import engine.storage.sqlite as mod

    captured = {}
    real_create = mod.create_engine

    def fake_create(url, **kw):
        captured["url"] = url
        # Build a throwaway sqlite engine so the rest of open_storage works.
        return real_create("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False})

    monkeypatch.setattr(mod, "create_engine", fake_create)
    mod.open_storage("postgres://user:pass@host:5432/db")
    assert captured["url"].startswith("postgresql://")


def test_asgi_app_builds(monkeypatch, tmp_path):
    """The ASGI entrypoint builds a FastAPI app. Force SQLite so this test
    never depends on a reachable Postgres (CI sets DATABASE_URL globally)."""
    import importlib
    import sys

    monkeypatch.setenv("AUTOREACH_DB", f"sqlite:///{tmp_path / 'asgi.db'}")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # Re-import asgi fresh so it picks up the overridden env.
    sys.modules.pop("asgi", None)
    asgi = importlib.import_module("asgi")

    from fastapi import FastAPI
    assert isinstance(asgi.app, FastAPI)


def test_readyz_reports_required_env_status(monkeypatch, tmp_path):
    from cockpit import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("AUTOREACH_SESSION_SECRET", "y" * 40)
    monkeypatch.setenv("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", "cal-secret")

    app = create_app(db_url=f"sqlite:///{tmp_path / 'readyz.db'}")
    response = TestClient(app).get("/readyz")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["missing_required"] == []


def test_readyz_deep_mode_checks_runtime_dependencies(monkeypatch, tmp_path):
    import importlib
    import redis
    from cockpit import create_app
    from fastapi.testclient import TestClient

    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            return None

    class FakeInspect:
        def active_queues(self):
            return {
                "worker-1": [
                    {"name": "engine"},
                    {"name": "maintenance"},
                    {"name": "standard-agents"},
                ],
            }

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("AUTOREACH_SESSION_SECRET", "y" * 40)
    monkeypatch.setenv("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", "cal-secret")
    monkeypatch.setenv("AUTOREACH_WORKER_QUEUES", "engine,maintenance,standard-agents")
    monkeypatch.setattr(redis.Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())
    celery_module = importlib.import_module("engine.worker.celery_app")
    monkeypatch.setattr(celery_module.celery_app.control, "inspect", lambda timeout=1.0: FakeInspect())

    app = create_app(db_url=f"sqlite:///{tmp_path / 'readyz_deep.db'}")
    response = TestClient(app).get("/readyz?deep=true")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["missing_required"] == []


def test_create_app_defaults_to_database_url(monkeypatch):
    import cockpit.app as app_module

    captured = {}

    def fake_open_storage(db_url):
        captured["db_url"] = db_url
        raise RuntimeError("stop after db_url capture")

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    monkeypatch.setenv("AUTOREACH_DB", "sqlite:///should-not-win.db")
    monkeypatch.setattr(app_module, "open_storage", fake_open_storage)

    try:
        app_module.create_app()
    except RuntimeError as exc:
        assert str(exc) == "stop after db_url capture"

    assert captured["db_url"] == "postgresql://user:pass@host/db"


def test_create_app_uses_smart_runtime_dispatch_when_enabled(monkeypatch, tmp_path):
    from cockpit import create_app
    from engine.dispatch import SmartRoutedEmailAdapter
    from engine.services.reply_detector import TenantMailboxReplyDetector

    monkeypatch.setenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "1")
    app = create_app(db_url=f"sqlite:///{tmp_path / 'smart_app.db'}")

    assert isinstance(app.state.email_adapter, SmartRoutedEmailAdapter)
    assert app.state.email_adapter_info["kind"] == "smart_router"
    assert isinstance(app.state.reply_detector, TenantMailboxReplyDetector)


def test_celery_tasks_registered():
    from engine.worker import celery_app
    tasks = set(celery_app.tasks.keys())
    assert "engine.tick_engagement" in tasks
    assert "engine.poll_replies" in tasks
    assert "engine.intent_ingest_campaign" in tasks
    assert "engine.tick_all_active" in tasks
    assert "engine.reset_daily_caps" in tasks
    assert "engine.warmup_tick_all" in tasks
    assert "engine.tasks.dispatch_agent_task" in tasks


def test_tick_engagement_task_is_engagement_scoped(monkeypatch):
    import importlib

    celery_module = importlib.import_module("engine.worker.celery_app")

    class FakeRuntime:
        def __init__(self):
            self.calls = []

        def tick(self, **kwargs):
            self.calls.append(kwargs)
            return {"planned": 0, "executed": 0}

    fake_runtime = FakeRuntime()
    monkeypatch.setattr(
        celery_module,
        "_build_runtime",
        lambda: (fake_runtime, None, None, None),
    )

    result = celery_module.tick_engagement.run("cmp-scoped")

    assert result == {"planned": 0, "executed": 0}
    assert fake_runtime.calls == [{"engagement_id": "cmp-scoped"}]


def test_poll_replies_uses_tenant_mailbox_detector_when_smart_dispatch_enabled(monkeypatch):
    import importlib

    celery_module = importlib.import_module("engine.worker.celery_app")
    captured = {}

    class FakeDetector:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def poll(self, engagement_id):
            captured["engagement_id"] = engagement_id

            class Result:
                replies_recorded = 2
                prospects_scanned = 3

            return Result()

    monkeypatch.setenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "1")
    monkeypatch.setattr(celery_module, "_build_runtime", lambda: (None, "store", "events", "ledger"))
    monkeypatch.setattr("engine.services.TenantMailboxReplyDetector", FakeDetector)

    result = celery_module.poll_replies.run("cmp-replies")

    assert result == {"replies_recorded": 2, "scanned": 3}
    assert captured["engagement_id"] == "cmp-replies"
    assert captured["kwargs"]["store"] == "store"


def test_mailbox_daily_reset_covers_tenants_without_engagements(monkeypatch, tmp_path):
    import importlib
    from datetime import datetime, timezone

    from engine import open_storage
    from engine.auth.mailbox_models import Mailbox

    celery_module = importlib.import_module("engine.worker.celery_app")
    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'reset_mailboxes.db'}")
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(
        id="mbx-no-campaign",
        tenant_id="tenant-no-campaign",
        email_address="sender@example.com",
        emails_sent_today=7,
        created_at=now,
        updated_at=now,
    ))
    monkeypatch.setattr(celery_module, "_build_runtime", lambda: (None, store, events, ledger))

    result = celery_module.reset_daily_caps.run()

    assert result == {"reset": 1}
    refreshed = store.get_mailbox("mbx-no-campaign")
    assert refreshed.emails_sent_today == 0
    assert refreshed.last_send_reset is not None


def test_mailbox_warmup_covers_tenants_without_engagements(monkeypatch, tmp_path):
    import importlib
    from datetime import datetime, timezone

    from engine import open_storage
    from engine.auth.mailbox_models import Mailbox

    celery_module = importlib.import_module("engine.worker.celery_app")
    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'warmup_mailboxes.db'}")
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(
        id="mbx-warming",
        tenant_id="tenant-no-campaign",
        email_address="sender@example.com",
        status="warming",
        warmup_day=0,
        created_at=now,
        updated_at=now,
    ))
    monkeypatch.setattr(celery_module, "_build_runtime", lambda: (None, store, events, ledger))

    result = celery_module.warmup_tick_all.run()

    assert result == {"advanced": 1}
    refreshed = store.get_mailbox("mbx-warming")
    assert refreshed.warmup_day == 1
    assert refreshed.max_emails_per_day > 0


def test_celery_beat_schedule_configured():
    from engine.worker import celery_app
    sched = celery_app.conf.beat_schedule
    assert "tick-all-active" in sched
    assert "reset-daily-caps" in sched
    assert "warmup-tick-all" in sched


def test_render_worker_consumes_agent_dispatch_queue():
    from pathlib import Path

    text = Path("render.yaml").read_text()
    worker_block = text.split("name: autoreach-worker", 1)[1].split("name: autoreach-beat", 1)[0]
    beat_block = text.split("name: autoreach-beat", 1)[1].split("\n  - type: redis", 1)[0]

    assert "-Q engine,maintenance,standard-agents" in worker_block
    assert "AUTOREACH_PHOENIX_ENDPOINT" in worker_block
    assert "AUTOREACH_INTENT_DUCKDB_PATH" in worker_block
    assert "AUTOREACH_WORKER_QUEUES" in worker_block
    assert "AUTOREACH_RUNTIME_SMART_DISPATCH" in worker_block
    assert "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY" in worker_block
    assert "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY" in beat_block


def test_procfile_worker_consumes_agent_dispatch_queue():
    from pathlib import Path

    text = Path("Procfile").read_text()
    assert "-Q engine,maintenance,standard-agents" in text


def test_legacy_console_runtime_controls_are_engagement_scoped(tmp_path):
    from cockpit import create_app
    from fastapi.testclient import TestClient

    class FakeRuntime:
        def __init__(self):
            self.calls = []

        def tick(self, **kwargs):
            self.calls.append(("tick", kwargs))
            return {"planned": 0, "executed": 0}

        def run_once(self, **kwargs):
            self.calls.append(("run_once", kwargs))
            return {"planned": 0, "executed": 0, "iterations": 1}

    app = create_app(db_url=f"sqlite:///{tmp_path / 'legacy_console.db'}")
    fake_runtime = FakeRuntime()
    app.state.runtime = fake_runtime
    client = TestClient(app, follow_redirects=False)

    assert client.post("/engagements/cmp-legacy/tick").status_code == 303
    assert client.post("/engagements/cmp-legacy/drain").status_code == 303

    assert fake_runtime.calls == [
        ("tick", {"engagement_id": "cmp-legacy"}),
        ("run_once", {"max_iters": 20, "engagement_id": "cmp-legacy"}),
    ]


def test_legacy_direct_send_scripts_have_production_escape_hatch():
    from pathlib import Path

    hr_script = Path("scripts/send_hr_outreach.py").read_text()
    direct_script = Path("scripts/send_direct.py").read_text()

    for text in (hr_script, direct_script):
        assert "AUTOREACH_ALLOW_LEGACY_DIRECT_SEND" in text
        assert "Production sends should" in text
        assert "/Users/tarandeepsinghjuneja/AutoReach-AI/token.json" not in text

    assert 'SENDER = os.getenv("AUTOREACH_GMAIL_SENDER", "")' in direct_script


def test_react_spa_deep_links_fall_back_to_index(tmp_path):
    from cockpit import create_app
    from fastapi.testclient import TestClient

    app = create_app(db_url=f"sqlite:///{tmp_path / 'spa.db'}")
    client = TestClient(app)

    response = client.get("/app/login")

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
