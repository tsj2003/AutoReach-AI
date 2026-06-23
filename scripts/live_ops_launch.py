#!/usr/bin/env python3
"""Operator launch planner for live AutoReach production setup.

This script does not deploy infrastructure for you. It turns the external live
ops surface area into deterministic checks and copyable commands: secrets,
Render envs, OAuth redirect, Cal.com webhook URL, DNS preflight, Phoenix wiring,
and the final deployed smoke gate.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shlex
import sys
from dataclasses import dataclass
from typing import Mapping, Optional

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class LiveOpsCheck:
    key: str
    status: str
    required: bool
    detail: str
    action: str


@dataclass(frozen=True)
class LiveOpsPlan:
    base_url: str
    domain: Optional[str]
    checks: tuple[LiveOpsCheck, ...]
    google_redirect_uri: str
    calcom_webhook_url: str
    dns_preflight_command: Optional[str]
    production_smoke_command: str
    phoenix_hint: str

    @property
    def missing_required(self) -> list[str]:
        return [check.key for check in self.checks if check.required and check.status == "FAIL"]

    @property
    def is_ready(self) -> bool:
        return not self.missing_required


def generate_live_ops_secrets() -> dict[str, str]:
    """Generate one-time production secrets for Render/env configuration."""
    return {
        "AUTOREACH_JWT_SECRET": secrets.token_urlsafe(48),
        "AUTOREACH_SESSION_SECRET": secrets.token_urlsafe(48),
        "AUTOREACH_CREDENTIAL_ENCRYPTION_KEY": Fernet.generate_key().decode("utf-8"),
        "CALCOM_WEBHOOK_SECRET": secrets.token_urlsafe(32),
    }


def _is_set(env: Mapping[str, str], key: str) -> bool:
    value = env.get(key)
    return bool(value and value.strip())


def _normalize_base_url(base_url: Optional[str], env: Mapping[str, str]) -> str:
    value = (base_url or env.get("AUTOREACH_PUBLIC_BASE_URL") or "https://YOUR_DEPLOYED_URL").strip()
    return value.rstrip("/")


def _pass_or_fail(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def _check_env(env: Mapping[str, str], key: str, *, required: bool, action: str) -> LiveOpsCheck:
    present = _is_set(env, key)
    return LiveOpsCheck(
        key=key,
        status=_pass_or_fail(present) if required else ("PASS" if present else "WARN"),
        required=required,
        detail="configured" if present else "missing",
        action=action,
    )


def _check_strong_secret(
    env: Mapping[str, str],
    key: str,
    *,
    action: str,
    dev_value: Optional[str] = None,
) -> LiveOpsCheck:
    value = env.get(key, "").strip()
    ok = bool(value) and len(value) >= 32 and value != dev_value
    if not value:
        detail = "missing"
    elif dev_value and value == dev_value:
        detail = "uses the dev fallback"
    elif len(value) < 32:
        detail = "must be at least 32 characters"
    else:
        detail = "configured"
    return LiveOpsCheck(
        key=key,
        status="PASS" if ok else "FAIL",
        required=True,
        detail=detail,
        action=action,
    )


def _check_fernet_key(env: Mapping[str, str]) -> LiveOpsCheck:
    value = env.get("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    ok = False
    if value:
        try:
            Fernet(value.encode("utf-8"))
            ok = True
        except Exception:
            ok = False
    return LiveOpsCheck(
        key="AUTOREACH_CREDENTIAL_ENCRYPTION_KEY",
        status="PASS" if ok else "FAIL",
        required=True,
        detail="configured" if ok else "must be a valid Fernet key",
        action="Use generate-secrets and set this on web, worker, and beat.",
    )


def _check_exact(
    env: Mapping[str, str],
    key: str,
    expected: str,
    *,
    required: bool,
    action: str,
) -> LiveOpsCheck:
    actual = env.get(key, "").strip()
    ok = actual == expected
    return LiveOpsCheck(
        key=key,
        status=_pass_or_fail(ok) if required else ("PASS" if ok else "WARN"),
        required=required,
        detail=f"must equal {expected!r}" if not ok else "configured",
        action=action,
    )


def _check_worker_queues(env: Mapping[str, str]) -> LiveOpsCheck:
    raw = env.get("AUTOREACH_WORKER_QUEUES", "")
    queues = {part.strip() for part in raw.split(",") if part.strip()}
    required = {"engine", "maintenance", "standard-agents"}
    missing = sorted(required - queues)
    return LiveOpsCheck(
        key="AUTOREACH_WORKER_QUEUES",
        status="PASS" if not missing else "FAIL",
        required=True,
        detail="configured" if not missing else f"missing queues: {', '.join(missing)}",
        action="Set AUTOREACH_WORKER_QUEUES=engine,maintenance,standard-agents on the worker.",
    )


def _check_base_url(base_url: str) -> LiveOpsCheck:
    ok = base_url.startswith("https://") and "YOUR_DEPLOYED_URL" not in base_url
    return LiveOpsCheck(
        key="AUTOREACH_PUBLIC_BASE_URL",
        status="PASS" if ok else "FAIL",
        required=True,
        detail="configured" if ok else "must be the deployed HTTPS origin",
        action="Set AUTOREACH_PUBLIC_BASE_URL to your Render/custom-domain HTTPS origin.",
    )


def _check_manual(key: str, action: str) -> LiveOpsCheck:
    return LiveOpsCheck(
        key=key,
        status="WARN",
        required=False,
        detail="manual external verification required",
        action=action,
    )


def _build_smoke_command(
    *,
    base_url: str,
    smoke_email: str,
    company: str,
    password_env: str,
    calcom_secret_env: str,
) -> str:
    return " ".join(
        [
            "python3",
            "scripts/production_smoke.py",
            "--base-url",
            shlex.quote(base_url),
            "--email",
            shlex.quote(smoke_email),
            "--password",
            f'"${password_env}"',
            "--company",
            shlex.quote(company),
            "--calcom-webhook-secret",
            f'"${calcom_secret_env}"',
            "--exercise-scoped-booking-webhook",
            "--secret-denylist",
            f'"$AUTOREACH_JWT_SECRET,$AUTOREACH_SESSION_SECRET,${calcom_secret_env}"',
        ]
    )


def build_live_ops_plan(
    *,
    env: Optional[Mapping[str, str]] = None,
    base_url: Optional[str] = None,
    domain: Optional[str] = None,
    smoke_email: str = "smoke@yourdomain.com",
    company: str = "Smoke Tenant",
    password_env: str = "AUTOREACH_SMOKE_PASSWORD",
    calcom_secret_env: str = "CALCOM_WEBHOOK_SECRET",
) -> LiveOpsPlan:
    env_map = dict(os.environ if env is None else env)
    normalized_base_url = _normalize_base_url(base_url, env_map)
    normalized_domain = domain.strip().lower().rstrip(".") if domain else None

    checks: list[LiveOpsCheck] = [
        _check_base_url(normalized_base_url),
        _check_env(env_map, "DATABASE_URL", required=True, action="Attach production Postgres to web, worker, and beat."),
        _check_env(env_map, "REDIS_URL", required=True, action="Attach Redis to web, worker, and beat."),
        _check_strong_secret(
            env_map,
            "AUTOREACH_JWT_SECRET",
            action="Use generate-secrets and set this in Render.",
            dev_value="CHANGE_ME_SET_AUTOREACH_JWT_SECRET_IN_ENV",
        ),
        _check_strong_secret(env_map, "AUTOREACH_SESSION_SECRET", action="Use generate-secrets and set this in Render."),
        _check_fernet_key(env_map),
        _check_exact(
            env_map,
            "AUTOREACH_ENABLE_CONSOLE",
            "0",
            required=True,
            action="Disable the legacy unauthenticated console in production.",
        ),
        _check_exact(
            env_map,
            "AUTOREACH_RUNTIME_SMART_DISPATCH",
            "1",
            required=True,
            action="Route approved sends through health-gated tenant mailboxes.",
        ),
        _check_worker_queues(env_map),
        _check_env(env_map, "GEMINI_API_KEY", required=True, action="Set Gemini API key for drafting/classification."),
        _check_env(env_map, "GOOGLE_CLIENT_ID", required=True, action="Create Google OAuth app and set client ID."),
        _check_env(env_map, "GOOGLE_CLIENT_SECRET", required=True, action="Create Google OAuth app and set client secret."),
        _check_env(env_map, "CALCOM_WEBHOOK_SECRET", required=True, action="Set this to the Cal.com webhook signing secret."),
        _check_env(env_map, password_env, required=True, action="Set a smoke-user password only in the operator shell."),
        _check_env(env_map, "AUTOREACH_PHOENIX_ENDPOINT", required=False, action="Point OTel spans at Phoenix before paid pilots."),
        _check_env(env_map, "AUTOREACH_INTENT_DUCKDB_PATH", required=False, action="Set before scheduling intent ingestion."),
        _check_env(env_map, "SENTRY_DSN", required=False, action="Set for production exception monitoring."),
        _check_manual(
            "DNS_SPF_DKIM_DMARC",
            "Run the DNS preflight command and fix SPF/MX/DMARC/DKIM before warming mailboxes.",
        ),
        _check_manual(
            "GOOGLE_OAUTH_REDIRECT_URI",
            "Add the generated mailbox callback URI to Google Cloud OAuth authorized redirect URIs.",
        ),
        _check_manual(
            "CALCOM_WEBHOOK_AND_METADATA",
            "Create the Cal.com webhook URL and include tenant_id plus engagement_id/campaign_id in booking metadata.",
        ),
        _check_manual(
            "WARMED_MAILBOXES",
            "Connect at least one tenant mailbox, keep warmup caps conservative, and verify health remains HEALTHY.",
        ),
        _check_manual(
            "PILOT_ONBOARDING",
            "Create the pilot tenant, launch checklist, approval queue, proof package, and customer Slack/email loop.",
        ),
    ]

    google_redirect_uri = f"{normalized_base_url}/api/mailboxes/connect/callback"
    calcom_webhook_url = f"{normalized_base_url}/webhooks/calcom/booking"
    dns_preflight_command = (
        f"python3 scripts/verify_dns_health.py {shlex.quote(normalized_domain)} --json"
        if normalized_domain
        else None
    )
    smoke_command = _build_smoke_command(
        base_url=normalized_base_url,
        smoke_email=smoke_email,
        company=company,
        password_env=password_env,
        calcom_secret_env=calcom_secret_env,
    )

    return LiveOpsPlan(
        base_url=normalized_base_url,
        domain=normalized_domain,
        checks=tuple(checks),
        google_redirect_uri=google_redirect_uri,
        calcom_webhook_url=calcom_webhook_url,
        dns_preflight_command=dns_preflight_command,
        production_smoke_command=smoke_command,
        phoenix_hint="Set AUTOREACH_PHOENIX_ENDPOINT to your Phoenix OTLP traces endpoint, for example https://PHOENIX_HOST/v1/traces.",
    )


def render_plan(plan: LiveOpsPlan) -> str:
    lines = [
        f"AutoReach live-ops launch plan for {plan.base_url}",
        "",
        "Checks:",
    ]
    for check in plan.checks:
        required = "required" if check.required else "manual/warn"
        lines.append(f"- [{check.status}] {check.key} ({required}): {check.detail}. {check.action}")

    lines.extend(
        [
            "",
            "Copy these into external systems:",
            f"- Google OAuth redirect URI: {plan.google_redirect_uri}",
            f"- Cal.com booking webhook URL: {plan.calcom_webhook_url}",
            "- Cal.com booking metadata: tenant_id plus engagement_id or campaign_id",
            "",
            "Commands:",
        ]
    )
    if plan.dns_preflight_command:
        lines.append(f"- DNS preflight: {plan.dns_preflight_command}")
    else:
        lines.append("- DNS preflight: provide --domain to generate this command")
    lines.append(f"- Production smoke: {plan.production_smoke_command}")
    lines.append(f"- Phoenix: {plan.phoenix_hint}")

    if plan.is_ready:
        lines.append("")
        lines.append("Required configuration checks passed. Complete the manual/warn items before inviting a pilot.")
    else:
        lines.append("")
        lines.append(f"Missing required configuration: {', '.join(plan.missing_required)}")
    return "\n".join(lines)


def _print_generated_secrets(*, dotenv: bool) -> None:
    for key, value in generate_live_ops_secrets().items():
        if dotenv:
            print(f"{key}={value}")
        else:
            print(f"export {key}={shlex.quote(value)}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the AutoReach live-ops launch plan.")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate-secrets", help="Generate one-time production secrets.")
    gen.add_argument("--dotenv", action="store_true", help="Print KEY=value instead of shell export lines.")

    plan_parser = sub.add_parser("plan", help="Render production launch checks and copyable commands.")
    plan_parser.add_argument("--base-url", help="Deployed HTTPS origin, e.g. https://app.example.com")
    plan_parser.add_argument("--domain", help="Sending domain to check with verify_dns_health.py")
    plan_parser.add_argument("--smoke-email", default="smoke@yourdomain.com")
    plan_parser.add_argument("--company", default="Smoke Tenant")
    plan_parser.add_argument("--password-env", default="AUTOREACH_SMOKE_PASSWORD")
    plan_parser.add_argument("--calcom-secret-env", default="CALCOM_WEBHOOK_SECRET")
    plan_parser.add_argument("--strict", action="store_true", help="Exit 1 when required config is missing.")

    args = parser.parse_args(argv)
    if args.command == "generate-secrets":
        _print_generated_secrets(dotenv=args.dotenv)
        return 0

    plan = build_live_ops_plan(
        base_url=args.base_url,
        domain=args.domain,
        smoke_email=args.smoke_email,
        company=args.company,
        password_env=args.password_env,
        calcom_secret_env=args.calcom_secret_env,
    )
    print(render_plan(plan))
    return 1 if args.strict and not plan.is_ready else 0


if __name__ == "__main__":
    sys.exit(main())
