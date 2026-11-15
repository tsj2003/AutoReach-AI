"""In-House Email Finder & SMTP/MX Verifier Engine (Own-Made Prospeo / Hunter / Dropcontact).

Capabilities:
  1. Generates canonical B2B email permutations ({first}.{last}, {first}, {f}{last}, etc.)
     normalized for accents/diacritics and hyphens.
  2. Resolves live DNS MX, SPF, and DMARC records via dnspython (with mail-provider fingerprinting:
     Google Workspace, Microsoft 365, Mimecast, Proofpoint, Cloudflare, ProtonMail, Zoho).
  3. Detects disposable domains and free webmail providers.
  4. Scrapes public company pages (/contact, /about, /team, /privacy, /terms), PGP keyservers
     (keys.openpgp.org), and GitHub public commit search to discover real email patterns on the domain.
  5. Probes SMTP RCPT TO on port 25 for catch-all detection and mailbox verification, with
     graceful non-blocking fallback when ISP/cloud blocks outbound port 25.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import random
import re
import smtplib
import socket
import ssl
import string
import unicodedata
import urllib.parse
import urllib.request
from typing import Any, Optional

import dns.exception
import dns.resolver

FREE_WEBMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com",
    "hotmail.com", "live.com", "msn.com", "icloud.com", "me.com", "aol.com",
    "protonmail.com", "proton.me", "zoho.com", "yandex.com", "gmx.com", "mail.com",
})

DISPOSABLE_DOMAINS: frozenset[str] = frozenset({
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "yopmail.com", "sharklasers.com", "trashmail.com", "getnada.com", "maildrop.cc",
})

ROLE_PREFIXES: frozenset[str] = frozenset({
    "info", "contact", "support", "help", "sales", "hello", "team", "office",
    "admin", "billing", "careers", "jobs", "press", "media", "legal", "privacy",
    "security", "hr", "noreply", "no-reply", "marketing", "enquiries", "inquiries",
})

_EMAIL_RE = re.compile(r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,24})\b")


@dataclass
class DomainMailProfile:
    domain: str
    has_mx: bool = False
    mx_hosts: list[str] = field(default_factory=list)
    mail_provider: str = "unknown"

    @property
    def provider(self) -> str:
        return self.mail_provider  # google_workspace | microsoft_365 | mimecast | proofpoint | zoho | protonmail | custom | none
    has_spf: bool = False
    spf_record: str = ""
    has_dmarc: bool = False
    dmarc_record: str = ""
    is_free_webmail: bool = False
    is_disposable: bool = False
    is_catch_all: Optional[bool] = None
    port25_reachable: bool = False
    detected_pattern: Optional[str] = None  # e.g. "{first}.{last}"
    public_emails_found: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmailFinderResult:
    email: str
    confidence: float  # 0.0 to 1.0
    status: str  # verified | catch_all | pattern_matched | permutation_best_guess | invalid
    pattern: str
    domain_profile: DomainMailProfile
    verification_method: str
    candidates_tested: list[dict[str, Any]] = field(default_factory=list)
    alternate_emails: list[str] = field(default_factory=list)

    @property
    def best_email(self) -> str:
        return self.email

    @property
    def domain(self) -> str:
        return self.domain_profile.domain if self.domain_profile else ""

    @property
    def mail_profile(self) -> DomainMailProfile:
        return self.domain_profile

    @property
    def verification_status(self) -> str:
        return self.status

    @property
    def inferred_pattern(self) -> str:
        return self.pattern

    def to_dict(self) -> dict[str, Any]:
        return self.as_dict()

    def as_dict(self) -> dict[str, Any]:
        return {
            "email": self.email,
            "confidence": self.confidence,
            "status": self.status,
            "pattern": self.pattern,
            "domain_profile": self.domain_profile.as_dict(),
            "verification_method": self.verification_method,
            "candidates_tested": list(self.candidates_tested),
            "alternate_emails": list(self.alternate_emails),
        }


def _slug_token(raw: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower().strip())


def normalize_domain(raw_domain_or_url: str) -> str:
    val = (raw_domain_or_url or "").strip().lower()
    if not val:
        return ""
    if "@" in val and "://" not in val and "/" not in val:
        val = val.split("@", 1)[-1]
    if "://" not in val:
        val = "https://" + val
    parsed = urllib.parse.urlparse(val)
    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def generate_email_permutations(
    first_name: str,
    last_name: str,
    domain: str | None = None,
) -> list[tuple[str, str, float]]:
    """Return ordered list of (email, pattern_name, base_prior_weight)."""
    if domain is None:
        domain = last_name
        parts_full = [p for p in re.split(r"\s+", (first_name or "").strip()) if p]
        first_name = parts_full[0] if parts_full else ""
        last_name = parts_full[-1] if len(parts_full) > 1 else ""
    dom = normalize_domain(domain)
    if not dom:
        return []
    parts = [p for p in re.split(r"\s+", (first_name or "").strip()) if p]
    first = _slug_token(parts[0]) if parts else ""
    last = _slug_token(last_name)
    if not last and len(parts) > 1:
        last = _slug_token(parts[-1])

    if not first and not last:
        return []
    if first and not last:
        return [(f"{first}@{dom}", "{first}", 0.65)]
    if last and not first:
        return [(f"{last}@{dom}", "{last}", 0.55)]

    f = first[0]
    l = last[0]
    permutations = [
        (f"{first}.{last}@{dom}", "{first}.{last}", 0.82),
        (f"{first}@{dom}", "{first}", 0.76),
        (f"{f}{last}@{dom}", "{f}{last}", 0.72),
        (f"{first}{last}@{dom}", "{first}{last}", 0.68),
        (f"{first}_{last}@{dom}", "{first}_{last}", 0.60),
        (f"{first}-{last}@{dom}", "{first}-{last}", 0.56),
        (f"{f}.{last}@{dom}", "{f}.{last}", 0.54),
        (f"{first}{l}@{dom}", "{first}{l}", 0.50),
        (f"{last}.{first}@{dom}", "{last}.{first}", 0.45),
        (f"{last}@{dom}", "{last}", 0.42),
    ]
    seen: set[str] = set()
    deduped: list[tuple[str, str, float]] = []
    for email, pat, weight in permutations:
        if email not in seen:
            seen.add(email)
            deduped.append((email, pat, weight))
    return deduped


def _classify_mail_provider(mx_hosts: list[str], spf_record: str) -> str:
    joined = " ".join(mx_hosts).lower() + " " + (spf_record or "").lower()
    if "google.com" in joined or "googlemail.com" in joined or "_spf.google.com" in joined:
        return "google_workspace"
    if "outlook.com" in joined or "protection.outlook.com" in joined or "spf.protection.outlook.com" in joined:
        return "microsoft_365"
    if "mimecast.com" in joined:
        return "mimecast"
    if "pphosted.com" in joined or "proofpoint" in joined:
        return "proofpoint"
    if "zoho.com" in joined or "zoho.eu" in joined or "zoho.in" in joined:
        return "zoho"
    if "protonmail.ch" in joined or "proton.me" in joined:
        return "protonmail"
    if "cloudflare.net" in joined or "route1.mx.cloudflare.net" in joined:
        return "cloudflare"
    if "yahoodns.net" in joined:
        return "yahoo"
    return "custom" if mx_hosts else "none"


def inspect_domain_mail_profile(domain: str, *, timeout: float = 4.0) -> DomainMailProfile:
    dom = normalize_domain(domain)
    profile = DomainMailProfile(
        domain=dom,
        is_free_webmail=dom in FREE_WEBMAIL_DOMAINS,
        is_disposable=dom in DISPOSABLE_DOMAINS,
    )
    if not dom or "." not in dom:
        return profile

    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout

    try:
        mx_answers = resolver.resolve(dom, "MX")
        sorted_mx = sorted(
            mx_answers,
            key=lambda r: getattr(r, "preference", 100),
        )
        profile.mx_hosts = [str(r.exchange).rstrip(".").lower() for r in sorted_mx]
        profile.has_mx = len(profile.mx_hosts) > 0
    except (dns.exception.DNSException, Exception):
        profile.has_mx = False

    try:
        txt_answers = resolver.resolve(dom, "TXT")
        for rdata in txt_answers:
            txt = "".join(
                s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else str(s)
                for s in getattr(rdata, "strings", [rdata.to_text()])
            ).strip('"')
            if txt.lower().startswith("v=spf1"):
                profile.has_spf = True
                profile.spf_record = txt
                break
    except (dns.exception.DNSException, Exception):
        pass

    try:
        dmarc_answers = resolver.resolve(f"_dmarc.{dom}", "TXT")
        for rdata in dmarc_answers:
            txt = "".join(
                s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else str(s)
                for s in getattr(rdata, "strings", [rdata.to_text()])
            ).strip('"')
            if "v=dmarc1" in txt.lower():
                profile.has_dmarc = True
                profile.dmarc_record = txt
                break
    except (dns.exception.DNSException, Exception):
        pass

    profile.mail_provider = _classify_mail_provider(profile.mx_hosts, profile.spf_record)
    return profile


def _smtp_rcpt_probe(
    mx_host: str,
    target_email: str,
    *,
    helo_domain: str = "verify.autoreach.local",
    sender_email: str = "probe@verify.autoreach.local",
    timeout: float = 3.5,
) -> tuple[bool, Optional[int], str]:
    """Attempt an unauthenticated SMTP RCPT TO check on port 25.

    Returns (port25_reachable, smtp_code, message). Never sends DATA.
    """
    try:
        with smtplib.SMTP(host=mx_host, port=25, local_hostname=helo_domain, timeout=timeout) as smtp:
            smtp.ehlo_or_helo_if_needed()
            if smtp.has_extn("starttls"):
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                except Exception:
                    pass
            code_mail, _ = smtp.mail(sender_email)
            if code_mail >= 400:
                return True, code_mail, "mail_from_rejected"
            code_rcpt, msg_rcpt = smtp.rcpt(target_email)
            decoded = msg_rcpt.decode("utf-8", errors="ignore") if isinstance(msg_rcpt, bytes) else str(msg_rcpt)
            smtp.rset()
            return True, code_rcpt, decoded
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False, None, "port25_unreachable_or_blocked"
    except smtplib.SMTPException as exc:
        return True, None, f"smtp_error:{type(exc).__name__}"


def _fetch_text(url: str, *, timeout: float = 5.0, headers: Optional[dict[str, str]] = None) -> str:
    req_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AutoReachBot/1.0; +https://autoreach.ai)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read(250_000)
            return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def discover_public_domain_emails(domain: str, *, timeout: float = 4.5) -> list[str]:
    """Harvest public @domain emails from company pages, PGP keyserver, and GitHub commits."""
    dom = normalize_domain(domain)
    if not dom:
        return []
    found: set[str] = set()

    # 1. Company public pages (/contact, /about, /privacy, /)
    for path in ("", "/contact", "/about", "/privacy", "/security"):
        html = _fetch_text(f"https://{dom}{path}", timeout=timeout)
        if not html:
            continue
        for match in _EMAIL_RE.findall(html):
            cleaned = match.lower().strip(".")
            if cleaned.endswith(f"@{dom}") and not any(
                cleaned.endswith(ext) for ext in (".png", ".jpg", ".svg", ".webp", ".js", ".css")
            ):
                found.add(cleaned)

    # 2. PGP Keyserver lookup (keys.openpgp.org machine-readable index)
    pgp_index = _fetch_text(
        f"https://keys.openpgp.org/pks/lookup?op=index&options=mr&search=%40{urllib.parse.quote(dom)}",
        timeout=timeout,
    )
    if pgp_index:
        unquoted = urllib.parse.unquote(pgp_index)
        for match in _EMAIL_RE.findall(unquoted):
            cleaned = match.lower().strip(".")
            if cleaned.endswith(f"@{dom}"):
                found.add(cleaned)

    # 3. GitHub public commit search for @domain
    gh_json = _fetch_text(
        f"https://api.github.com/search/commits?q={urllib.parse.quote(dom)}&per_page=10",
        timeout=timeout,
        headers={"Accept": "application/vnd.github+json"},
    )
    if gh_json:
        try:
            payload = json.loads(gh_json)
            for item in payload.get("items", []) or []:
                commit = (item or {}).get("commit") or {}
                for actor_key in ("author", "committer"):
                    actor_email = str((commit.get(actor_key) or {}).get("email") or "").lower().strip()
                    if actor_email.endswith(f"@{dom}") and "noreply" not in actor_email:
                        found.add(actor_email)
        except Exception:
            pass

    return sorted(found)


def _infer_pattern_from_known_emails(emails: list[str], domain: str) -> Optional[str]:
    """Infer corporate naming convention from non-role public emails on the domain."""
    dom = normalize_domain(domain)
    personal = [
        e.split("@", 1)[0]
        for e in emails
        if e.endswith(f"@{dom}") and e.split("@", 1)[0] not in ROLE_PREFIXES
    ]
    if not personal:
        return None
    for local in personal:
        if "." in local:
            left, right = local.split(".", 1)
            if len(left) == 1 and len(right) >= 2:
                return "{f}.{last}"
            if len(left) >= 2 and len(right) >= 2:
                return "{first}.{last}"
        if "_" in local:
            return "{first}_{last}"
        if "-" in local:
            return "{first}-{last}"
    return "{first}"


def find_and_verify_email(
    first_name: str = "",
    last_name: str = "",
    domain_or_url: str = "",
    *,
    full_name: Optional[str] = None,
    domain: Optional[str] = None,
    company_domain: Optional[str] = None,
    company_name: Optional[str] = None,
    enable_smtp_probe: bool = True,
    discover_public: bool = True,
    enable_osint: Optional[bool] = None,
    enable_osint_harvest: Optional[bool] = None,
    timeout: float = 4.0,
) -> EmailFinderResult:
    """End-to-end email discovery + DNS/SMTP verification for a B2B decision maker."""
    if full_name and not (first_name or last_name):
        parts_fn = [p for p in re.split(r"\s+", full_name.strip()) if p]
        first_name = parts_fn[0] if parts_fn else ""
        last_name = parts_fn[-1] if len(parts_fn) > 1 else ""
    if enable_osint is not None:
        discover_public = enable_osint
    if enable_osint_harvest is not None:
        discover_public = enable_osint_harvest
    target_dom = domain_or_url or domain or company_domain or company_name or ""
    dom = normalize_domain(target_dom)
    profile = inspect_domain_mail_profile(dom, timeout=timeout)
    candidates = generate_email_permutations(first_name, last_name, dom)

    if not dom or "." not in dom or profile.is_disposable or not candidates:
        return EmailFinderResult(
            email="",
            confidence=0.0,
            status="invalid",
            pattern="",
            domain_profile=profile,
            verification_method="dns_mx_reject",
        )

    if discover_public:
        profile.public_emails_found = discover_public_domain_emails(dom, timeout=timeout)
        profile.detected_pattern = _infer_pattern_from_known_emails(profile.public_emails_found, dom)

        # Direct hit check if the exact person's email is already in public commits/pages
        first_slug = _slug_token(first_name)
        last_slug = _slug_token(last_name)
        for pub_email in profile.public_emails_found:
            local = pub_email.split("@", 1)[0]
            if first_slug and last_slug and first_slug in local and last_slug in local:
                alt = [e for e, _, _ in candidates if e != pub_email][:2]
                return EmailFinderResult(
                    email=pub_email,
                    confidence=0.98,
                    status="verified",
                    pattern=profile.detected_pattern or "{first}.{last}",
                    domain_profile=profile,
                    verification_method="public_osint_exact_match",
                    alternate_emails=alt,
                )

    tested: list[dict[str, Any]] = []

    # Optional SMTP RCPT TO verification + catch-all probe
    if enable_smtp_probe and profile.mx_hosts:
        primary_mx = profile.mx_hosts[0]
        rand_token = "xv9z-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        reachable, catch_code, catch_msg = _smtp_rcpt_probe(
            primary_mx, f"{rand_token}@{dom}", timeout=min(timeout, 3.0)
        )
        profile.port25_reachable = reachable
        if reachable and catch_code is not None:
            profile.is_catch_all = 200 <= catch_code < 300
            if not profile.is_catch_all:
                for email, pat, base_weight in candidates[:5]:
                    _, rcpt_code, rcpt_msg = _smtp_rcpt_probe(primary_mx, email, timeout=min(timeout, 3.0))
                    tested.append({"email": email, "pattern": pat, "smtp_code": rcpt_code, "msg": rcpt_msg})
                    if rcpt_code is not None and 200 <= rcpt_code < 300:
                        alt = [e for e, _, _ in candidates if e != email][:2]
                        return EmailFinderResult(
                            email=email,
                            confidence=0.95,
                            status="verified",
                            pattern=pat,
                            domain_profile=profile,
                            verification_method="smtp_rcpt_250",
                            candidates_tested=tested,
                            alternate_emails=alt,
                        )

    # Rank candidates using detected domain pattern + MX/SPF/DMARC security signals
    security_bonus = (0.04 if profile.has_spf else 0.0) + (0.04 if profile.has_dmarc else 0.0)
    scored: list[tuple[float, str, str]] = []
    for email, pat, base_weight in candidates:
        score = base_weight + security_bonus
        if profile.detected_pattern and pat == profile.detected_pattern:
            score = min(0.92, score + 0.14)
        scored.append((round(min(score, 0.92), 2), email, pat))
        tested.append({"email": email, "pattern": pat, "score": round(min(score, 0.92), 2)})

    scored.sort(key=lambda item: item[0], reverse=True)
    best_conf, best_email, best_pat = scored[0]
    alt_emails = [item[1] for item in scored[1:3]]
    status = (
        "catch_all"
        if profile.is_catch_all
        else ("pattern_matched" if profile.detected_pattern else "permutation_best_guess")
    )
    return EmailFinderResult(
        email=best_email,
        confidence=best_conf,
        status=status,
        pattern=best_pat,
        domain_profile=profile,
        verification_method="dns_mx_pattern_inference",
        candidates_tested=tested,
        alternate_emails=alt_emails,
    )
