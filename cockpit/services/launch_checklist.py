"""Pilot campaign launch checklist for internal operators."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from pydantic import BaseModel, Field


class LaunchChecklistItem(BaseModel):
    key: str
    label: str
    passed: bool
    detail: str


class LaunchChecklistResult(BaseModel):
    tenant_id: str
    campaign_id: str
    is_launch_ready: bool
    items: list[LaunchChecklistItem] = Field(default_factory=list)


class PilotLaunchChecklist:
    """Evaluates whether a tenant-scoped campaign is safe to launch."""

    def __init__(self, *, store: Any) -> None:
        self._store = store

    def evaluate(self, *, tenant_id: str, campaign_id: str) -> LaunchChecklistResult:
        engagement = self._store.get_engagement(campaign_id, tenant_id=tenant_id)
        if engagement is None:
            items = [
                LaunchChecklistItem(
                    key="campaign_scope",
                    label="Campaign ownership",
                    passed=False,
                    detail="Campaign was not found for this tenant.",
                )
            ]
            return LaunchChecklistResult(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                is_launch_ready=False,
                items=items,
            )

        metadata = dict(getattr(engagement, "metadata", {}) or {})
        items = [
            self._dns_item(metadata),
            self._client_cure_item(metadata),
            self._mailbox_item(tenant_id),
            self._budget_item(engagement),
            self._signal_matrix_item(metadata),
            self._hitl_item(campaign_id),
        ]
        return LaunchChecklistResult(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            is_launch_ready=all(item.passed for item in items),
            items=items,
        )

    def activate_if_ready(self, *, tenant_id: str, campaign_id: str) -> LaunchChecklistResult:
        result = self.evaluate(tenant_id=tenant_id, campaign_id=campaign_id)
        if not result.is_launch_ready:
            return result

        engagement = self._store.get_engagement(campaign_id, tenant_id=tenant_id)
        if engagement is not None and getattr(engagement, "status", "") != "active":
            self._store.save_engagement(
                replace(engagement, status="active"),
                tenant_id=tenant_id,
            )
        return result

    @staticmethod
    def _dns_item(metadata: dict[str, Any]) -> LaunchChecklistItem:
        preflight = dict(metadata.get("deliverability_preflight") or {})
        passed = preflight.get("is_safe_to_send") is True or metadata.get("onboarding_status") == "ACTIVE"
        return LaunchChecklistItem(
            key="dns_preflight",
            label="Deliverability preflight",
            passed=passed,
            detail="SPF and DMARC passed." if passed else "SPF and DMARC must pass before launch.",
        )

    @staticmethod
    def _client_cure_item(metadata: dict[str, Any]) -> LaunchChecklistItem:
        client_cure = str(metadata.get("client_cure") or "").strip()
        return LaunchChecklistItem(
            key="client_cure",
            label="Client cure",
            passed=bool(client_cure),
            detail=(
                "Specific client cure is configured."
                if client_cure else "Describe the exact pain this client's product cures."
            ),
        )

    def _mailbox_item(self, tenant_id: str) -> LaunchChecklistItem:
        list_mailboxes = getattr(self._store, "list_mailboxes", None)
        mailboxes = list(list_mailboxes(tenant_id)) if callable(list_mailboxes) else []
        usable = [mb for mb in mailboxes if getattr(mb, "status", "") in ("active", "warming")]
        return LaunchChecklistItem(
            key="mailbox_ready",
            label="Mailbox connected",
            passed=bool(usable),
            detail=(
                f"{len(usable)} usable mailbox connection(s)."
                if usable else "Connect at least one active or warming mailbox."
            ),
        )

    @staticmethod
    def _budget_item(engagement: Any) -> LaunchChecklistItem:
        budget = getattr(engagement, "monthly_budget_cents", None)
        passed = isinstance(budget, int) and budget > 0
        return LaunchChecklistItem(
            key="budget_guardrail",
            label="Budget guardrail",
            passed=passed,
            detail=(
                f"Monthly budget set to {budget} cents."
                if passed else "Set a positive monthly budget before launch."
            ),
        )

    @staticmethod
    def _signal_matrix_item(metadata: dict[str, Any]) -> LaunchChecklistItem:
        matrix = dict(metadata.get("signal_matrix") or {})
        allowed = matrix.get("allowed_signal_types") or []
        passed = isinstance(allowed, list) and len(allowed) > 0
        return LaunchChecklistItem(
            key="signal_matrix",
            label="Signal matrix",
            passed=passed,
            detail=(
                f"{len(allowed)} allowed signal type(s) configured."
                if passed else "Configure at least one allowed intent signal type."
            ),
        )

    def _hitl_item(self, campaign_id: str) -> LaunchChecklistItem:
        agents = list(self._store.list_agents(campaign_id))
        configured = [
            agent for agent in agents
            if "hitl_threshold" in dict(getattr(agent, "config", {}) or {})
        ]
        return LaunchChecklistItem(
            key="hitl_configured",
            label="Approval workflow",
            passed=bool(configured),
            detail=(
                "Human approval threshold is configured."
                if configured else "Configure HITL approval before launch."
            ),
        )
