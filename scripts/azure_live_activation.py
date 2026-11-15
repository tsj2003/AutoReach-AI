#!/usr/bin/env python3
"""Apply live-ops secrets/env to Azure Container Apps.

This script is intentionally boring and operator-safe:

* reads secret values from the local shell environment
* rejects placeholders / empty / example values
* writes them to Azure Container App secrets
* references those secrets as env vars on web/worker/beat
* never prints secret values
* keeps Gmail dispatch in dry-run unless --enable-real-send is explicit
* can verify live /healthz and /readyz after apply

It does not create Google OAuth credentials, Cal.com webhooks, warmed mailboxes,
or an intent feed. It applies the runtime configuration once those external
pieces exist.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable


DEFAULT_RESOURCE_GROUP = "attainly-prod-swedencentral-rg"
DEFAULT_APPS = ("attainly-web", "attainly-worker", "attainly-beat")
DEFAULT_BASE_URL = "https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io"

_PLACEHOLDER_MARKERS = (
    "REPLACE_WITH",
    "CHANGE_ME",
    "CHANGEME",
    "YOUR_",
    "TODO",
    "EXAMPLE",
    "DUMMY",
    "PLACEHOLDER",
)
_PLACEHOLDER_EXACT = {
    "x",
    "xx",
    "xxx",
    "test",
    "testing",
    "secret",
    "password",
    "changeme",
    "you@yourdomain.com",
}


@dataclass(frozen=True)
class SecretBinding:
    env_name: str
    secret_name: str
    required: bool = False


SECRET_BINDINGS: tuple[SecretBinding, ...] = (
    SecretBinding("GEMINI_API_KEY", "gemini-api-key", required=True),
    SecretBinding("GOOGLE_CLIENT_ID", "google-client-id", required=True),
    SecretBinding("GOOGLE_CLIENT_SECRET", "google-client-secret", required=True),
    SecretBinding("GOOGLE_SIGNIN_CLIENT_ID", "google-signin-client-id"),
    SecretBinding("CALCOM_WEBHOOK_SECRET", "calcom-webhook-secret", required=True),
    SecretBinding("AUTOREACH_PHOENIX_ENDPOINT", "phoenix-endpoint"),
    SecretBinding("AUTOREACH_INTENT_DUCKDB_PATH", "intent-duckdb-path"),
    SecretBinding("SENTRY_DSN", "sentry-dsn"),
    SecretBinding("POSTHOG_API_KEY", "posthog-api-key"),
    SecretBinding("FIRECRAWL_API_KEY", "firecrawl-api-key"),
    SecretBinding("RAZORPAY_KEY_ID", "razorpay-key-id"),
    SecretBinding("RAZORPAY_KEY_SECRET", "razorpay-key-secret"),
)

REQUIRED_ENV_NAMES = tuple(b.env_name for b in SECRET_BINDINGS if b.required)


def _present(value: str | None) -> bool:
    return bool(value and value.strip())


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return False
    cleaned = value.strip()
    if not cleaned:
        return False
    upper = cleaned.upper()
    if cleaned.lower() in _PLACEHOLDER_EXACT:
        return True
    return any(marker in upper for marker in _PLACEHOLDER_MARKERS)


def _classify(value: str | None) -> str:
    if not _present(value):
        return "MISSING"
    if _is_placeholder(value):
        return "PLACEHOLDER"
    return "SET"


def _run(cmd: list[str], *, dry_run: bool) -> None:
    printable = " ".join(_redact_arg(arg) for arg in cmd)
    if dry_run:
        print(f"DRY-RUN {printable}")
        return
    print(f"RUN {printable}")
    subprocess.run(cmd, check=True)


def _redact_arg(arg: str) -> str:
    if "=" not in arg:
        return arg
    key, value = arg.split("=", 1)
    sensitive_key = (
        key.endswith("-key")
        or "secret" in key.lower()
        or "token" in key.lower()
        or "client-id" in key.lower()
        or "dsn" in key.lower()
        or key.upper().endswith("_KEY")
        or key.upper().endswith("_SECRET")
        or key.upper().endswith("_ID")
    )
    if sensitive_key or value.startswith("secretref:"):
        return f"{key}=***"
    return arg


def _az_base(args: argparse.Namespace) -> list[str]:
    cmd = ["az"]
    if args.subscription:
        cmd.extend(["--subscription", args.subscription])
    return cmd


def _containerapp_cmd(args: argparse.Namespace, *parts: str) -> list[str]:
    return [*_az_base(args), "containerapp", *parts]


def _local_status(bindings: Iterable[SecretBinding]) -> tuple[list[str], list[str], list[str]]:
    missing_required: list[str] = []
    placeholder_required: list[str] = []
    missing_optional: list[str] = []
    for binding in bindings:
        status = _classify(os.getenv(binding.env_name))
        if status == "SET":
            continue
        if binding.required:
            if status == "PLACEHOLDER":
                placeholder_required.append(binding.env_name)
            else:
                missing_required.append(binding.env_name)
        elif status != "SET":
            missing_optional.append(binding.env_name)
    return missing_required, placeholder_required, missing_optional


def _selected_apps(args: argparse.Namespace) -> tuple[str, ...]:
    apps = tuple(args.apps.split(",")) if isinstance(args.apps, str) else tuple(args.apps)
    return tuple(app.strip() for app in apps if app.strip())


def check(args: argparse.Namespace) -> int:
    missing_required, placeholder_required, missing_optional = _local_status(SECRET_BINDINGS)
    print("Local activation env check:")
    for binding in SECRET_BINDINGS:
        status = _classify(os.getenv(binding.env_name))
        required = "required" if binding.required else "optional"
        print(f"- {status}: {binding.env_name} ({required})")
    print(f"- {'REAL SEND' if args.enable_real_send else 'DRY-RUN'}: AUTOREACH_GMAIL_DRY_RUN")
    if missing_optional:
        print("\nOptional missing:")
        for key in missing_optional:
            print(f"- {key}")
    blocked = False
    if placeholder_required:
        blocked = True
        print("\nRequired PLACEHOLDER (rejected):")
        for key in placeholder_required:
            print(f"- {key}")
    if missing_required:
        blocked = True
        print("\nRequired missing:")
        for key in missing_required:
            print(f"- {key}")
    if blocked:
        print("\nREFUSE / BLOCKED — export real values before apply.")
        return 1
    print("\nLocal required values look present (not printed). Ready for apply.")
    return 0


def apply(args: argparse.Namespace) -> int:
    missing_required, placeholder_required, _ = _local_status(SECRET_BINDINGS)
    if placeholder_required:
        print("Refusing to apply because required env vars are placeholders:")
        for key in placeholder_required:
            print(f"- {key}")
        return 1
    if missing_required and not args.allow_missing:
        print("Refusing to apply because required env vars are missing:")
        for key in missing_required:
            print(f"- {key}")
        print("\nExport them locally first, then rerun. Use --allow-missing only for partial staging.")
        return 1

    # Even with --allow-missing, never apply a placeholder value.
    for binding in SECRET_BINDINGS:
        if _is_placeholder(os.getenv(binding.env_name)):
            print(f"Refusing to apply placeholder value for {binding.env_name}")
            return 1

    apps = _selected_apps(args)
    if not apps:
        print("No container apps selected.")
        return 1

    public_base_url = (args.public_base_url or os.getenv("AUTOREACH_PUBLIC_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    dry_run_value = "0" if args.enable_real_send else "1"
    if args.enable_real_send:
        print("Real Gmail send is being enabled. Only do this after OAuth and warmed mailbox checks pass.")
    else:
        print("Safe mode: Gmail dispatch stays in dry-run. Use --enable-real-send for live email.")

    active_bindings = [
        binding for binding in SECRET_BINDINGS
        if _classify(os.getenv(binding.env_name)) == "SET"
    ]
    secret_args = [
        f"{binding.secret_name}={os.environ[binding.env_name].strip()}"
        for binding in active_bindings
    ]
    secret_env_args = [
        f"{binding.env_name}=secretref:{binding.secret_name}"
        for binding in active_bindings
    ]
    nonsecret_env_args = [
        "AUTOREACH_ENABLE_CONSOLE=0",
        "AUTOREACH_RUNTIME_SMART_DISPATCH=1",
        f"AUTOREACH_WORKER_QUEUES={args.worker_queues}",
        f"AUTOREACH_INTENT_HOURS_BACK={args.intent_hours_back}",
        f"AUTOREACH_PUBLIC_BASE_URL={public_base_url}",
        f"AUTOREACH_GMAIL_DRY_RUN={dry_run_value}",
    ]

    for app in apps:
        if secret_args:
            _run(
                _containerapp_cmd(
                    args,
                    "secret", "set",
                    "--name", app,
                    "--resource-group", args.resource_group,
                    "--secrets", *secret_args,
                ),
                dry_run=args.dry_run,
            )
        _run(
            _containerapp_cmd(
                args,
                "update",
                "--name", app,
                "--resource-group", args.resource_group,
                "--set-env-vars", *nonsecret_env_args, *secret_env_args,
            ),
            dry_run=args.dry_run,
        )

    print("\nNext:")
    print("python3 scripts/azure_live_activation.py verify")
    print(
        "Then (after Gmail gate unlock): "
        f"python3 scripts/production_smoke.py --base-url {public_base_url} "
        "--email \"$AUTOREACH_SMOKE_EMAIL\" --password \"$AUTOREACH_SMOKE_PASSWORD\" "
        "--company 'Production Smoke' "
        "--calcom-webhook-secret \"$CALCOM_WEBHOOK_SECRET\" "
        "--exercise-scoped-booking-webhook"
    )
    return 0


def _http_json(url: str, timeout: float = 20.0) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return int(resp.status), json.loads(body)
            except json.JSONDecodeError:
                return int(resp.status), None
    except urllib.error.HTTPError as exc:
        return int(exc.code), None
    except Exception as exc:
        print(f"REQUEST_FAIL {url} ({exc.__class__.__name__})")
        return 0, None


def _azure_env_status(args: argparse.Namespace, app: str) -> dict[str, str]:
    """Classify required env bindings on an app without printing values."""
    cmd = _containerapp_cmd(
        args,
        "show",
        "--name", app,
        "--resource-group", args.resource_group,
        "-o", "json",
    )
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(proc.stdout)
    env = (
        ((data.get("properties") or {}).get("template") or {})
        .get("containers", [{}])[0]
        .get("env")
        or []
    )
    by_name = {item.get("name"): item for item in env if item.get("name")}
    out: dict[str, str] = {}
    for binding in SECRET_BINDINGS:
        if not binding.required:
            continue
        item = by_name.get(binding.env_name)
        if not item:
            out[binding.env_name] = "MISSING"
            continue
        if item.get("secretRef"):
            # Presence of secretRef means the env is wired; do not read secret values.
            out[binding.env_name] = "SET"
        else:
            value = item.get("value")
            out[binding.env_name] = _classify(value if isinstance(value, str) else None)
    return out


def verify(args: argparse.Namespace) -> int:
    public_base_url = (args.public_base_url or os.getenv("AUTOREACH_PUBLIC_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    apps = _selected_apps(args)
    failed = False

    print(f"Verifying Azure apps in {args.resource_group}: {', '.join(apps)}")
    for app in apps:
        try:
            status = _azure_env_status(args, app)
        except subprocess.CalledProcessError as exc:
            print(f"- {app}: AZURE_SHOW_FAILED")
            failed = True
            if exc.stderr:
                # stderr may contain Azure errors but should not contain our secrets
                print(f"  az_error_class={exc.__class__.__name__}")
            continue
        bad = [k for k, v in status.items() if v != "SET"]
        if bad:
            failed = True
            print(f"- {app}: NOT READY ({', '.join(f'{k}={status[k]}' for k in bad)})")
        else:
            print(f"- {app}: READY (required app secrets referenced)")

    health_code, health = _http_json(f"{public_base_url}/healthz")
    ready_code, ready = _http_json(f"{public_base_url}/readyz?deep=true")
    health_ok = bool(health and health.get("ok"))
    ready_ok = bool(ready and ready.get("ok"))
    missing = (ready or {}).get("missing_required") if isinstance(ready, dict) else None

    print(f"\n/healthz http={health_code} ok={health_ok}")
    print(f"/readyz?deep=true http={ready_code} ok={ready_ok} missing_required={missing}")

    if not health_ok or not ready_ok:
        failed = True
        print("\nDEEP READINESS: FAIL")
        return 1

    if failed:
        print("\nAzure config incomplete even though readyz is ok — investigate.")
        return 1

    print("\nPRODUCTION SECRETS GATE: PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply Attainly live-ops activation config to Azure Container Apps.")
    parser.add_argument("--subscription", default=os.getenv("AZURE_SUBSCRIPTION_ID", ""))
    parser.add_argument("--resource-group", default=os.getenv("AZURE_RESOURCE_GROUP", DEFAULT_RESOURCE_GROUP))
    parser.add_argument("--apps", default=",".join(DEFAULT_APPS), help="Comma-separated app names. Default: web,worker,beat.")
    parser.add_argument("--public-base-url", default=os.getenv("AUTOREACH_PUBLIC_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--worker-queues", default=os.getenv("AUTOREACH_WORKER_QUEUES", "engine,maintenance,standard-agents"))
    parser.add_argument("--intent-hours-back", default=os.getenv("AUTOREACH_INTENT_HOURS_BACK", "24"))
    parser.add_argument("--enable-real-send", action="store_true", help="Set AUTOREACH_GMAIL_DRY_RUN=0. Do this only after Gmail OAuth and mailbox warmup are verified.")
    parser.add_argument("--allow-missing", action="store_true", help="Allow partial application when required env vars are missing.")
    parser.add_argument("--dry-run", action="store_true", help="Print redacted az commands without applying changes.")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Check local env var presence (rejects placeholders).")
    sub.add_parser("apply", help="Apply env/secrets to Azure Container Apps.")
    sub.add_parser("verify", help="Verify Azure app config + live /healthz + /readyz?deep=true.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args)
    if args.command == "apply":
        return apply(args)
    if args.command == "verify":
        return verify(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
