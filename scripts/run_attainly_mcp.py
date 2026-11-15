#!/usr/bin/env python3
"""Run the Attainly MCP server (stdio transport)."""

from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from dotenv import load_dotenv

load_dotenv()

from engine import open_storage
from engine.auth.jwt_handler import decode_jwt
from engine.mcp.audit import MCPAuditRepository
from engine.mcp.server import configure_runtime, mcp, set_tenant


def _resolve_tenant() -> str:
    token = os.environ.get("AUTOREACH_MCP_BEARER", "").strip()
    if token.startswith("Bearer "):
        token = token[7:].strip()
    if not token:
        token = os.environ.get("AUTOREACH_MCP_JWT", "").strip()
    if not token:
        raise SystemExit("Set AUTOREACH_MCP_JWT or AUTOREACH_MCP_BEARER with a valid tenant JWT")
    payload = decode_jwt(token, expected_type="access")
    return payload["tenant_id"]


def main() -> None:
    db_url = os.getenv("DATABASE_URL") or os.getenv("AUTOREACH_DB", "sqlite:///autoreach_engine.db")
    store, events, _ = open_storage(db_url)
    audit = MCPAuditRepository(store._holder.engine)
    configure_runtime(store=store, events=events, audit_repo=audit)
    set_tenant(_resolve_tenant())
    mcp.run()


if __name__ == "__main__":
    main()
