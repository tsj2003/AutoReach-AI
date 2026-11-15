#!/usr/bin/env python3
"""
scripts/send_hr_outreach.py
Clean Downloads/hr_contacts.csv, select a batch of 100 contacts, save to newlit.csv,
schedule email outreach in SQLite with random 1-2 minute delays, and execute them.

Usage:
    # Test batching and email generation (Dry-Run mode)
    PYTHONPATH=. .venv/bin/python scripts/send_hr_outreach.py

    # Start live sending campaign
    PYTHONPATH=. .venv/bin/python scripts/send_hr_outreach.py --live
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine import (
    open_storage,
    Engagement,
    Agent,
    Prospect,
    Job,
    JobKind,
    RealGmailSendAdapter,
    JsonFileTokenStore,
    EngineRuntime,
    AdapterRegistry,
    OutboundAgentV1,
)

# Email address format validation regex
EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
ALLOW_LEGACY_DIRECT_SEND_ENV = "AUTOREACH_ALLOW_LEGACY_DIRECT_SEND"


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _require_live_send_escape_hatch() -> None:
    if not _env_flag(ALLOW_LEGACY_DIRECT_SEND_ENV):
        raise SystemExit(
            f"Live legacy outreach is disabled. Set {ALLOW_LEGACY_DIRECT_SEND_ENV}=1 "
            "only for an intentional one-off operator run. Production sends should "
            "flow through tenant mailboxes and the smart dispatch router."
        )


def clean_and_batch_contacts(csv_path: str, count: int = 100) -> list[dict]:
    """Clean the input CSV, validate emails, deduplicate, and return first N contacts."""
    cleaned = []
    seen_emails = set()

    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = (row.get("Email") or "").strip()
            name = (row.get("Name") or "").strip()
            title = (row.get("Title") or "").strip()
            company = (row.get("Company") or "").strip()

            # Clean and validate email
            if not email or not EMAIL_RE.match(email):
                continue

            email_lower = email.lower()
            if email_lower in seen_emails:
                continue

            seen_emails.add(email_lower)
            cleaned.append({
                "Name": name,
                "Email": email,
                "Title": title,
                "Company": company
            })

            if len(cleaned) == count:
                break

    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run the campaign in LIVE mode (sends real emails)")
    parser.add_argument("--db", default="sqlite:///autoreach_engine.db", help="Database URL")
    parser.add_argument("--csv", default=os.getenv("AUTOREACH_HR_CONTACTS_CSV", str(Path.home() / "Downloads" / "hr_contacts.csv")))
    parser.add_argument("--out", default=os.getenv("AUTOREACH_HR_BATCH_CSV", "newlit.csv"))
    parser.add_argument("--resume", default=os.getenv("AUTOREACH_HR_RESUME_PATH", "Tarandeep_Resume_AI (1).pdf"))
    parser.add_argument("--token-path", default=os.getenv("AUTOREACH_GMAIL_TOKEN_PATH", "token.json"))
    parser.add_argument("--sender-email", default=os.getenv("AUTOREACH_GMAIL_SENDER", ""))
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()

    live_mode = args.live
    if live_mode:
        _require_live_send_escape_hatch()
        if not args.sender_email:
            raise SystemExit("Live mode requires --sender-email or AUTOREACH_GMAIL_SENDER.")

    csv_input_path = args.csv
    newlit_output_path = args.out
    resume_pdf_path = args.resume
    token_json_path = args.token_path

    # 1. Clean and batch the contacts
    print(f"[*] Ingesting and cleaning contacts from: {csv_input_path}...")
    batch = clean_and_batch_contacts(csv_input_path, count=args.count)
    print(f"[+] Loaded {len(batch)} unique, valid HR contacts.")

    if not batch:
        print("[-] No valid contacts found.")
        sys.exit(1)

    # 2. Write the 100 cleaned contacts to newlit.csv as a record
    print(f"[*] Writing target batch of 100 to: {newlit_output_path}...")
    with open(newlit_output_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Name", "Email", "Title", "Company"])
        writer.writeheader()
        writer.writerows(batch)
    print(f"[+] Cleaned batch saved successfully to {newlit_output_path}.")

    # 3. Setup the engine runtime and storage
    store, events, ledger = open_storage(args.db)
    token_store = JsonFileTokenStore(token_path=token_json_path)

    # Configure adapter
    gmail_adapter = RealGmailSendAdapter(
        sender_email=args.sender_email or "dry-run@example.invalid",
        token_store=token_store,
        dry_run=not live_mode,
    )
    registry = AdapterRegistry([gmail_adapter])
    runners = {OutboundAgentV1.runner_kind: OutboundAgentV1()}

    runtime = EngineRuntime(
        store=store,
        events=events,
        ledger=ledger,
        adapters=registry,
        agent_runners=runners,
    )

    # 4. Initialize Engagement and Agent if they don't exist
    engagement_id = "hr_outreach_100"
    eng = store.get_engagement(engagement_id)
    if not eng:
        eng = Engagement(
            id=engagement_id,
            customer_name="Tarandeep Singh Juneja",
            offer="Software Engineer Role",
            icp_description="Indian Tech & GCC HR Inboxes",
            booking_url="https://portfolio-tsj.netlify.app/",
            status="active",
        )
        store.save_engagement(eng)
        print(f"[+] Created Engagement: {engagement_id}")

    agent_id = "hr_agent_100"
    agent = store.get_agent(agent_id)
    if not agent:
        agent = Agent(
            id=agent_id,
            engagement_id=engagement_id,
            runner_kind=OutboundAgentV1.runner_kind,
            config={
                "hitl_threshold": 0,  # Disable trust-ramp hitl checks for our custom script execution
                "send_gap_seconds": 60,
            }
        )
        store.save_agent(agent)
        print(f"[+] Created Agent: {agent_id}")

    # 5. Plan and schedule jobs with random delays
    print(f"[*] Scheduling {len(batch)} email jobs in the database...")
    now = datetime.now(timezone.utc)
    current_scheduled_time = now

    jobs_created = 0
    for idx, contact in enumerate(batch):
        prospect_id = f"hr_{idx:03d}"
        prospect = Prospect(
            id=prospect_id,
            engagement_id=engagement_id,
            email=contact["Email"],
            full_name=contact["Name"],
            company=contact["Company"],
            title=contact["Title"],
        )
        store.save_prospect(prospect)

        # Generate a deterministic job ID
        job_id = f"job_hr_{prospect_id}"

        # Spacing: random delay between 60 and 120 seconds (1-2 minutes)
        delay_seconds = random.randint(60, 120)
        current_scheduled_time += timedelta(seconds=delay_seconds)

        # Build email templates
        subject = f"Software Engineer candidate - Meta Hacker Cup Top 1.5% - Tarandeep Singh Juneja"
        body = f"""Hello Hiring Team,

