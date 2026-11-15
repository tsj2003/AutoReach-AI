"""SSRF-safe HTTP fetch for tenant-configured external URLs.

Used by RSS connectors, webhooks, and any user-supplied URL fetch path.
External data is untrusted; URLs must never reach internal networks.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import httpx

# Blocked hostnames beyond IP checks (cloud metadata, etc.)
_BLOCKED_HOSTS = frozenset({
    "localhost",
    "metadata.google.internal",
    "metadata.google",
    "169.254.169.254",
})

_DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB
_DEFAULT_TIMEOUT = 15.0
_MAX_REDIRECTS = 3


@dataclass(frozen=True)
class SafeFetchResult:
    url: str
    status_code: int
    content: bytes
    content_type: str


class SafeFetchError(Exception):
    """Raised when a URL cannot be fetched safely."""


def is_safe_fetch_url(url: str) -> bool:
    """Return True if URL is a public http(s) endpoint safe to fetch."""

    try:
        parsed = urllib.parse.urlparse(url if "//" in url else f"https://{url}")
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower().strip(".")
    if not host or host in _BLOCKED_HOSTS:
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
    except Exception:
        return False
    return True


def safe_fetch(
    url: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    headers: Optional[dict[str, str]] = None,
) -> SafeFetchResult:
    """Fetch a URL with SSRF checks on every redirect hop."""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not is_safe_fetch_url(url):
        raise SafeFetchError(f"URL blocked by SSRF policy: {url}")

    current = url
    req_headers = {"User-Agent": "AttainlySignalBot/1.0", **(headers or {})}

    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            if not is_safe_fetch_url(current):
                raise SafeFetchError(f"Redirect target blocked: {current}")
            response = client.get(current, headers=req_headers)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise SafeFetchError(f"Redirect without Location header from {current}")
                current = urllib.parse.urljoin(current, location)
                continue
            content = b""
            for chunk in response.iter_bytes():
                content += chunk
                if len(content) > max_bytes:
                    raise SafeFetchError(f"Response exceeds max size ({max_bytes} bytes)")
            return SafeFetchResult(
                url=current,
                status_code=response.status_code,
                content=content,
                content_type=response.headers.get("content-type", ""),
            )
    raise SafeFetchError(f"Too many redirects (> {_MAX_REDIRECTS})")
