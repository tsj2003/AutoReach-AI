"""MCP audit event persistence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine

from engine.storage.sqlite import mcp_audit_events_table


class MCPAuditRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(
        self,
        *,
        tenant_id: str,
        actor: str,
        tool_name: str,
        arguments: dict[str, Any],
        result_status: str,
        trace_id: str | None = None,
        error: str | None = None,
    ) -> None:
        safe_args = json.dumps(arguments, sort_keys=True, default=str)[:4000]
        arg_hash = hashlib.sha256(safe_args.encode()).hexdigest()[:32]
        values = {
            "id": f"mcp_{arg_hash[:16]}_{int(datetime.now(timezone.utc).timestamp())}",
            "tenant_id": tenant_id,
            "actor": actor,
            "tool_name": tool_name,
            "arguments_hash": arg_hash,
            "arguments_safe": safe_args,
            "result_status": result_status,
            "trace_id": trace_id,
            "error": error,
            "occurred_at": datetime.now(timezone.utc),
        }
        with self._engine.begin() as conn:
            conn.execute(mcp_audit_events_table.insert().values(**values))

    def list_recent(self, *, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        stmt = (
            select(mcp_audit_events_table)
            .where(mcp_audit_events_table.c.tenant_id == tenant_id)
            .order_by(mcp_audit_events_table.c.occurred_at.desc())
            .limit(limit)
        )
        with self._engine.begin() as conn:
            rows = conn.execute(stmt).all()
        return [
            {
                "id": r.id,
                "tool_name": r.tool_name,
                "actor": r.actor,
                "result_status": r.result_status,
                "trace_id": r.trace_id,
                "error": r.error,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            }
            for r in rows
        ]
