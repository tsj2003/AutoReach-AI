"""MCP per-tool authorization — tenant derived from session context only."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class MCPAuthContext:
    tenant_id: str
    actor: str = "mcp_client"


class MCPAuthorizationError(PermissionError):
    def __init__(self, message: str, *, tool: str, status: str = "denied") -> None:
        super().__init__(message)
        self.tool = tool
        self.status = status


def require_mcp_auth() -> MCPAuthContext:
    """Resolve authenticated tenant from ContextVar — never from tool args."""
    from engine.mcp.server import _current_tenant, _store_ref

    tenant_id = _current_tenant.get()
    if not tenant_id:
        raise MCPAuthorizationError("MCP session not authenticated", tool="session", status="unauthenticated")
    store = _store_ref.get()
    if store is None:
        raise MCPAuthorizationError("MCP runtime not configured", tool="session", status="error")
    return MCPAuthContext(tenant_id=tenant_id)


def require_campaign_access(campaign_id: str, *, tool: str) -> None:
    from engine.mcp.server import _store_ref

    ctx = require_mcp_auth()
    store = _store_ref.get()
    if not store.get_engagement(campaign_id, tenant_id=ctx.tenant_id):
        _audit_denied(tool, {"campaign_id": campaign_id}, "access_denied")
        raise MCPAuthorizationError("Campaign not found for tenant", tool=tool, status="denied")


def _audit_denied(tool: str, args: dict, status: str, error: str | None = None) -> None:
    from engine.mcp.server import _audit_ref, _current_tenant

    repo = _audit_ref.get()
    tenant_id = _current_tenant.get() or "unknown"
    if repo:
        repo.record(
            tenant_id=tenant_id,
            actor="mcp_client",
            tool_name=tool,
            arguments=args,
            result_status=status,
            error=error,
        )


def audited_tool(tool_name: str) -> Callable[[F], F]:
    """Decorator: enforce auth + audit success/denial/error for MCP tools."""

    def decorator(fn: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                require_mcp_auth()
                return fn(*args, **kwargs)
            except MCPAuthorizationError as exc:
                logger.warning("MCP auth denied tool=%s: %s", tool_name, exc)
                raise
            except PermissionError as exc:
                _audit_denied(tool_name, dict(kwargs), "denied", str(exc))
                raise
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper  # type: ignore[return-value]

    return decorator
