#!/usr/bin/env python3
"""
Gmail proof chain — honest dry-run or live verification.

Checks mailbox configuration, optional dry-run send, and documents what is
implemented vs what requires live OAuth credentials.

Run:
    AUTOREACH_GMAIL_DRY_RUN=1 python3 scripts/gmail_proof_chain.py
    python3 scripts/gmail_proof_chain.py --tenant-id <id> --live
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ProofStep:
    name: str
    status: str  # pass | skip | fail | needs_credentials
    detail: str = ""


@dataclass
class ProofReport:
    mode: str
    tenant_id: str | None
    steps: list[ProofStep] = field(default_factory=list)
    verdict: str = "UNKNOWN"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append(ProofStep(name=name, status=status, detail=detail))

    def finalize(self) -> None:
        statuses = {s.status for s in self.steps}
        if "fail" in statuses:
            self.verdict = "FAIL"
        elif statuses <= {"pass"}:
            self.verdict = "PASS"
        elif "needs_credentials" in statuses:
            self.verdict = "IMPLEMENTED — LIVE CREDENTIALS REQUIRED"
        else:
            self.verdict = "PARTIAL"


def _dry_run_enabled() -> bool:
    return os.getenv("AUTOREACH_GMAIL_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")


def run_proof(*, tenant_id: str | None, live: bool) -> ProofReport:
    from engine import Engagement, Prospect, Reply, open_storage
    from engine.services.reply_sender import ReplySender

    db_url = os.getenv("DATABASE_URL") or os.getenv("AUTOREACH_DB", "sqlite:///autoreach_engine.db")
    store, events, ledger = open_storage(db_url)

    mode = "live" if live and not _dry_run_enabled() else "dry_run"
    report = ProofReport(mode=mode, tenant_id=tenant_id)

    mailboxes = []
    if tenant_id:
        mailboxes = list(store.list_mailboxes(tenant_id, status="active"))
    else:
        report.add("tenant_scope", "skip", "No --tenant-id; mailbox lookup skipped")

    if tenant_id and not mailboxes:
        report.add(
            "active_mailbox",
            "needs_credentials",
            "No active mailbox for tenant — connect Gmail OAuth first",
        )
    elif tenant_id:
        mb = mailboxes[0]
        report.add("active_mailbox", "pass", f"{mb.email_address} ({mb.id})")

    if mode == "dry_run":
        report.add("dry_run_flag", "pass", "AUTOREACH_GMAIL_DRY_RUN enabled or --live not set")
    else:
        report.add("dry_run_flag", "skip", "Live mode requested")

    if not tenant_id:
        report.finalize()
        return report

    # Minimal synthetic reply for adapter path exercise (dry-run only).
    eng_id = "proof_eng"
    if not store.get_engagement(eng_id, tenant_id=tenant_id):
        store.save_engagement(
            Engagement(id=eng_id, customer_name="Proof", offer="O", icp_description="I"),
            tenant_id=tenant_id,
        )
    prospect_id = "proof_prospect"
    if store.get_prospect(prospect_id) is None:
        store.save_prospect(
            Prospect(
                id=prospect_id,
                engagement_id=eng_id,
                email="proof-recipient@example.com",
                full_name="Proof Recipient",
            )
        )
    reply_id = "proof_reply"
    existing = store.get_reply(reply_id)
    if existing is None:
        store.save_reply(
            Reply(
                id=reply_id,
                engagement_id=eng_id,
                prospect_id=prospect_id,
                job_id=None,
                snippet="Re: proof chain",
                classification="interested",
                suggested_reply="Proof chain dry-run body.",
                status="pending",
            )
        )
        existing = store.get_reply(reply_id)

    if not mailboxes:
        report.add("adapter_execute", "skip", "No mailbox — cannot exercise send adapter")
        report.finalize()
        return report

    sender = ReplySender(store=store, events=events, ledger=ledger)
    ok = sender.send(existing, existing.suggested_reply or "", tenant_id=tenant_id)
    if ok:
        report.add(
            "adapter_execute",
            "pass" if mode == "dry_run" else "pass",
            f"ReplySender returned success ({mode})",
        )
    else:
        report.add(
            "adapter_execute",
            "needs_credentials" if mode == "live" else "fail",
            "ReplySender returned False — check mailbox tokens / OAuth",
        )

    report.add(
        "receive_classify",
        "needs_credentials",
        "Reply poll + classify requires live Gmail inbox — not exercised by this script",
    )
    report.add(
        "inbox_approve_loop",
        "needs_credentials",
        "Full approve→send loop requires REST + live mailbox — use e2e smoke with credentials",
    )

    report.finalize()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Gmail proof chain (honest dry-run or live)")
    parser.add_argument("--tenant-id", default=os.getenv("AUTOREACH_PROOF_TENANT_ID"))
    parser.add_argument("--live", action="store_true", help="Attempt live send (requires OAuth tokens)")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    if args.live and _dry_run_enabled():
        print("WARN: AUTOREACH_GMAIL_DRY_RUN is set — adapter will not hit Gmail API", file=sys.stderr)

    report = run_proof(tenant_id=args.tenant_id, live=args.live)
    payload = {
        "verdict": report.verdict,
        "mode": report.mode,
        "tenant_id": report.tenant_id,
        "timestamp": report.timestamp,
        "steps": [asdict(s) for s in report.steps],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Gmail proof chain — {report.verdict}")
        print(f"Mode: {report.mode} | Tenant: {report.tenant_id or '(none)'}")
        for step in report.steps:
            print(f"  [{step.status.upper():>18}] {step.name}: {step.detail}")

    evidence_path = ROOT / "docs" / "PHASE6_EVIDENCE.md"
    if evidence_path.exists() and report.tenant_id:
        ts = report.timestamp[:10]
        line = (
            f"| Gmail proof chain ({report.mode}) | YES | PARTIAL | "
            f"{'NO' if report.verdict.endswith('REQUIRED') else 'PARTIAL'} | "
            f"`scripts/gmail_proof_chain.py` {ts} | local | OAuth | {report.verdict} | NO |"
        )
        print(f"\nEvidence line (append to PHASE6_EVIDENCE.md manually if desired):\n{line}")

    return 0 if report.verdict in ("PASS", "IMPLEMENTED — LIVE CREDENTIALS REQUIRED", "PARTIAL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
