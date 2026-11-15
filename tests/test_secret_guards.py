"""Fail-closed guards for signing/encryption secrets.

Regression coverage for the deploy footgun where the committed placeholders
(REPLACE_WITH_GENERATED_SECRET / REPLACE_WITH_GENERATED_FERNET_KEY) would pass
the old guards and silently ship a repo-public JWT key and plaintext creds.
"""

import pytest

from engine.auth import jwt_handler
from engine.security import secrets as secrets_mod


def _make_production_like(monkeypatch):
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@db:5432/prod")


def test_production_rejects_placeholder_jwt_secret(monkeypatch):
    _make_production_like(monkeypatch)
    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "REPLACE_WITH_GENERATED_SECRET")
    with pytest.raises(jwt_handler.AuthError):
        jwt_handler.sign_jwt(
            user_id="u", tenant_id="t", email="e@x.co", role="owner", plan="pro"
        )


def test_production_rejects_empty_jwt_secret(monkeypatch):
    _make_production_like(monkeypatch)
    monkeypatch.delenv("AUTOREACH_JWT_SECRET", raising=False)
    with pytest.raises(jwt_handler.AuthError):
        jwt_handler.sign_jwt(
            user_id="u", tenant_id="t", email="e@x.co", role="owner", plan="pro"
        )


def test_production_accepts_real_jwt_secret_roundtrip(monkeypatch):
    _make_production_like(monkeypatch)
    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "s3cure-random-unique-value-4821-xyz")
    token = jwt_handler.sign_jwt(
        user_id="u", tenant_id="t-42", email="e@x.co", role="owner", plan="pro"
    )
    payload = jwt_handler.decode_jwt(token)
    assert payload["tenant_id"] == "t-42"


def test_non_production_falls_back_on_placeholder(monkeypatch):
    # Console on + sqlite => not production-like => dev fallback, no raise.
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "REPLACE_WITH_GENERATED_SECRET")
    token = jwt_handler.sign_jwt(
        user_id="u", tenant_id="t", email="e@x.co", role="owner", plan="pro"
    )
    assert jwt_handler.decode_jwt(token)["tenant_id"] == "t"


def test_encryption_guard_requires_key_in_production(monkeypatch):
    monkeypatch.delenv(secrets_mod.KEY_ENV, raising=False)
    with pytest.raises(RuntimeError):
        secrets_mod.assert_encryption_ready(production=True)


def test_encryption_guard_allows_unset_key_in_dev(monkeypatch):
    monkeypatch.delenv(secrets_mod.KEY_ENV, raising=False)
    # Should not raise in dev.
    secrets_mod.assert_encryption_ready(production=False)


def test_encryption_guard_rejects_invalid_key_everywhere(monkeypatch):
    monkeypatch.setenv(secrets_mod.KEY_ENV, "REPLACE_WITH_GENERATED_FERNET_KEY")
    with pytest.raises(RuntimeError):
        secrets_mod.assert_encryption_ready(production=False)


def test_encryption_guard_accepts_valid_fernet_key(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv(secrets_mod.KEY_ENV, Fernet.generate_key().decode())
    secrets_mod.assert_encryption_ready(production=True)


def test_encrypt_fails_closed_in_production_without_key(monkeypatch):
    """In production, missing key must refuse to write plaintext (not silently pass it)."""
    _make_production_like(monkeypatch)
    monkeypatch.delenv(secrets_mod.KEY_ENV, raising=False)
    with pytest.raises(RuntimeError):
        secrets_mod.encrypt_text("gmail-refresh-token")
    with pytest.raises(RuntimeError):
        secrets_mod.encrypt_json_blob({"refresh_token": "x"})


def test_encrypt_allows_plaintext_in_dev_without_key(monkeypatch):
    """Dev (sqlite, console on) keeps backward-compatible plaintext when no key is set."""
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///dev.db")
    monkeypatch.delenv(secrets_mod.KEY_ENV, raising=False)
    assert secrets_mod.encrypt_text("token") == "token"


def test_encrypt_roundtrip_with_valid_key(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv(secrets_mod.KEY_ENV, Fernet.generate_key().decode())
    enc = secrets_mod.encrypt_text("token")
    assert enc.startswith(secrets_mod.SECRET_PREFIX)
    assert secrets_mod.decrypt_text(enc) == "token"


def test_create_app_does_not_crash_when_encryption_unset_in_production(tmp_path, monkeypatch):
    """The encryption guard must degrade + log, NOT crash-loop the web service.

    Regression for the boot-crash risk: a production-like env with no encryption
    key (exactly what a deploy carrying the .do/app.yaml Fernet placeholder looks
    like) must still build the app so auth/dashboard/health stay up; credential
    writes fail closed at the point of use instead.
    """
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/prod")  # production-like signal
    monkeypatch.delenv(secrets_mod.KEY_ENV, raising=False)
    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "a-real-unique-secret-value-32chars-long")

    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'boot.db'}")  # storage on sqlite
    assert app is not None
