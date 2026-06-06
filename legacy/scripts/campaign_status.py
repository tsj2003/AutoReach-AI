#!/usr/bin/env python3

import csv
import json
from pathlib import Path


STATE_FILE = Path(".campaign_state.json")
SENT_FILE = Path("sent_emails.txt")
FAILED_FILE = Path("failed_emails.csv")


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def main() -> int:
    state = {}
    if STATE_FILE.exists():
        with STATE_FILE.open(encoding="utf-8") as f:
            state = json.load(f)

    csv_path = Path(state.get("csv") or "out/hr_reachout_list.csv")
    total_rows = count_csv_rows(csv_path)
    sent_logged = count_lines(SENT_FILE)
    failed_logged = max(count_lines(FAILED_FILE) - 1, 0) if FAILED_FILE.exists() else 0
    resume_point = int(state.get("resume_point") or 0)

    print("Campaign Status")
    print("---------------")
    print(f"status: {state.get('status', 'unknown')}")
    print(f"csv: {csv_path}")
    print(f"subject: {state.get('subject', '')}")
    print(f"attachment: {state.get('attachment', '')}")
    print(f"total rows in current CSV: {total_rows}")
    print(f"sent log count: {sent_logged}")
    print(f"failed/invalid rows logged: {failed_logged}")
    print(f"sent in current run: {state.get('sent_this_run', 0)}")
    print(f"skipped duplicates in current run: {state.get('skipped_duplicates_this_run', 0)}")
    print(f"last success: {state.get('last_success_email', '')}")
    print(f"resume point: {resume_point}")
    print(f"updated at: {state.get('updated_at', '')}")

    if resume_point and csv_path.exists():
        print()
        print("Resume command")
        print("--------------")
        print(
            "python3 bulk_mail_with_attachment.py "
            f"--csv {csv_path} "
            f"--subject \"{state.get('subject', 'SDE 2026 | VIT CSE | IIT Bombay Intern')}\" "
            "--text-template templates/tsj_outreach.txt.j2 "
            "--html-template templates/tsj_outreach.html.j2 "
            f"--attachment {state.get('attachment', 'Tarandeep_Resume_SDE.pdf')} "
            "--sleep-min 90 --sleep-max 150 "
            f"--batch-size {state.get('batch_size', 450)} "
            f"--skip {resume_point}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
