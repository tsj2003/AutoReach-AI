"""Pytest configuration — isolate test env from developer .env."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_external_email_env(monkeypatch):
    """Developer .env Gmail OAuth and live LLM keys must not turn unit tests into live API calls."""
    for key in (
        "AUTOREACH_GMAIL_TOKEN_PATH",
        "AUTOREACH_GMAIL_SENDER",
        "AUTOREACH_GMAIL_DRY_RUN",
        "AUTOREACH_PUBLIC_BASE_URL",
        "AZURE_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiter():
    """Keep auth rate-limit state from leaking across tests in one process."""
    from cockpit.api.ratelimit import reset_rate_limiter

    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture(autouse=True)
def _isolate_legacy_console_env(monkeypatch, request):
    """Legacy Jinja console + mailbox OAuth dev tests require console enabled.

    Developer .env often sets AUTOREACH_ENABLE_CONSOLE=0 which breaks
    sqlite-default console tests and localhost OAuth redirect validation.
    """
    nodeid = request.node.nodeid
    legacy_markers = (
        "test_engine_phase2",
        "test_engine_phase3",
        "test_engine_phase3_replies",
        "test_production_wiring",
        "test_m4_mailboxes",
    )
    if any(marker in nodeid for marker in legacy_markers):
        monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "1")
