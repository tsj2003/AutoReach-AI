#!/usr/bin/env python3
"""
verify_dns_health.py — pre-launch sending-domain authentication check.

Verifies that a domain is properly authenticated before it's used to send cold
email. Improperly authenticated "burner" domains land in spam and torch sender
reputation, so this gate runs before any campaign goes live.

Checks
------
  SPF    — TXT record on the apex domain containing `v=spf1`        (FAIL if missing)
  DMARC  — TXT record on `_dmarc.<domain>` containing `v=DMARC1`    (WARN if missing)
  MX     — mail exchangers, with provider detection (Google / Microsoft / other)
  DKIM   — best-effort probe of common selectors (informational)

Usage
-----
    python scripts/verify_dns_health.py example.com
    python scripts/verify_dns_health.py example.com --json

Exit codes
----------
    0  all required checks passed (SPF + MX present)
    1  a required check failed (missing SPF, or no MX)
    2  usage / resolution error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Optional

try:
    import dns.resolver  # dnspython
except ImportError:
    print("ERROR: dnspython is not installed. Run: pip install dnspython", file=sys.stderr)
    sys.exit(2)


# ── ANSI colors (only when attached to a TTY) ────────────────────────────────
class _C:
    def __init__(self, enabled: bool):
        self.G = "\033[92m" if enabled else ""
        self.Y = "\033[93m" if enabled else ""
        self.R = "\033[91m" if enabled else ""
        self.B = "\033[1m" if enabled else ""
        self.E = "\033[0m" if enabled else ""


COMMON_DKIM_SELECTORS = ["google", "selector1", "selector2", "k1", "default", "dkim", "mail"]


class _ResolutionError(RuntimeError):
    """Transient DNS resolution failure (timeout/servfail) after retries."""

PROVIDER_MX_PATTERNS = {
    "Google Workspace": ["google.com", "googlemail.com", "aspmx.l.google.com"],
    "Microsoft 365": ["protection.outlook.com", "mail.protection.outlook.com", "outlook.com"],
    "Zoho": ["zoho.com", "zoho.eu", "zohomail.com"],
    "ProtonMail": ["protonmail.ch", "proton.me"],
}


@dataclass
class CheckResult:
    domain: str
    spf_found: bool = False
    spf_record: Optional[str] = None
    dmarc_found: bool = False
    dmarc_record: Optional[str] = None
    mx_records: list = field(default_factory=list)
    mx_provider: str = "unknown"
    dkim_selectors_found: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def required_passed(self) -> bool:
        # Required for a launchable sending domain: SPF present AND at least one MX.
        return self.spf_found and bool(self.mx_records)


def _query_txt(name: str, *, retries: int = 2) -> list[str]:
    last_err = None
    for attempt in range(retries + 1):
        try:
            answers = dns.resolver.resolve(name, "TXT", lifetime=10.0)
            out = []
            for r in answers:
                txt = "".join(
                    part.decode() if isinstance(part, bytes) else str(part)
                    for part in r.strings
                )
                out.append(txt)
            return out
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return []
        except Exception as exc:  # timeout / transient — retry
            last_err = exc
            continue
    # All retries exhausted on a transient error — signal it upward.
    raise _ResolutionError(f"TXT query for {name} failed: {last_err}")


def _query_mx(domain: str, *, retries: int = 2) -> list[str]:
    last_err = None
    for attempt in range(retries + 1):
        try:
            answers = dns.resolver.resolve(domain, "MX", lifetime=10.0)
            records = sorted(answers, key=lambda r: r.preference)
            return [f"{r.preference} {str(r.exchange).rstrip('.')}" for r in records]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return []
        except Exception as exc:
            last_err = exc
            continue
    raise _ResolutionError(f"MX query for {domain} failed: {last_err}")


def _detect_provider(mx_records: list[str]) -> str:
    joined = " ".join(mx_records).lower()
    for provider, patterns in PROVIDER_MX_PATTERNS.items():
        if any(p in joined for p in patterns):
            return provider
    return "other / self-hosted" if mx_records else "none"


def check_domain(domain: str) -> CheckResult:
    domain = domain.strip().lower().rstrip(".")
    result = CheckResult(domain=domain)

    # SPF — apex TXT containing v=spf1
    try:
        for txt in _query_txt(domain):
            if "v=spf1" in txt.lower():
                result.spf_found = True
                result.spf_record = txt
                break
    except _ResolutionError as exc:
        result.errors.append(str(exc))

    # DMARC — _dmarc.<domain> TXT containing v=DMARC1
    try:
        for txt in _query_txt(f"_dmarc.{domain}"):
            if "v=dmarc1" in txt.lower():
                result.dmarc_found = True
                result.dmarc_record = txt
                break
    except _ResolutionError as exc:
        result.errors.append(str(exc))

    # MX + provider
    try:
        result.mx_records = _query_mx(domain)
    except _ResolutionError as exc:
        result.errors.append(str(exc))
    result.mx_provider = _detect_provider(result.mx_records)

    # DKIM — best-effort probe of common selectors (informational only)
    for selector in COMMON_DKIM_SELECTORS:
        try:
            recs = _query_txt(f"{selector}._domainkey.{domain}")
        except _ResolutionError:
            continue
        if any("v=dkim1" in t.lower() or "k=rsa" in t.lower() or "p=" in t for t in recs):
            result.dkim_selectors_found.append(selector)

    return result


def _print_human(r: CheckResult, c: _C) -> None:
    print(f"\n{c.B}DNS health check — {r.domain}{c.E}\n")

    # SPF (required)
    if r.spf_found:
        print(f"  {c.G}✓ SPF{c.E}    present")
        print(f"          {r.spf_record}")
    else:
        print(f"  {c.R}✗ SPF{c.E}    MISSING — emails will likely fail authentication (REQUIRED)")

    # DMARC (warn)
    if r.dmarc_found:
        print(f"  {c.G}✓ DMARC{c.E}  present")
        print(f"          {r.dmarc_record}")
    else:
        print(f"  {c.Y}⚠ DMARC{c.E}  missing — add a _dmarc TXT record (recommended for deliverability)")

    # MX (required)
    if r.mx_records:
        print(f"  {c.G}✓ MX{c.E}     routed to: {c.B}{r.mx_provider}{c.E}")
        for mx in r.mx_records:
            print(f"          {mx}")
    else:
        print(f"  {c.R}✗ MX{c.E}     no mail exchangers found (REQUIRED)")

    # DKIM (info)
    if r.dkim_selectors_found:
        print(f"  {c.G}✓ DKIM{c.E}   selector(s) found: {', '.join(r.dkim_selectors_found)}")
    else:
        print(f"  {c.Y}ℹ DKIM{c.E}   no common selector responded (set up via your ESP; selector names vary)")

    print()
    if r.required_passed:
        print(f"  {c.G}{c.B}READY{c.E} — SPF + MX present. Safe to send (add DMARC/DKIM for best results).\n")
    else:
        print(f"  {c.R}{c.B}NOT READY{c.E} — fix the REQUIRED items above before launching campaigns.\n")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify sending-domain DNS authentication.")
    parser.add_argument("domain", help="domain to check, e.g. example.com")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of human output")
    args = parser.parse_args(argv)

    try:
        result = check_domain(args.domain)
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: could not check domain: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "domain": result.domain,
            "spf": {"found": result.spf_found, "record": result.spf_record},
            "dmarc": {"found": result.dmarc_found, "record": result.dmarc_record},
            "mx": {"records": result.mx_records, "provider": result.mx_provider},
            "dkim_selectors_found": result.dkim_selectors_found,
            "ready": result.required_passed,
        }, indent=2))
    else:
        _print_human(result, _C(enabled=sys.stdout.isatty()))

    return 0 if result.required_passed else 1


if __name__ == "__main__":
    sys.exit(main())
