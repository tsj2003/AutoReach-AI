"""
The legacy Jinja operator console is unauthenticated and not tenant-scoped, so
it must be off in production. These tests pin that behavior:

* `/` always redirects to the customer-facing React app at `/app/`.
* Secure by default: with the env unset, the console is ON only for a local
  sqlite dev DB and OFF for any real (non-sqlite) database.
* AUTOREACH_ENABLE_CONSOLE always wins when set explicitly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cockpit.app import _console_enabled_from_env


def _make_client(tmp_path, name):
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / name}")
    # follow_redirects=False so we can assert on the 302 itself.
    return TestClient(app, raise_server_exceptions=True, follow_redirects=False)


def test_root_redirects_to_react_app(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOREACH_ENABLE_CONSOLE", raising=False)
    client = _make_client(tmp_path, "root.db")
    r = client.get("/")
    assert r.status_code == 302
    assert r.headers["location"] == "/app/"


def test_console_disabled_returns_404(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    client = _make_client(tmp_path, "noconsole.db")
    r = client.get("/engagements")
    assert r.status_code == 404


def test_console_default_is_secure_for_real_databases(monkeypatch):
    """Pure-helper contract: the console never auto-enables on a real database."""
    monkeypatch.delenv("AUTOREACH_ENABLE_CONSOLE", raising=False)
    assert _console_enabled_from_env("postgresql://user:pw@db:5432/prod") is False
    assert _console_enabled_from_env("postgres://user:pw@db:5432/prod") is False
    # Local sqlite dev is the one convenience exception.
    assert _console_enabled_from_env("sqlite:///autoreach_engine.db") is True
    # Explicit env always wins, both ways.
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "1")
    assert _console_enabled_from_env("postgresql://x") is True
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    assert _console_enabled_from_env("sqlite:///x.db") is False


def test_console_enabled_by_default_on_local_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOREACH_ENABLE_CONSOLE", raising=False)
    client = _make_client(tmp_path, "console.db")
    r = client.get("/engagements")
    # Reachable (renders HTML) on a local sqlite dev DB — not a 404.
    assert r.status_code == 200


def test_api_still_works_when_console_disabled(tmp_path, monkeypatch):
    """Disabling the console must not affect the JSON API the SPA relies on."""
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    client = _make_client(tmp_path, "apionly.db")
    r = client.post("/api/auth/signup", json={
        "email": "founder@acme.com", "password": "Password1!", "company_name": "Acme",
    })
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_legacy_oauth_disabled_with_console_but_mailbox_api_remains(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    client = _make_client(tmp_path, "nolegacyoath.db")

    assert client.get("/oauth/google/start").status_code == 404
    assert client.get("/oauth/status").status_code == 404
    assert client.get("/api/mailboxes").status_code in {401, 403}


def test_openapi_schema_is_not_public(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    client = _make_client(tmp_path, "noopenapi.db")

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
