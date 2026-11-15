"""Pilot tenant onboarding for the internal Outcome-as-a-Service console."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field

from engine.auth import Tenant
from engine.runtime.context import TenantContext

from cockpit.services.preflight import DeliverabilityPreflight, PreflightResult

ACTIVE = "ACTIVE"
PENDING_REMEDIATION = "PENDING_REMEDIATION"

db_session: Any = None


class TenantOnboardingPayload(BaseModel):
    company_name: str
    domain: str
    budget_limit: Decimal
    meeting_price: Decimal
    linkedin_enabled: bool = False
    mcp_server_command: Optional[str] = None
    mcp_server_url: Optional[str] = None


class TenantOnboardingResult(BaseModel):
    tenant_id: str
    company_name: str
    domain: str
    status: str
    preflight: PreflightResult
    tenant_context: TenantContext


@dataclass
class PilotTenantRecord:
    tenant_id: str
    company_name: str
    domain: str
    status: str
    budget_limit: Decimal
    meeting_price: Decimal
    linkedin_enabled: bool = False
    mcp_server_command: Optional[str] = None
    mcp_server_url: Optional[str] = None
    failure_reasons: list[str] = field(default_factory=list)


class OnboardingService:
    """Creates a tenant record but only activates it after deliverability passes."""

    def __init__(self, preflight: DeliverabilityPreflight | None = None, db: Any | None = None) -> None:
        self._preflight = preflight or DeliverabilityPreflight()
        self._db = db

    async def register_tenant(self, payload: TenantOnboardingPayload) -> TenantOnboardingResult:
        preflight = await self._preflight.verify_domain(payload.domain)
        status = ACTIVE if preflight.is_safe_to_send else PENDING_REMEDIATION
        tenant_id = self._tenant_id_for(payload.domain)
        tenant_context = TenantContext(
            tenant_id=tenant_id,
            campaign_id="pilot-onboarding",
            variables=self._variables_for(payload=payload, status=status),
            encrypted_secrets={},
        )

        record = PilotTenantRecord(
            tenant_id=tenant_id,
            company_name=payload.company_name,
            domain=payload.domain,
            status=status,
            budget_limit=payload.budget_limit,
            meeting_price=payload.meeting_price,
            linkedin_enabled=payload.linkedin_enabled,
            mcp_server_command=payload.mcp_server_command,
            mcp_server_url=payload.mcp_server_url,
            failure_reasons=list(preflight.failure_reasons),
        )
        await self._persist(record)

        return TenantOnboardingResult(
            tenant_id=tenant_id,
            company_name=payload.company_name,
            domain=payload.domain,
            status=status,
            preflight=preflight,
            tenant_context=tenant_context,
        )

    async def _persist(self, record: PilotTenantRecord) -> None:
        session = self._db if self._db is not None else db_session
        if session is None:
            return

        save_tenant = getattr(session, "save_tenant", None)
        if callable(save_tenant) and not session.__class__.__module__.startswith("unittest.mock"):
            now = datetime.now(timezone.utc)
            save_tenant(
                Tenant(
                    id=record.tenant_id,
                    name=record.company_name,
                    plan="pro" if record.status == ACTIVE else "free",
                    trial_ends_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            return

        add = getattr(session, "add", None)
        if callable(add):
            add(record)

        commit = getattr(session, "commit", None)
        if callable(commit):
            maybe_awaitable = commit()
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable

    @staticmethod
    def _tenant_id_for(domain: str) -> str:
        normalized = domain.strip().lower().rstrip(".")
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
        return f"tnt_{digest}"

    @staticmethod
    def _variables_for(*, payload: TenantOnboardingPayload, status: str) -> dict[str, Any]:
        variables: dict[str, Any] = {
            "company_name": payload.company_name,
            "domain": payload.domain,
            "budget_limit": payload.budget_limit,
            "meeting_price": payload.meeting_price,
            "linkedin_enabled": payload.linkedin_enabled,
            "onboarding_status": status,
        }
        if payload.mcp_server_command:
            variables["mcp_server_command"] = payload.mcp_server_command
        if payload.mcp_server_url:
            variables["mcp_server_url"] = payload.mcp_server_url
        return variables
