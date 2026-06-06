#!/usr/bin/env python3
"""
scripts/send_direct.py
Direct Gmail API sender — bypasses the engine runtime entirely.
Reads contacts from newlit.csv, sends personalized emails with resume attached,
with random 60-120s delays between sends.

Usage:
    .venv/bin/python -u scripts/send_direct.py
"""

import base64
import csv
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


TOKEN_PATH = os.path.join(os.path.dirname(__file__), "..", "token.json")
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "newlit.csv")
RESUME_PATH = os.path.join(os.path.dirname(__file__), "..", "Tarandeep_Resume_AI (1).pdf")
SENDER = "tarandeepjuneja11@gmail.com"
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "send_log.csv")

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def load_creds():
    """Load and refresh Gmail OAuth credentials."""
    token_path = os.path.abspath(TOKEN_PATH)
    with open(token_path, "r") as f:
        data = json.load(f)

    creds = Credentials.from_authorized_user_info(data, scopes=SCOPES)

    if creds.expired and creds.refresh_token:
        print("[*] Token expired, refreshing...")
        creds.refresh(Request())
        # Save refreshed token
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or []),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }
        with open(token_path, "w") as f:
            json.dump(token_data, f, indent=2)
        print("[+] Token refreshed and saved.")
    elif not creds.valid and not creds.refresh_token:
        print("[-] FATAL: Token expired and no refresh_token. Re-authenticate.")
        sys.exit(1)

    return creds


def build_email(to_email, company, resume_path):
    """Build a MIME email with resume attachment."""
    subject = "Software Engineer candidate - Meta Hacker Cup Top 1.5% - Tarandeep Singh Juneja"

    body = f"""Hello Hiring Team,

I am interested in Software Engineer opportunities at {company}. I have experience in Python, React, FastAPI, PyTorch, and SQL, including independently contributing production PyQt5/Python code to IIT Bombay's FOSSEE Osdag software (serving 10,000+ structural engineers) and ranking 186 globally in the Meta Hacker Cup.

I have attached my resume and included links below. I would appreciate consideration for a suitable current opening.

Resume: Attached PDF (Tarandeep_Resume_AI.pdf)
LinkedIn: https://www.linkedin.com/in/tarandeep-singh-juneja-55542424b
Portfolio: https://portfolio-tsj.netlify.app/
GitHub: https://github.com/tsj2003

Thank you,
Tarandeep Singh Juneja
+91-9098520440 | Bhopal, Madhya Pradesh"""

    outer = MIMEMultipart("mixed")
    outer["From"] = SENDER
    outer["To"] = to_email
    outer["Subject"] = subject
    outer.attach(MIMEText(body, "plain", "utf-8"))

    # Attach resume PDF
    abs_resume = os.path.abspath(resume_path)
    if os.path.exists(abs_resume):
        with open(abs_resume, "rb") as f:
            part = MIMEBase("application", "pdf")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(abs_resume)}"',
        )
        outer.attach(part)
    else:
        print(f"[!] WARNING: Resume not found at {abs_resume}")

    raw = base64.urlsafe_b64encode(outer.as_bytes()).decode("utf-8")
    return raw, subject


def load_contacts():
    """Load contacts from newlit.csv."""
    csv_path = os.path.abspath(CSV_PATH)
    contacts = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append({
                "Email": (row.get("Email") or "").strip(),
                "Name": (row.get("Name") or "").strip(),
                "Company": (row.get("Company") or "").strip(),
                "Title": (row.get("Title") or "").strip(),
            })
    return contacts


def load_already_sent():
    """Load already-sent emails from the log file to resume safely."""
    log_path = os.path.abspath(LOG_PATH)
    sent = set()
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == "sent":
                    sent.add(row.get("email", "").strip().lower())
    return sent


def log_result(email, company, status, message_id="", error=""):
    """Append send result to the log CSV."""
    log_path = os.path.abspath(LOG_PATH)
    file_exists = os.path.exists(log_path)
    with open(log_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "email", "company", "status", "message_id", "error"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            email,
            company,
            status,
            message_id,
            error,
        ])


def main():
    print("=" * 60)
    print("📧 DIRECT GMAIL SENDER — AutoReach HR Outreach")
    print("=" * 60)

    # Load contacts
    contacts = load_contacts()
    print(f"[+] Loaded {len(contacts)} contacts from newlit.csv")

    # Check already sent
    already_sent = load_already_sent()
    if already_sent:
        print(f"[*] {len(already_sent)} emails already sent (will be skipped)")

    # Filter out already sent
    to_send = [c for c in contacts if c["Email"].lower() not in already_sent]
    print(f"[*] {len(to_send)} emails remaining to send")

    if not to_send:
        print("[+] All emails already sent!")
        return

    # Load credentials and build Gmail service
    print("[*] Loading Gmail credentials...")
    creds = load_creds()
    print("[+] Credentials loaded and valid.")

    print("[*] Building Gmail API service...")
    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    print("[+] Gmail service ready.")

    # Send loop
    sent_count = 0
    fail_count = 0

    for i, contact in enumerate(to_send):
        email = contact["Email"]
        company = contact["Company"] or "your company"

        print(f"\n[{i+1}/{len(to_send)}] Sending to {email} ({company})...")

        try:
            raw, subject = build_email(email, company, RESUME_PATH)
            result = gmail.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()

            msg_id = result.get("id", "")
            print(f"  ✅ SENT! Message ID: {msg_id}")
            log_result(email, company, "sent", message_id=msg_id)
            sent_count += 1

        except Exception as e:
            err_str = str(e)
            print(f"  ❌ FAILED: {err_str}")
            log_result(email, company, "failed", error=err_str[:500])
            fail_count += 1

            # If token error, try refreshing once
            if "401" in err_str or "invalid_grant" in err_str or "Insufficient" in err_str:
                print("  [!] Token may have expired mid-run. Attempting refresh...")
                try:
                    creds = load_creds()
                    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
                    print("  [+] Credentials refreshed, continuing...")
                except Exception as re_err:
                    print(f"  [-] Could not refresh: {re_err}")
                    print("  [-] Aborting campaign.")
                    break

        # Random delay between sends (60-120 seconds)
        if i < len(to_send) - 1:
            delay = random.randint(60, 120)
            print(f"  ⏳ Waiting {delay}s before next send...")
            time.sleep(delay)

    print("\n" + "=" * 60)
    print("🏁 CAMPAIGN COMPLETE")
    print(f"   ✅ Sent: {sent_count}")
    print(f"   ❌ Failed: {fail_count}")
    print(f"   📄 Log: {os.path.abspath(LOG_PATH)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
