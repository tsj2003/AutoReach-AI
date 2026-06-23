"""Deliverability preflight checks for pilot onboarding."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

try:
    import dns.asyncresolver
except ImportError:  # pragma: no cover - exercised only in incomplete envs
    class _MissingAsyncResolver:
        async def resolve(self, *_args: Any, **_kwargs: Any) -> list[Any]:
            raise RuntimeError("dnspython is not installed")

    class _MissingDNS:
        asyncresolver = _MissingAsyncResolver()

    dns = _MissingDNS()  # type: ignore[assignment]
else:
    import dns  # type: ignore[no-redef]


class PreflightResult(BaseModel):
    is_safe_to_send: bool
    failure_reasons: list[str] = Field(default_factory=list)


class DeliverabilityPreflight:
    """Verifies outbound DNS records before a tenant can go active."""

    async def verify_domain(self, domain: str) -> PreflightResult:
        normalized_domain = domain.strip().lower().rstrip(".")
        failure_reasons: list[str] = []

        spf_records = await self._lookup_txt(normalized_domain)
        if not any("v=spf1" in record.lower() for record in spf_records):
            failure_reasons.append("SPF missing")

        dmarc_records = await self._lookup_txt(f"_dmarc.{normalized_domain}")
        if not any("v=dmarc1" in record.lower() for record in dmarc_records):
            failure_reasons.append("DMARC missing")

        return PreflightResult(
            is_safe_to_send=not failure_reasons,
            failure_reasons=failure_reasons,
        )

    async def _lookup_txt(self, qname: str) -> list[str]:
        try:
            answers = await dns.asyncresolver.resolve(qname, "TXT")
        except Exception:
            return []
        return [self._record_to_text(record) for record in answers]

    @staticmethod
    def _record_to_text(record: Any) -> str:
        strings = getattr(record, "strings", None)
        if strings is not None:
            return "".join(
                part.decode("utf-8", errors="ignore") if isinstance(part, bytes) else str(part)
                for part in strings
            )

        to_text = getattr(record, "to_text", None)
        if callable(to_text):
            return str(to_text()).replace('"', "")
        return str(record).replace('"', "")
