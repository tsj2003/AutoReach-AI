#!/usr/bin/env python3

import argparse
import base64
import csv
import logging
import os
import sys
import time
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from jinja2 import Environment, FileSystemLoader, select_autoescape

# If modifying these scopes, delete token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


@dataclass
class RenderedEmail:
    to_address: str
    subject: str
    text_body: Optional[str]
    html_body: Optional[str]
    cc: Optional[str]
    bcc: Optional[str]


def build_jinja_env(template_dir: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def render_email(
    env: Environment,
    row: Dict[str, str],
    subject_template: Optional[str],
    text_template_name: Optional[str],
    html_template_name: Optional[str],
    email_column: str,
) -> RenderedEmail:
    subject_value = row.get("subject") if row.get("subject") else None
    if subject_template:
        try:
            subject_rendered = env.from_string(subject_template).render(**row)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to render subject for {row.get(email_column)}: {exc}")
    elif subject_value:
        try:
            subject_rendered = env.from_string(subject_value).render(**row)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to render subject from CSV for {row.get(email_column)}: {exc}")
    else:
        raise ValueError("Subject is required. Provide --subject or a 'subject' column in CSV.")

    text_body = None
    html_body = None

    if text_template_name:
        try:
            text_body = env.get_template(os.path.basename(text_template_name)).render(**row)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to render text template for {row.get(email_column)}: {exc}")

    if html_template_name:
        try:
            html_body = env.get_template(os.path.basename(html_template_name)).render(**row)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to render HTML template for {row.get(email_column)}: {exc}")

    to_address = row.get(email_column)
    if not to_address:
        raise ValueError(f"CSV row is missing required email column '{email_column}'. Row: {row}")

    cc_value = row.get("cc")
    bcc_value = row.get("bcc")

    return RenderedEmail(
        to_address=to_address,
        subject=subject_rendered,
        text_body=text_body,
        html_body=html_body,
        cc=cc_value,
        bcc=bcc_value,
    )


def get_gmail_service(credentials_path: str, token_path: str):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
    service = build("gmail", "v1", credentials=creds)
    return service


def create_mime_message(
    sender: Optional[str],
    to_address: str,
    subject: str,
    text_body: Optional[str],
    html_body: Optional[str],
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> Tuple[str, str]:
    if html_body and text_body:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(text_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))
    elif html_body:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(html_body, "html", "utf-8"))
    elif text_body:
        message = MIMEText(text_body, "plain", "utf-8")
    else:
        raise ValueError("At least one of text or HTML body must be provided.")

    message["To"] = to_address
    message["Subject"] = subject
    if sender:
        message["From"] = sender
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return raw_message, message.as_string()


def send_via_gmail(service, user_id: str, raw_message: str) -> str:
    sent = service.users().messages().send(userId=user_id, body={"raw": raw_message}).execute()
    return sent.get("id")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send personalized bulk emails via Gmail API using CSV data and Jinja templates.")
    parser.add_argument("--csv", required=True, help="Path to recipients CSV file.")
    parser.add_argument("--subject", help="Jinja template string for subject, or rely on 'subject' column in CSV.")
    parser.add_argument("--html-template", dest="html_template", help="Path to HTML Jinja template file.")
    parser.add_argument("--text-template", dest="text_template", help="Path to Text Jinja template file.")
    parser.add_argument("--templates-dir", default="templates", help="Templates directory for loading template files.")
    parser.add_argument("--email-column", default="email", help="CSV column name containing recipient email.")
    parser.add_argument("--from", dest="from_address", help="Optional 'From' address (must be a verified Gmail alias).")
    parser.add_argument("--credentials", default="credentials.json", help="Path to Google OAuth client secrets JSON.")
    parser.add_argument("--token", default="token.json", help="Path to store OAuth token.")
    parser.add_argument("--sleep", type=float, default=0.3, help="Seconds to sleep between sends to avoid rate limits.")
    parser.add_argument("--limit", type=int, help="Optional limit on number of emails to process.")
    parser.add_argument("--dry-run", action="store_true", help="Render and log emails without sending.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    return parser.parse_args(argv)


def read_csv_rows(csv_path: str) -> List[Dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows: List[Dict[str, str]] = []
        for row in reader:
            # Preserve original keys
            normalized = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
            # Also add sanitized aliases: lowercase, spaces and non-alnum to underscore
            aliases: Dict[str, str] = {}
            for k, v in list(normalized.items()):
                if not isinstance(k, str):
                    continue
                alias = "".join([c if c.isalnum() else "_" for c in k.strip().lower()])
                if alias and alias not in normalized and alias not in aliases:
                    aliases[alias] = v
            # Common convenience aliases
            for candidate in ("email", "e_mail", "mail", "email_id", "emailaddress", "email_address", "Email"):
                if candidate in normalized and normalized.get(candidate):
                    aliases.setdefault("email", normalized[candidate])
            for candidate in ("company", "company_name", "Company Name", "organisation", "organization", "employer"):
                if candidate in normalized and normalized.get(candidate):
                    aliases.setdefault("company", normalized[candidate])
                    aliases.setdefault("company_name", normalized[candidate])
            normalized.update(aliases)
            # Derive hr_name from email local part when not present
            email_val = normalized.get("email") or normalized.get("Email")
            if email_val and not normalized.get("hr_name"):
                try:
                    local_part = str(email_val).split("@", 1)[0]
                    tokens = [t for s in local_part.replace("_", ".").replace("-", ".").split(".") for t in [s] if s]
                    if tokens:
                        normalized["hr_name"] = tokens[0].capitalize()
                except Exception:  # noqa: BLE001
                    pass
            rows.append(normalized)
        return rows


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.html_template and not args.text_template:
        logging.error("You must provide at least one of --html-template or --text-template.")
        return 2

    if not os.path.exists(args.csv):
        logging.error("CSV file not found: %s", args.csv)
        return 2

    if not os.path.isdir(args.templates_dir):
        logging.error("Templates directory not found: %s", args.templates_dir)
        return 2

    env = build_jinja_env(args.templates_dir)

    rows = read_csv_rows(args.csv)
    if args.limit is not None:
        rows = rows[: args.limit]

    service = None
    if not args.dry_run:
        if not os.path.exists(args.credentials):
            logging.error("Credentials file not found: %s", args.credentials)
            return 2
        service = get_gmail_service(args.credentials, args.token)

    processed = 0
    for row in rows:
        try:
            rendered = render_email(
                env=env,
                row=row,
                subject_template=args.subject,
                text_template_name=args.text_template,
                html_template_name=args.html_template,
                email_column=args.email_column,
            )
            raw, preview = create_mime_message(
                sender=args.from_address,
                to_address=rendered.to_address,
                subject=rendered.subject,
                text_body=rendered.text_body,
                html_body=rendered.html_body,
                cc=rendered.cc,
                bcc=rendered.bcc,
            )
        except Exception as exc:  # noqa: BLE001
            logging.exception("Skipping row due to render/build error: %s", exc)
            continue

        if args.dry_run:
            logging.info("[DRY-RUN] To=%s Subject=%s", rendered.to_address, rendered.subject)
            logging.debug("\n%s\n", preview)
        else:
            try:
                message_id = send_via_gmail(service, user_id="me", raw_message=raw)
                logging.info("Sent to %s (id=%s)", rendered.to_address, message_id)
                time.sleep(args.sleep)
            except Exception as exc:  # noqa: BLE001
                logging.exception("Failed to send to %s: %s", rendered.to_address, exc)
                continue
        processed += 1

    logging.info("Processed %d rows", processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())

