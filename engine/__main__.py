"""
`python -m engine` CLI — the operator's hand on the throttle.

Usage examples
--------------
    # Set up a fresh DB
    python -m engine init --db sqlite:///autoreach_engine.db

    # Create an engagement (yourself, dogfooding)
    python -m engine engagement-create \\
        --id self \\
        --customer "AutoReach (self)" \\
        --offer "AI sales infra for B2B founders. 500/qualified meeting." \\
        --icp "seed-series A B2B SaaS founders, US/EU, 5-50 employees" \\
        --booking-url https://cal.com/yourname/intro \\
        --target 20 --price 50000 --budget 100000

    # Create a console-email outbound agent (no real Gmail yet)
    python -m engine agent-create --engagement self --runner outbound.v1 --id agent_self

    # Add a prospect
    python -m engine prospect-add --engagement self \\
        --email founder@startup.com --name "Test Founder" --company "Startup Inc"

    # Plan + execute one tick (jobs go to console adapter, captured in DB events)
    python -m engine tick

    # Drain (run until quiescent)
    python -m engine drain

    # Approve a HITL-blocked job
    python -m engine approve --job <job_id>

    # Inspect events
    python -m engine events --engagement self --limit 20
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from typing import Optional

from engine import (
    AdapterRegistry,
    Agent,
    ConsoleEmailAdapter,
    Engagement,
    EngineRuntime,
    OutboundAgentV1,
    Prospect,
    open_storage,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _runtime(db_url: str) -> tuple[EngineRuntime, ConsoleEmailAdapter, "open_storage"]:
    store, events, ledger = open_storage(db_url)
    console = ConsoleEmailAdapter()
    registry = AdapterRegistry([console])
    runners = {OutboundAgentV1.runner_kind: OutboundAgentV1()}
    runtime = EngineRuntime(
        store=store,
        events=events,
        ledger=ledger,
        adapters=registry,
        agent_runners=runners,
    )
    return runtime, console, (store, events, ledger)


def _print(obj) -> None:
    sys.stdout.write(json.dumps(obj, default=str, indent=2) + "\n")


# ─── command handlers ───────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    open_storage(args.db)
    _print({"ok": True, "db": args.db})
    return 0


def cmd_engagement_create(args: argparse.Namespace) -> int:
    _, _, (store, _, _) = _runtime(args.db)
    eng = Engagement(
        id=args.id,
        customer_name=args.customer,
        offer=args.offer,
        icp_description=args.icp,
        booking_url=args.booking_url,
        monthly_meeting_target=args.target,
        price_per_outcome_cents=args.price,
        monthly_budget_cents=args.budget,
    )
    store.save_engagement(eng)
    _print({"ok": True, "engagement_id": eng.id})
    return 0


def cmd_agent_create(args: argparse.Namespace) -> int:
    _, _, (store, _, _) = _runtime(args.db)
    config: dict = {}
    if args.hitl_threshold is not None:
        config["hitl_threshold"] = args.hitl_threshold
    if args.send_gap_seconds is not None:
        config["send_gap_seconds"] = args.send_gap_seconds
    if args.subject_template:
        config["subject_template"] = args.subject_template
    if args.body_template:
        config["body_template"] = args.body_template
    agent = Agent(
        id=args.id,
        engagement_id=args.engagement,
        runner_kind=args.runner,
        config=config,
    )
    store.save_agent(agent)
    _print({"ok": True, "agent_id": agent.id})
    return 0


def cmd_prospect_add(args: argparse.Namespace) -> int:
    _, _, (store, _, _) = _runtime(args.db)
    p = Prospect(
        id=args.id or _new_id("p"),
        engagement_id=args.engagement,
        email=args.email,
        full_name=args.name,
        company=args.company,
        title=args.title,
    )
    store.save_prospect(p)
    _print({"ok": True, "prospect_id": p.id})
    return 0


def cmd_tick(args: argparse.Namespace) -> int:
    runtime, console, _ = _runtime(args.db)
    result = runtime.tick(engagement_id=args.engagement)
    _print(
        {
            "ok": True,
            "tick": result,
            "console_outbox_count": len(console.outbox),
            "last_console_subject": (console.outbox[-1]["subject"] if console.outbox else None),
        }
    )
    return 0


def cmd_drain(args: argparse.Namespace) -> int:
    runtime, console, _ = _runtime(args.db)
    result = runtime.run_once(max_iters=args.max_iters, engagement_id=args.engagement)
    _print(
        {
            "ok": True,
            "drain": result,
            "console_outbox_count": len(console.outbox),
        }
    )
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    runtime, _, _ = _runtime(args.db)
    ok = runtime.approve_job(args.job)
    _print({"ok": ok, "job_id": args.job})
    return 0 if ok else 1


def cmd_reject(args: argparse.Namespace) -> int:
    runtime, _, _ = _runtime(args.db)
    ok = runtime.reject_job(args.job, reason=args.reason or "")
    _print({"ok": ok, "job_id": args.job})
    return 0 if ok else 1


def cmd_events(args: argparse.Namespace) -> int:
    _, _, (_, events, _) = _runtime(args.db)
    rows = list(events.list_recent(engagement_id=args.engagement, limit=args.limit))
    _print(
        [
            {
                "kind": ev.kind.value,
                "engagement_id": ev.engagement_id,
                "job_id": ev.job_id,
                "prospect_id": ev.prospect_id,
                "payload": dict(ev.payload),
                "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
            }
            for ev in rows
        ]
    )
    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    _, _, (store, _, _) = _runtime(args.db)
    rows = list(store.list_jobs_by_state(args.state, engagement_id=args.engagement, limit=args.limit))
    _print(
        [
            {
                "id": j.id,
                "state": j.state,
                "kind": j.kind.value,
                "attempt": j.attempt,
                "requires_approval": j.requires_approval,
                "scheduled_for": j.scheduled_for.isoformat() if j.scheduled_for else None,
                "last_error": j.last_error,
                "prospect_id": j.prospect_id,
            }
            for j in rows
        ]
    )
    return 0


# ─── argument parser ─────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m engine")
    p.add_argument("--db", default="sqlite:///autoreach_engine.db", help="storage URL")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="create the DB schema")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("engagement-create", help="create an engagement")
    sp.add_argument("--id", required=True)
    sp.add_argument("--customer", required=True)
    sp.add_argument("--offer", required=True)
    sp.add_argument("--icp", required=True)
    sp.add_argument("--booking-url", default=None)
    sp.add_argument("--target", type=int, default=None, help="monthly meeting target")
    sp.add_argument("--price", type=int, default=None, help="price per outcome (cents)")
    sp.add_argument("--budget", type=int, default=None, help="monthly budget (cents)")
    sp.set_defaults(func=cmd_engagement_create)

    sp = sub.add_parser("agent-create", help="create an agent")
    sp.add_argument("--id", required=True)
    sp.add_argument("--engagement", required=True)
    sp.add_argument("--runner", default="outbound.v1")
    sp.add_argument("--hitl-threshold", type=int, default=None)
    sp.add_argument("--send-gap-seconds", type=int, default=None)
    sp.add_argument("--subject-template", default=None)
    sp.add_argument("--body-template", default=None)
    sp.set_defaults(func=cmd_agent_create)

    sp = sub.add_parser("prospect-add", help="add one prospect")
    sp.add_argument("--engagement", required=True)
    sp.add_argument("--email", required=True)
    sp.add_argument("--name", default=None)
    sp.add_argument("--company", default=None)
    sp.add_argument("--title", default=None)
    sp.add_argument("--id", default=None, help="optional explicit prospect ID")
    sp.set_defaults(func=cmd_prospect_add)

    sp = sub.add_parser("tick", help="run one plan + execute cycle")
    sp.add_argument("--engagement", default=None, help="optional engagement scope")
    sp.set_defaults(func=cmd_tick)

    sp = sub.add_parser("drain", help="run until quiescent")
    sp.add_argument("--max-iters", type=int, default=50)
    sp.add_argument("--engagement", default=None, help="optional engagement scope")
    sp.set_defaults(func=cmd_drain)

    sp = sub.add_parser("approve", help="approve a job awaiting HITL approval")
    sp.add_argument("--job", required=True)
    sp.set_defaults(func=cmd_approve)

    sp = sub.add_parser("reject", help="reject a job awaiting HITL approval")
    sp.add_argument("--job", required=True)
    sp.add_argument("--reason", default=None)
    sp.set_defaults(func=cmd_reject)

    sp = sub.add_parser("events", help="list recent events")
    sp.add_argument("--engagement", default=None)
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_events)

    sp = sub.add_parser("jobs", help="list jobs by state")
    sp.add_argument("--state", required=True)
    sp.add_argument("--engagement", default=None)
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_jobs)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
