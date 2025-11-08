#!/usr/bin/env python3
import csv
import re
import subprocess
import time
from pathlib import Path

import dns.resolver

INPUT = "/Users/tarandeepsinghjuneja/Downloads/Copy-Paste Ready Email list - Sheet1.csv"
OUTPUT = "/Users/tarandeepsinghjuneja/email/cleaned_contacts.csv"

CORPORATE_FREE = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
    "proton.me", "zoho.com", "icloud.com", "gmx.com", "yandex.com",
}


def is_email(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", value))


def has_mx(domain: str) -> bool:
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(answers) > 0
    except Exception:  # noqa: BLE001
        return False


def extract_emails_from_row(row: list[str]) -> list[str]:
    emails = []
    for cell in row:
        if not cell:
            continue
        # split by commas
        for part in [p.strip() for p in cell.split(",") if p.strip()]:
            if is_email(part):
                emails.append(part)
    return emails


def clean_csv(input_path: str, output_path: str) -> int:
    seen = set()
    kept = []
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            emails = extract_emails_from_row(row)
            for email in emails:
                local, domain = email.lower().split("@", 1)
                if domain in CORPORATE_FREE:
                    continue
                if not has_mx(domain):
                    continue
                if email.lower() in seen:
                    continue
                seen.add(email.lower())
                first_name = local.split(".")[0].split("_")[0].split("-")[0].title()
                company = domain.split(".")[0].title()
                kept.append({
                    "email": email,
                    "first_name": first_name or "there",
                    "last_name": "",
                    "company": company,
                })
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "first_name", "last_name", "company"])
        writer.writeheader()
        writer.writerows(kept)
    return len(kept)


def main():
    count = clean_csv(INPUT, OUTPUT)
    print(f"Cleaned contacts: {count}")
    if count == 0:
        return 0
    # Dry run 10
    subprocess.run([
        "python", "send_job_applications.py",
        "--csv", OUTPUT,
        "--from", "junejatarandeepsingh@gmail.com",
        "--subject", "Software Development Opportunities - {{ company }}",
        "--text-template", "templates/job_application.txt.j2",
        "--email-column", "email",
        "--dry-run",
        "--batch-size", "10",
    ], check=False)
    # Start send 50 with 60–120s delays
    subprocess.Popen([
        "python", "send_job_applications.py",
        "--csv", OUTPUT,
        "--from", "junejatarandeepsingh@gmail.com",
        "--batch-size", "50",
        "--delay-min", "60",
        "--delay-max", "120",
    ])
    print("Started sending 50 emails with 60–120s delays.")


if __name__ == "__main__":
    main()
