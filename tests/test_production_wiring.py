"""Production wiring: Postgres URL handling, ASGI entrypoint, Celery tasks."""

from __future__ import annotations

import os


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


def test_asgi_app_builds():
    import asgi
    from fastapi import FastAPI
    assert isinstance(asgi.app, FastAPI)


def test_celery_tasks_registered():
    from engine.worker import celery_app
    tasks = set(celery_app.tasks.keys())
    assert "engine.tick_engagement" in tasks
    assert "engine.poll_replies" in tasks
    assert "engine.tick_all_active" in tasks
    assert "engine.reset_daily_caps" in tasks
    assert "engine.warmup_tick_all" in tasks


def test_celery_beat_schedule_configured():
    from engine.worker import celery_app
    sched = celery_app.conf.beat_schedule
    assert "tick-all-active" in sched
    assert "reset-daily-caps" in sched
    assert "warmup-tick-all" in sched
