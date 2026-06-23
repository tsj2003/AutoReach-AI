#!/usr/bin/env python3
"""
Live production smoke test for a deployed AutoReach instance.

This intentionally targets an already-running URL. It does not fake DNS,
Redis, Postgres, Gmail, or Phoenix; it verifies the deployment surfaces that
prove those dependencies are configured and reachable.

Run:
    python3 scripts/production_smoke.py \
      --base-url https://autoreach-web.onrender.com \
      --email pilot-smoke@example.com \
      --password 'Password1!' \
      --company 'Pilot Smoke'
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request


Urlopen = Callable[[request.Request, float], Any]


@dataclass
class SmokeConfig:
    base_url: str
    email: str
    password: str
    company: str
    timeout: float = 10.0
    secret_denylist: tuple[str, ...] = ()
    calcom_webhook_secret: str | None = None
    exercise_scoped_booking_webhook: bool = False


class SmokeFailure(RuntimeError):
    pass


def run_smoke(config: SmokeConfig, *, urlopen: Urlopen = request.urlopen) -> list[str]:
    base = config.base_url.rstrip("/")
    steps: list[str] = []

    health = _get_json(urlopen, f"{base}/healthz", timeout=config.timeout)
    _assert(bool(health.get("ok")), "healthz did not return ok=true")
    _assert_no_secret_leak(health, config.secret_denylist)
    steps.append("healthz ok")

    ready = _get_json(urlopen, f"{base}/readyz", timeout=config.timeout)
    _assert(bool(ready.get("ok")), f"readyz not ok: {ready.get('missing_required')}")
    _assert_no_secret_leak(ready, config.secret_denylist)
    steps.append("readyz ok")

    deep = _get_json(urlopen, f"{base}/readyz?deep=true", timeout=config.timeout)
    _assert(bool(deep.get("ok")), f"deep readyz not ok: {deep.get('missing_required')}")
    _assert_no_secret_leak(deep, config.secret_denylist)
    steps.append("deep readyz ok")

    _assert_closed_surface(
        urlopen,
        f"{base}/engagements",
        timeout=config.timeout,
        denylist=config.secret_denylist,
        label="legacy console",
    )
    _assert_closed_surface(
        urlopen,
        f"{base}/docs",
        timeout=config.timeout,
        denylist=config.secret_denylist,
        label="interactive docs",
    )
    _assert_closed_surface(
        urlopen,
        f"{base}/redoc",
        timeout=config.timeout,
        denylist=config.secret_denylist,
        label="redoc",
    )
    _assert_closed_surface(
        urlopen,
        f"{base}/openapi.json",
        timeout=config.timeout,
        denylist=config.secret_denylist,
        label="openapi schema",
    )
    _assert_closed_surface(
        urlopen,
        f"{base}/api/operations/readiness",
        timeout=config.timeout,
        denylist=config.secret_denylist,
        label="unauthenticated operations readiness",
    )
    _assert_closed_surface(
        urlopen,
        f"{base}/oauth/google/start",
        timeout=config.timeout,
        denylist=config.secret_denylist,
        label="legacy global OAuth start",
    )
    _assert_closed_surface(
        urlopen,
        f"{base}/oauth/status",
        timeout=config.timeout,
        denylist=config.secret_denylist,
        label="legacy global OAuth status",
    )
    steps.append("public attack surface closed")

    _assert_unsigned_webhook_rejected(
        urlopen,
        f"{base}/webhooks/calcom/booking",
        timeout=config.timeout,
        denylist=config.secret_denylist,
    )
    steps.append("unsigned booking webhook rejected")
    if config.calcom_webhook_secret:
        _assert_signed_webhook_accepted(
            urlopen,
            f"{base}/webhooks/calcom/booking",
            secret=config.calcom_webhook_secret,
            timeout=config.timeout,
            denylist=config.secret_denylist,
        )
        steps.append("signed booking webhook accepted")
    elif config.exercise_scoped_booking_webhook:
        raise SmokeFailure("--exercise-scoped-booking-webhook requires --calcom-webhook-secret")

    token = _signup_or_login(
        urlopen,
        base_url=base,
        email=config.email,
        password=config.password,
        company=config.company,
        timeout=config.timeout,
    )
    _assert(token, "auth did not return an access token")
    steps.append("auth ok")

    me = _get_json(urlopen, f"{base}/api/auth/me", timeout=config.timeout, token=token)
    _assert(me.get("email") == config.email.lower(), "auth/me did not return the smoke user")
    _assert_no_secret_leak(me, config.secret_denylist)
    steps.append("auth/me ok")

    if config.exercise_scoped_booking_webhook:
        _assert_scoped_booking_webhook_books_contact(
            urlopen,
            base_url=base,
            token=token,
            secret=config.calcom_webhook_secret or "",
            timeout=config.timeout,
            denylist=config.secret_denylist,
        )
        steps.append("scoped booking webhook booked contact")

    ops_ready = _get_json(
        urlopen,
        f"{base}/api/operations/readiness?deep=true",
        timeout=config.timeout,
        token=token,
    )
    _assert(
        bool(ops_ready.get("is_production_ready")),
        f"operations readiness failed: {ops_ready.get('missing_required')}",
    )
    _assert_no_secret_leak(ops_ready, config.secret_denylist)
    _assert(
        {"database_connectivity", "redis_connectivity", "celery_worker_queues"} <= {
            check.get("key") for check in ops_ready.get("checks", [])
        },
        "operations readiness did not include deep dependency and worker checks",
    )
    steps.append("operations deep readiness ok")

    app_html = _get_text(urlopen, f"{base}/app/", timeout=config.timeout)
    _assert('id="root"' in app_html, "React SPA root was not served at /app/")
    _assert_no_secret_leak(app_html, config.secret_denylist)
    steps.append("React SPA served")

    return steps


def _signup_or_login(
    urlopen: Urlopen,
    *,
    base_url: str,
    email: str,
    password: str,
    company: str,
    timeout: float,
) -> str:
    payload = {
        "email": email.lower(),
        "password": password,
        "company_name": company,
        "full_name": "Production Smoke",
    }
    try:
        signup = _request_json(
            urlopen,
            f"{base_url}/api/auth/signup",
            method="POST",
            payload=payload,
            timeout=timeout,
        )
        return str(signup.get("access_token") or "")
    except SmokeFailure as exc:
        if "HTTP 409" not in str(exc):
            raise

    login = _request_json(
        urlopen,
        f"{base_url}/api/auth/login",
        method="POST",
        payload={"email": email.lower(), "password": password},
        timeout=timeout,
    )
    return str(login.get("access_token") or "")


def _get_json(urlopen: Urlopen, url: str, *, timeout: float, token: str | None = None) -> dict[str, Any]:
    return _request_json(urlopen, url, method="GET", timeout=timeout, token=token)


def _get_text(urlopen: Urlopen, url: str, *, timeout: float) -> str:
    req = request.Request(url, method="GET")
    try:
        with urlopen(req, timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"GET {url} failed with HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise SmokeFailure(f"GET {url} failed: {exc.__class__.__name__}") from exc


def _request_json(
    urlopen: Urlopen,
    url: str,
    *,
    method: str,
    timeout: float,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"{method} {url} failed with HTTP {exc.code}: {raw}") from exc
    except Exception as exc:
        raise SmokeFailure(f"{method} {url} failed: {exc.__class__.__name__}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"{method} {url} did not return JSON") from exc
    _assert(isinstance(parsed, dict), f"{method} {url} returned non-object JSON")
    return parsed


def _assert_closed_surface(
    urlopen: Urlopen,
    url: str,
    *,
    timeout: float,
    denylist: tuple[str, ...],
    label: str,
) -> None:
    status, body = _get_status_and_body(urlopen, url, timeout=timeout)
    _assert_no_secret_leak(body, denylist)
    _assert(
        status in {401, 403, 404},
        f"{label} was reachable without protection (HTTP {status})",
    )


def _assert_unsigned_webhook_rejected(
    urlopen: Urlopen,
    url: str,
    *,
    timeout: float,
    denylist: tuple[str, ...],
) -> None:
    payload = {
        "triggerEvent": "BOOKING_CREATED",
        "payload": {
            "uid": "production-smoke-unsigned",
            "title": "Unsigned Smoke Probe",
            "startTime": "2026-06-01T15:00:00Z",
            "attendees": [{"email": "unsigned-smoke@example.invalid"}],
        },
    }
    status, body = _status_and_body(
        urlopen,
        url,
        method="POST",
        body=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    _assert_no_secret_leak(body, denylist)
    _assert(
        status in {401, 403, 503},
        f"unsigned booking webhook was accepted or exposed unsafely (HTTP {status})",
    )


def _assert_signed_webhook_accepted(
    urlopen: Urlopen,
    url: str,
    *,
    secret: str,
    timeout: float,
    denylist: tuple[str, ...],
) -> None:
    payload = {
        "triggerEvent": "BOOKING_CREATED",
        "payload": {
            "uid": "production-smoke-signed",
            "title": "Signed Smoke Probe",
            "startTime": "2026-06-01T15:00:00Z",
            "attendees": [{"email": "signed-smoke@example.invalid"}],
            "metadata": {
                "tenant_id": "production-smoke",
                "engagement_id": "production-smoke",
            },
        },
    }
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    status, response_body = _status_and_body(
        urlopen,
        url,
        method="POST",
        body=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Cal-Signature-256": f"sha256={signature}",
        },
        timeout=timeout,
    )
    _assert_no_secret_leak(response_body, denylist)
    _assert(status == 200, f"signed booking webhook was rejected (HTTP {status})")
    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise SmokeFailure("signed booking webhook did not return JSON") from exc
    _assert(parsed.get("ok") is True, "signed booking webhook did not return ok=true")
    _assert(parsed.get("matched") is False, "signed smoke webhook unexpectedly matched a real booking")


def _assert_scoped_booking_webhook_books_contact(
    urlopen: Urlopen,
    *,
    base_url: str,
    token: str,
    secret: str,
    timeout: float,
    denylist: tuple[str, ...],
) -> None:
    unique = str(int(time.time()))
    campaign_id: str | None = None
    contact_id: str | None = None
    contact_email = f"calcom-smoke-{unique}@example.invalid"

    try:
        campaign = _request_json(
            urlopen,
            f"{base_url}/api/campaigns",
            method="POST",
            payload={
                "customer_name": f"Cal.com Smoke {unique}",
                "offer": "Production webhook smoke test.",
                "icp_description": "Disposable smoke contact.",
                "booking_url": "https://cal.com/autoreach-smoke",
                "client_cure": "Verifies scoped booking webhooks.",
                "allowed_signal_types": ["smoke"],
                "price_per_outcome_cents": 100,
                "monthly_budget_cents": 1000,
                "hitl_threshold": 1,
            },
            timeout=timeout,
            token=token,
        )
        campaign_id = str(campaign.get("id") or "")
        _assert(campaign_id, "smoke campaign creation did not return an id")
        _assert_no_secret_leak(campaign, denylist)

        contact = _request_json(
            urlopen,
            f"{base_url}/api/contacts",
            method="POST",
            payload={
                "campaign_id": campaign_id,
                "email": contact_email,
                "full_name": "Cal.com Smoke",
                "company": "AutoReach Smoke",
            },
            timeout=timeout,
            token=token,
        )
        contact_id = str(contact.get("id") or "")
        _assert(contact_id, "smoke contact creation did not return an id")
        _assert_no_secret_leak(contact, denylist)

        payload = {
            "triggerEvent": "BOOKING_CREATED",
            "payload": {
                "uid": f"production-smoke-scoped-{unique}",
                "title": "Scoped Booking Smoke Probe",
                "startTime": "2026-06-01T15:00:00Z",
                "attendees": [{"email": contact_email, "name": "Cal.com Smoke"}],
                "metadata": {"engagement_id": campaign_id},
            },
        }
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        status, response_body = _status_and_body(
            urlopen,
            f"{base_url}/webhooks/calcom/booking",
            method="POST",
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Cal-Signature-256": f"sha256={signature}",
            },
            timeout=timeout,
        )
        _assert_no_secret_leak(response_body, denylist)
        _assert(status == 200, f"scoped signed booking webhook was rejected (HTTP {status})")
        try:
            webhook_result = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise SmokeFailure("scoped signed booking webhook did not return JSON") from exc
        _assert(webhook_result.get("matched") is True, "scoped signed booking webhook did not match the smoke contact")

        refreshed = _get_json(
            urlopen,
            f"{base_url}/api/contacts/{contact_id}",
            timeout=timeout,
            token=token,
        )
        _assert(refreshed.get("status") == "booked", "smoke contact was not marked booked after webhook")
        _assert_no_secret_leak(refreshed, denylist)
    finally:
        if campaign_id:
            try:
                _status_and_body(
                    urlopen,
                    f"{base_url}/api/campaigns/{campaign_id}",
                    method="DELETE",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=timeout,
                )
            except SmokeFailure:
                pass


def _get_status_and_body(urlopen: Urlopen, url: str, *, timeout: float) -> tuple[int, str]:
    return _status_and_body(urlopen, url, method="GET", timeout=timeout)


def _status_and_body(
    urlopen: Urlopen,
    url: str,
    *,
    method: str,
    timeout: float,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    req = request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout) as response:
            status = _response_status(response)
            body = response.read().decode("utf-8", errors="replace")
            return status, body
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body
    except Exception as exc:
        raise SmokeFailure(f"{method} {url} failed: {exc.__class__.__name__}") from exc


def _response_status(response: Any) -> int:
    getcode = getattr(response, "getcode", None)
    if callable(getcode):
        return int(getcode())
    status = getattr(response, "status", None)
    return int(status or 200)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _assert_no_secret_leak(value: Any, denylist: tuple[str, ...]) -> None:
    rendered = json.dumps(value, default=str) if not isinstance(value, str) else value
    for secret in denylist:
        if secret and secret in rendered:
            raise SmokeFailure("response leaked a configured secret value")


def _load_config(argv: list[str]) -> SmokeConfig:
    parser = argparse.ArgumentParser(description="Smoke-test a live AutoReach deployment.")
    parser.add_argument("--base-url", default=os.getenv("AUTOREACH_SMOKE_BASE_URL", ""))
    parser.add_argument("--email", default=os.getenv("AUTOREACH_SMOKE_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("AUTOREACH_SMOKE_PASSWORD", ""))
    parser.add_argument("--company", default=os.getenv("AUTOREACH_SMOKE_COMPANY", "Production Smoke"))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("AUTOREACH_SMOKE_TIMEOUT", "10")))
    parser.add_argument(
        "--calcom-webhook-secret",
        default=os.getenv("AUTOREACH_SMOKE_CALCOM_SECRET", ""),
        help="Optional Cal.com webhook secret used to prove the signed live webhook path.",
    )
    parser.add_argument(
        "--exercise-scoped-booking-webhook",
        action="store_true",
        default=os.getenv("AUTOREACH_SMOKE_EXERCISE_SCOPED_BOOKING_WEBHOOK", "").strip().lower()
        in {"1", "true", "yes", "on"},
        help="Create a disposable campaign/contact and prove a signed scoped Cal.com webhook books it.",
    )
    parser.add_argument(
        "--secret-denylist",
        default=os.getenv("AUTOREACH_SMOKE_SECRET_DENYLIST", ""),
        help="Comma-separated secret values that must not appear in responses.",
    )
    args = parser.parse_args(argv)

    missing = [
        name for name, value in (
            ("--base-url", args.base_url),
            ("--email", args.email),
            ("--password", args.password),
        )
        if not value
    ]
    if missing:
        parser.error(f"missing required values: {', '.join(missing)}")

    return SmokeConfig(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        company=args.company,
        timeout=args.timeout,
        secret_denylist=tuple(
            secret.strip() for secret in args.secret_denylist.split(",") if secret.strip()
        ),
        calcom_webhook_secret=args.calcom_webhook_secret.strip() or None,
        exercise_scoped_booking_webhook=bool(args.exercise_scoped_booking_webhook),
    )


def main(argv: list[str] | None = None) -> int:
    config = _load_config(list(argv or sys.argv[1:]))
    print(f"\n=== AutoReach production smoke: {config.base_url.rstrip('/')} ===\n")
    try:
        steps = run_smoke(config)
    except SmokeFailure as exc:
        print(f"  FAIL {exc}")
        return 1

    for step in steps:
        print(f"  OK {step}")
    print(f"\nProduction smoke passed at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
