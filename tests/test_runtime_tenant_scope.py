"""EngineRuntime must refuse accidental unscoped all-tenant sweeps in SaaS mode.

`require_tenant_scope=True` is set for the multi-tenant cockpit web app and the
worker; the single-operator CLI and these engine tests leave it False.
"""

from __future__ import annotations

import pytest

from engine import (
    AdapterRegistry,
    ConsoleEmailAdapter,
    EngineRuntime,
    OutboundAgentV1,
    open_storage,
)


def _runtime(tmp_path, *, require_tenant_scope):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'scope.db'}")
    return EngineRuntime(
        store=store,
        events=events,
        ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
        require_tenant_scope=require_tenant_scope,
    )


def test_strict_runtime_refuses_unscoped_plan_and_run(tmp_path):
    rt = _runtime(tmp_path, require_tenant_scope=True)
    with pytest.raises(ValueError):
        rt.plan_all()
    with pytest.raises(ValueError):
        rt.execute_due_jobs()
    with pytest.raises(ValueError):
        rt.tick()
    with pytest.raises(ValueError):
        rt.run_once()


def test_strict_runtime_allows_scoped_and_explicit_sweep(tmp_path):
    rt = _runtime(tmp_path, require_tenant_scope=True)
    # Scoped by tenant is fine (empty store → 0 planned).
    assert rt.plan_all(tenant_id="t-1") == 0
    # Scoped by engagement is fine.
    assert rt.plan_all(engagement_id="e-1") == 0
    # Explicit system-wide sweep (what the beat scheduler does) is allowed.
    assert rt.run_once(allow_all_tenants=True)["planned"] == 0


def test_default_runtime_allows_unscoped_single_operator(tmp_path):
    """Legacy/CLI/test behavior is unchanged when require_tenant_scope is False."""
    rt = _runtime(tmp_path, require_tenant_scope=False)
    assert rt.plan_all() == 0
    assert rt.run_once()["planned"] == 0
