"""MCP stdio handshake verification."""

from __future__ import annotations

import pytest


def test_mcp_tools_registered():
    from engine.mcp.server import mcp

    tools = list(mcp._tool_manager._tools.keys())
    assert "get_campaign" in tools
    assert "list_campaigns" in tools
    assert "review_pending_outreach" in tools
    assert "get_signal_history" in tools
    assert "get_readiness_summary" in tools


def test_mcp_auth_denies_without_tenant(tmp_path):
    from engine import open_storage
    from engine.mcp.audit import MCPAuditRepository
    from engine.mcp.auth import MCPAuthorizationError, require_mcp_auth
    from engine.mcp.server import configure_runtime, set_tenant

    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'mcp.db'}")
    audit = MCPAuditRepository(store._holder.engine)
    configure_runtime(store=store, events=events, audit_repo=audit)

  # Clear tenant context
    import engine.mcp.server as srv
    srv._current_tenant.set(None)

    with pytest.raises(MCPAuthorizationError):
        require_mcp_auth()


def test_mcp_campaign_access_isolated(tmp_path):
    from engine import Engagement, open_storage
    from engine.mcp.audit import MCPAuditRepository
    from engine.mcp.auth import MCPAuthorizationError, require_campaign_access
    from engine.mcp.server import configure_runtime, set_tenant

    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'mcp2.db'}")
    audit = MCPAuditRepository(store._holder.engine)
    configure_runtime(store=store, events=events, audit_repo=audit)

    store.save_engagement(
        Engagement(id="c-a", customer_name="A", offer="O", icp_description="I"),
        tenant_id="t-a",
    )
    set_tenant("t-b")
    with pytest.raises(MCPAuthorizationError):
        require_campaign_access("c-a", tool="get_campaign")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_attainly_mcp_stdio_client_session_handshake(tmp_path, monkeypatch):
    """Subprocess stdio handshake — proves ClientSession can list Attainly tools."""
    import pathlib
    import sys

    from engine.auth.jwt_handler import sign_jwt
    from engine.integrations.mcp_client import RealMCPClient

    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "x" * 40)
    db = tmp_path / "mcp_stdio.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    token = sign_jwt(
        user_id="u-mcp",
        tenant_id="t-mcp",
        email="mcp@example.com",
        role="owner",
        plan="pro",
    )
    monkeypatch.setenv("AUTOREACH_MCP_JWT", token)

    root = pathlib.Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_attainly_mcp.py"
    cmd = f"{sys.executable} {script}"

    client = RealMCPClient(server_command=cmd, timeout=45)
    try:
        assert await client.connect() is True
        tools = await client.discover_tools()
        names = {t.name for t in tools}
        assert "get_campaign" in names
        assert "list_campaigns" in names
    finally:
        await client.close()
