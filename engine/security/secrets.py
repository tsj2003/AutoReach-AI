"""Small field-encryption helpers for OAuth credential blobs.

The storage layer remains backward-compatible with existing plaintext rows.
When AUTOREACH_CREDENTIAL_ENCRYPTION_KEY is configured, new writes are encrypted
using Fernet. Existing plaintext values are decrypted as-is and can be migrated
by saving the row again.
"""

from __future__ import annotations

import json
import os
from typing import Any

KEY_ENV = "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY"
SECRET_PREFIX = "enc:v1:"
JSON_MARKER = "__autoreach_encrypted__"


def _fernet():
    key = os.getenv(KEY_ENV, "").strip()
    if not key:
        return None
    from cryptography.fernet import Fernet  # type: ignore

    return Fernet(key.encode("utf-8"))


def credential_encryption_configured() -> bool:
    try:
        return _fernet() is not None
    except Exception:
        return False


def encrypt_text(value: str | None) -> str | None:
    if value is None or value == "" or value.startswith(SECRET_PREFIX):
        return value
    fernet = _fernet()
    if fernet is None:
        return value
    token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
    return SECRET_PREFIX + token


def decrypt_text(value: str | None) -> str | None:
    if value is None or not value.startswith(SECRET_PREFIX):
        return value
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError(f"{KEY_ENV} is required to decrypt stored mailbox secrets")
    token = value[len(SECRET_PREFIX):]
    return fernet.decrypt(token.encode("utf-8")).decode("utf-8")


def encrypt_json_blob(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None or value.get(JSON_MARKER):
        return value
    fernet = _fernet()
    if fernet is None:
        return dict(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        JSON_MARKER: True,
        "ciphertext": fernet.encrypt(raw).decode("utf-8"),
    }


def decrypt_json_blob(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None or not value.get(JSON_MARKER):
        return value
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError(f"{KEY_ENV} is required to decrypt stored mailbox credentials")
    raw = fernet.decrypt(str(value.get("ciphertext", "")).encode("utf-8"))
    loaded = json.loads(raw.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("decrypted credential payload was not an object")
    return loaded
