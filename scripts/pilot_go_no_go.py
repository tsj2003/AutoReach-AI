#!/usr/bin/env python3
"""Pilot GO/NO-GO probe — network + config honesty check (no secret printing)."""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _host_from_base(base: str) -> str:
    return base.replace("https://", "").replace("http://", "").split("/")[0]


def dns_ok(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443)
        return True
    except OSError:
        return False


def http_json(url: str, timeout: float = 10.0) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


def classify_secret(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        return "MISSING"
    if "REPLACE_WITH" in v or v.startswith("CHANGE_ME") or "change-me" in v.lower():
        return "PLACEHOLDER"
    if name.endswith("SENDER") and v == "you@yourdomain.com":
        return "PLACEHOLDER"
    return "SET"


def main() -> int:
    _load_dotenv()
    base = (
        os.getenv("AUTOREACH_PUBLIC_BASE_URL", "").strip()
        or "https://autoreach-ai-j2rdy.ondigitalocean.app"
    ).rstrip("/")
    host = _host_from_base(base)
    report = {
        "base_url": base,
        "dns_resolves": dns_ok(host),
        "healthz": None,
        "readyz": None,
        "readyz_deep": None,
        "secrets": {
            k: classify_secret(k)
            for k in (
                "AUTOREACH_JWT_SECRET",
                "AUTOREACH_SESSION_SECRET",
                "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY",
                "GEMINI_API_KEY",
                "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET",
                "HUNTER_API_KEY",
                "AUTOREACH_GMAIL_SENDER",
                "CALCOM_WEBHOOK_SECRET",
            )
        },
        "gmail_dry_run": os.getenv("AUTOREACH_GMAIL_DRY_RUN", ""),
        "verdict": "NO-GO",
        "blockers": [],
    }

    if not report["dns_resolves"]:
        report["blockers"].append("DNS_UNRESOLVED")
    else:
        code, payload = http_json(f"{base}/healthz")
        report["healthz"] = {"http": code, "ok": bool(payload and payload.get("ok"))}
        code, payload = http_json(f"{base}/readyz")
        report["readyz"] = {
            "http": code,
            "ok": bool(payload and payload.get("ok")),
            "missing_required": (payload or {}).get("missing_required"),
        }
        code, payload = http_json(f"{base}/readyz?deep=true")
        report["readyz_deep"] = {
            "http": code,
            "ok": bool(payload and payload.get("ok")),
            "missing_required": (payload or {}).get("missing_required"),
        }
        if not report["healthz"]["ok"]:
            report["blockers"].append("HEALTHZ_FAIL")
        if not (report["readyz"] or {}).get("ok"):
            report["blockers"].append("READYZ_FAIL")
        if not (report["readyz_deep"] or {}).get("ok"):
            report["blockers"].append("READYZ_DEEP_FAIL")

    for name, status in report["secrets"].items():
        if status in ("MISSING", "PLACEHOLDER") and name.startswith("AUTOREACH_"):
            report["blockers"].append(f"SECRET_{name}_{status}")

    if report["secrets"].get("AUTOREACH_GMAIL_SENDER") == "PLACEHOLDER":
        report["blockers"].append("GMAIL_SENDER_PLACEHOLDER")
    if str(report["gmail_dry_run"]).strip() in ("1", "true", "yes", "on"):
        report["blockers"].append("GMAIL_DRY_RUN_ON")
    if report["secrets"].get("HUNTER_API_KEY") != "SET":
        report["blockers"].append("HUNTER_NOT_CONFIGURED")

    # GO only if deploy healthy; Gmail/Hunter remain separately reported.
    deploy_ok = (
        report["dns_resolves"]
        and report.get("healthz", {}).get("ok")
        and report.get("readyz", {}).get("ok")
        and report.get("readyz_deep", {}).get("ok")
    )
    critical = [b for b in report["blockers"] if b.startswith(("DNS_", "HEALTHZ_", "READYZ_"))]
    report["verdict"] = "DEPLOY_OK_PENDING_GMAIL" if deploy_ok and critical == [] else "NO-GO"
    if deploy_ok and "GMAIL_DRY_RUN_ON" not in report["blockers"] and "GMAIL_SENDER_PLACEHOLDER" not in report["blockers"]:
        # Still not full GO without live send proof — honest intermediate.
        report["verdict"] = "DEPLOY_OK_GMAIL_CONFIGURED_PROOF_REQUIRED"

    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] != "NO-GO" or not critical else 1


if __name__ == "__main__":
    raise SystemExit(main())