I am interested in Software Engineer opportunities at {contact['Company']}. I have experience in Python, React, FastAPI, PyTorch, and SQL, including independently contributing production PyQt5/Python code to IIT Bombay's FOSSEE Osdag software (serving 10,000+ structural engineers) and ranking 186 globally in the Meta Hacker Cup.

I have attached my resume and included links below. I would appreciate consideration for a suitable current opening.

Resume: Attached PDF (Tarandeep_Resume_AI.pdf)
LinkedIn: https://www.linkedin.com/in/tarandeep-singh-juneja-55542424b
Portfolio: https://portfolio-tsj.netlify.app/
GitHub: https://github.com/tsj2003

Thank you,
Tarandeep Singh Juneja
+91-9098520440 | Bhopal, Madhya Pradesh"""

        payload = {
            "to_email": contact["Email"],
            "to_name": contact["Name"],
            "company": contact["Company"],
            "title": contact["Title"],
            "subject": subject,
            "body_text": body,
            "attachment_paths": [resume_pdf_path],
        }

        # Save email job directly
        job = Job(
            id=job_id,
            engagement_id=engagement_id,
            agent_id=agent_id,
            kind=JobKind.EMAIL_SEND,
            payload=payload,
            prospect_id=prospect_id,
            requires_approval=False,  # Run directly
            scheduled_for=current_scheduled_time,
        )
        
        # Check if already processed or exists
        existing_job = store.get_job(job_id)
        if not existing_job:
            store.save_job(job)
            jobs_created += 1

    print(f"[+] Total jobs queued/planned: {jobs_created}")

    if not live_mode:
        print("\n" + "="*50)
        print("🔍 DRY-RUN MODE ACTIVE (Real emails will NOT be sent)")
        print("="*50)
        print("Reviewing first 3 drafts:")
        for idx in range(min(3, len(batch))):
            prospect_id = f"hr_{idx:03d}"
            job_id = f"job_hr_{prospect_id}"
            job = store.get_job(job_id)
            print(f"\n--- Draft #{idx+1} ---")
            print(f"To: {job.payload['to_email']} ({job.payload['to_name']} - {job.payload['company']})")
            print(f"Subject: {job.payload['subject']}")
            print(f"Attachment: {job.payload['attachment_paths']}")
            print(f"Body:\n{job.payload['body_text']}")
            print("-"*40)
        
        print("\n[!] Dry-Run complete. To start the live sending process, run:")
        print("    PYTHONPATH=. .venv/bin/python scripts/send_hr_outreach.py --live")
        sys.exit(0)

    # 6. Live execution loop with delay sleep
    print("\n" + "="*50)
    print("🚀 LIVE SENDING CAMPAIGN STARTING")
    print("="*50)

    completed = 0
    failed = 0

    # Retrieve all pending jobs sorted by scheduled_for
    all_jobs = list(store.list_jobs_by_state("pending", engagement_id=engagement_id, limit=500))
    all_jobs.sort(key=lambda j: j.scheduled_for)

    print(f"[*] Found {len(all_jobs)} pending outreach jobs.")

    for i, job in enumerate(all_jobs):
        prospect = store.get_prospect(job.prospect_id)
        email = job.payload["to_email"]
        company = job.payload["company"]

        # If job is already succeeded, skip
        if job.state == "succeeded":
            continue

        print(f"\n[{i+1}/{len(all_jobs)}] Sending outreach to {email} ({company})...")
        
        # Execute the single job
        try:
            runtime._execute_one(job)
            
            # Refresh job state
            refreshed_job = store.get_job(job.id)
            if refreshed_job.state == "succeeded":
                print(f"[+] Success! Email sent to {email}.")
                completed += 1
            else:
                print(f"[-] Execution failed: {refreshed_job.last_error}")
                failed += 1
        except Exception as e:
            print(f"[-] Unexpected error: {e}")
            failed += 1

        # Calculate random delay for the next email (between 60 and 120 seconds)
        if i < len(all_jobs) - 1:
            delay = random.randint(60, 120)
            print(f"[*] Sleeping for {delay} seconds (1-2 minutes) to prevent spam flags...")
            time.sleep(delay)

    print("\n" + "="*50)
    print("🏁 OUTREACH CAMPAIGN COMPLETE")
    print(f"    Sent successfully: {completed}")
    print(f"    Failed: {failed}")
    print("="*50)


if __name__ == "__main__":
    main()
