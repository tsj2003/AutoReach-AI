#!/usr/bin/env python3

import argparse
import base64
import csv
import logging
import os
import re
import sys
import time
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, List, Optional, Tuple

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from jinja2 import Environment, FileSystemLoader, select_autoescape
import random

try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

# If modifying these scopes, delete token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Sent emails tracking file
SENT_EMAILS_FILE = "sent_emails.txt"
STATE_FILE = ".campaign_state.json"
FAILED_EMAILS_FILE = "failed_emails.csv"
EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
PLACEHOLDER_VALUES = {"", "-", "--", "na", "n/a", "none", "null", "unknown"}
GENERIC_LOCAL_TOKENS = {
    "admin",
    "apply",
    "application",
    "applications",
    "campus",
    "career",
    "careers",
    "connect",
    "contact",
    "cv",
    "freshers",
    "global",
    "hello",
    "help",
    "hiring",
    "hr",
    "idc",
    "in",
    "india",
    "info",
    "job",
    "jobs",
    "mail",
    "noreply",
    "office",
    "people",
    "recruit",
    "recruiter",
    "recruiting",
    "recruitment",
    "resume",
    "support",
    "ta",
    "talent",
    "team",
}
COMMON_SURNAME_TOKENS = {
    "agarwal",
    "agrawal",
    "bose",
    "das",
    "gupta",
    "iyer",
    "jain",
    "khan",
    "kumar",
    "lobo",
    "mehta",
    "nair",
    "nag",
    "patel",
    "rao",
    "reddy",
    "roy",
    "shah",
    "sharma",
    "singh",
    "soni",
    "verma",
    "yadav",
}
COMPANY_OVERRIDES = {
    "accenture": "Accenture",
    "g10x": "G10X",
    "2isolutions": "2iSolutions",
    "aapnainfotech": "AAPNA Infotech",
}


def load_sent_emails() -> set:
    """Load already-sent emails from tracking file."""
    if not os.path.exists(SENT_EMAILS_FILE):
        return set()
    with open(SENT_EMAILS_FILE, "r") as f:
        return {line.strip().lower() for line in f if line.strip()}


def record_sent_email(email: str):
    """Append a sent email to the tracking file."""
    with open(SENT_EMAILS_FILE, "a") as f:
        f.write(email.lower() + "\n")


def normalize_email(value: Optional[str]) -> str:
    """Return a clean single email address from a CSV cell."""
    if not value:
        return ""
    cleaned = re.sub(r"\s+", "", str(value).strip())
    match = re.search(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}", cleaned)
    return match.group(0).strip().lower() if match else cleaned.lower()


def is_valid_email(email: str) -> bool:
    """Comprehensive email validation with strict checks."""
    if not email or not EMAIL_RE.match(email):
        return False
    
    # Additional validation checks
    email = email.lower()
    
    # Check for truncated domains (.c instead of .com)
    if email.endswith('.c'):
        return False
    
    # Check for double dots
    if '..' in email:
        return False
    
    # Check for leading/trailing dots
    if email.startswith('.') or email.endswith('.'):
        return False
    
    # Check email length
    if len(email) > 254:
        return False
    
    # Check domain part
    domain = email.split('@')[1]
    if domain.endswith('.'):
        return False
    
    # Check for hyphen in TLD
    if '-' in domain.split('.')[-1]:
        return False
    
    return True


def has_valid_mx_record(email: str) -> bool:
    """Check if email domain has valid MX records using DNS."""
    if not DNS_AVAILABLE:
        return True  # Skip if dnspython not installed
    try:
        domain = email.split('@')[-1]
        dns.resolver.resolve(domain, 'MX', tcp=False, lifetime=2.0)
        return True
    except Exception:
        return False



def clean_person_value(value: Optional[str], fallback: str = "") -> str:
    cleaned = str(value or "").strip()
    if cleaned.lower() in PLACEHOLDER_VALUES or not re.search(r"[A-Za-z]", cleaned):
        return fallback
    return cleaned


def format_name_token(token: str) -> str:
    return token.replace("_", " ").replace("-", " ").strip().title()


def email_local_tokens(email: str) -> List[str]:
    local_part = normalize_email(email).split("@", 1)[0]
    return [
        token.lower()
        for token in re.split(r"[^A-Za-z]+", local_part)
        if token and token.lower() not in GENERIC_LOCAL_TOKENS
    ]


def derive_name_from_email(email: str) -> Tuple[str, str]:
    """Derive a conservative first/last name from a personal-looking email."""
    local_part = normalize_email(email).split("@", 1)[0]
    raw_tokens = [
        token.lower()
        for token in re.split(r"[^A-Za-z]+", local_part)
        if token and token.lower() not in GENERIC_LOCAL_TOKENS
    ]
    long_tokens = [token for token in raw_tokens if len(token) > 1]
    if not long_tokens:
        return "", ""

    if len(long_tokens) == 1:
        token = long_tokens[0]
        has_initial_prefix = any(len(token_part) == 1 for token_part in raw_tokens)
        looks_like_initial_plus_surname = len(token) > 3 and token[1:] in COMMON_SURNAME_TOKENS
        if has_initial_prefix or len(token) < 5 or looks_like_initial_plus_surname:
            return "", ""
        return format_name_token(token), ""

    # Handles patterns like jain.nihit@... where the first token is likely a surname.
    if len(long_tokens) >= 2 and long_tokens[0] in COMMON_SURNAME_TOKENS:
        return format_name_token(long_tokens[1]), format_name_token(long_tokens[0])

    first = format_name_token(long_tokens[0])
    last_tokens = [
        token
        for token in long_tokens[1:]
        if len(token) > 1 and token not in GENERIC_LOCAL_TOKENS
    ]
    return first, " ".join(format_name_token(token) for token in last_tokens)


def smart_company_name(value: Optional[str], email: str = "") -> str:
    cleaned = clean_person_value(value, "")
    cleaned = re.sub(r"[_\s]+", " ", cleaned).strip()
    if cleaned.lower() in PLACEHOLDER_VALUES:
        cleaned = ""

    if not cleaned and email and "@" in normalize_email(email):
        domain = normalize_email(email).split("@", 1)[1]
        labels = [label for label in domain.split(".") if label not in {"com", "co", "in", "net", "org", "io"}]
        cleaned = labels[-1] if labels else ""

    key = cleaned.lower().replace(" ", "").replace("-", "")
    if key in COMPANY_OVERRIDES:
        return COMPANY_OVERRIDES[key]
    if cleaned.isupper() or any(char.isdigit() for char in cleaned):
        return cleaned
    return cleaned.title() if cleaned else "your company"


def record_failed_email(row_index: int, email: str, reason: str, row: Dict[str, str]):
    """Append a failed/skipped row to a CSV for later repair."""
    file_exists = os.path.exists(FAILED_EMAILS_FILE)
    with open(FAILED_EMAILS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp", "row_index", "email", "company", "first_name", "reason"],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "row_index": row_index,
                "email": email,
                "company": row.get("company", ""),
                "first_name": row.get("first_name", ""),
                "reason": reason,
            }
        )


def load_campaign_state() -> Dict:
    """Load campaign state from JSON"""
    if not os.path.exists(STATE_FILE):
        return {"status": "idle", "sent": 0, "failed": 0, "total": 0}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"status": "idle", "sent": 0, "failed": 0, "total": 0}


def save_campaign_state(state: Dict):
    """Save campaign state to JSON"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def load_sender_profile(profile_path: Optional[str]) -> Dict[str, str]:
    if not profile_path or not os.path.exists(profile_path):
        return {}
    try:
        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        logging.warning("Could not read sender profile: %s", profile_path)
        return {}
    return {
        f"sender_{key}": str(value)
        for key, value in data.items()
        if value is not None and key != "gemini_api_key"
    }


def handle_rate_limit_error(error_str: str) -> Tuple[bool, Optional[int]]:
    """
    Check if error is rate limit and return retry seconds.
    Returns (is_rate_limit, retry_after_seconds)
    """
    if "quotaExceeded" in error_str or "rateLimitExceeded" in error_str:
        # Gmail rate limit - retry after ~24 hours
        return True, 86400
    elif "429" in error_str:
        # HTTP 429 Too Many Requests
        return True, 3600
    return False, None


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
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Could not read stored Gmail token: %s", exc)
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                backup_path = f"{token_path}.invalid_{datetime.now():%Y%m%d_%H%M%S}"
                try:
                    os.replace(token_path, backup_path)
                    logging.warning(
                        "Stored Gmail token is invalid; backed it up to %s and starting a new authorization flow.",
                        backup_path,
                    )
                except OSError:
                    logging.warning("Stored Gmail token is invalid and could not be backed up.")
                logging.debug("Gmail token refresh failed: %s", exc)
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
    service = build("gmail", "v1", credentials=creds)
    return service


def create_mime_message_with_attachment(
    sender: Optional[str],
    to_address: str,
    subject: str,
    text_body: Optional[str],
    html_body: Optional[str],
    attachment_path: Optional[str] = None,
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

    # Add attachment if provided
    if attachment_path and os.path.exists(attachment_path):
        # Avoid attaching the same filename twice (dedupe)
        filename = os.path.basename(attachment_path)
        already_has = False
        if isinstance(message, MIMEMultipart):
            for part in message.walk():
                try:
                    disp = part.get("Content-Disposition", "")
                except Exception:
                    disp = ""
                if disp and filename in disp:
                    already_has = True
                    break
        if not already_has:
            msg_with_attachment = MIMEMultipart()
            msg_with_attachment.attach(message)
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{filename}"'
            )
            msg_with_attachment.attach(part)
            message = msg_with_attachment

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


def personalize_with_gemini(rendered: RenderedEmail, row: Dict[str, str], args) -> RenderedEmail:
    """Rewrite an already-rendered email with Gemini while preserving the original intent."""
    api_key = args.gemini_api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Gemini personalization is enabled, but no API key was provided.")

    source_body = rendered.text_body or rendered.html_body or ""
    custom_instruction = getattr(args, "personalization_prompt", None) or (
        "Rewrite this cold email for one recipient. Keep it truthful, concise, warm, "
        "and professional. Do not invent facts, offers, roles, metrics, or relationships. "
        "Preserve the sender's intent, links, dates, and attachments."
    )
    prompt = (
        f"{custom_instruction}\n"
        'Return strict JSON with keys "subject" and "body" only.\n\n'
        f"Recipient row JSON:\n{json.dumps(row, ensure_ascii=True)[:6000]}\n\n"
        f"Current subject:\n{rendered.subject}\n\n"
        f"Current body:\n{source_body[:6000]}"
    )
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(args.personalization_model)}:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.45,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini personalization request failed: {exc}") from exc

    text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    try:
        rewritten = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini returned non-JSON personalization output.") from exc

    subject = str(rewritten.get("subject") or rendered.subject).strip()
    body = str(rewritten.get("body") or source_body).strip()
    if not subject or not body:
        raise RuntimeError("Gemini personalization returned an empty subject or body.")

    html_body = rendered.html_body
    if html_body:
        escaped = (
            body.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        html_body = f"<p>{escaped}</p>"

    return RenderedEmail(
        to_address=rendered.to_address,
        subject=subject,
        text_body=body,
        html_body=html_body,
        cc=rendered.cc,
        bcc=rendered.bcc,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send personalized bulk emails via Gmail API using CSV data and Jinja templates with attachments.")
    parser.add_argument("--csv", required=True, help="Path to recipients CSV file.")
    parser.add_argument("--subject", help="Jinja template string for subject, or rely on 'subject' column in CSV.")
    parser.add_argument("--html-template", dest="html_template", help="Path to HTML Jinja template file.")
    parser.add_argument("--text-template", dest="text_template", help="Path to Text Jinja template file.")
    parser.add_argument("--templates-dir", default="templates", help="Templates directory for loading template files.")
    parser.add_argument("--email-column", default="email", help="CSV column name containing recipient email.")
    parser.add_argument("--from", dest="from_address", help="Optional 'From' address (must be a verified Gmail alias).")
    parser.add_argument("--credentials", default="credentials.json", help="Path to Google OAuth client secrets JSON.")
    parser.add_argument("--token", default="token.json", help="Path to store OAuth token.")
    parser.add_argument("--sleep", type=float, default=None, help="Fixed seconds to sleep between sends (deprecated if --sleep-min/max provided).")
    parser.add_argument("--sleep-min", type=float, help="Minimum seconds to sleep between sends (overrides --sleep when set).")
    parser.add_argument("--sleep-max", type=float, help="Maximum seconds to sleep between sends (overrides --sleep when set).")
    parser.add_argument("--limit", type=int, help="Optional limit on number of emails to process.")
    parser.add_argument("--dry-run", action="store_true", help="Render and log emails without sending.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    parser.add_argument("--attachment", help="Path to file to attach to emails (e.g., resume PDF).")
    parser.add_argument("--skip", type=int, default=0, help="Number of CSV rows to skip from the start (useful to resume runs).")
    parser.add_argument("--reverse", action="store_true", help="Process CSV rows in reverse order (start from last row).")
    parser.add_argument("--batch-size", type=int, default=450, help="Batch size for daily sending limit.")
    parser.add_argument("--auto-resume", action="store_true", help="Auto-resume when rate limit resets.")
    parser.add_argument("--auth-only", action="store_true", help="Run Gmail OAuth and exit without sending.")
    parser.add_argument("--personalize", action="store_true", help="Use Gemini to rewrite each email before sending.")
    parser.add_argument("--gemini-api-key", help="Gemini API key. Defaults to GEMINI_API_KEY environment variable.")
    parser.add_argument("--personalization-model", default="gemini-2.0-flash", help="Gemini model used for personalization.")
    parser.add_argument("--personalization-prompt", help="Custom instructions/prompt template for Gemini personalization.")
    parser.add_argument("--sender-profile", default="out/sender_profile.json", help="JSON file with sender profile fields for templates.")
    return parser.parse_args(argv)


def read_csv_rows(csv_path: str) -> List[Dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        # Read all lines to handle files with disclaimer lines before the header
        all_lines = csv_file.read().splitlines()
        header_start = 0
        # Find the first line that looks like a header containing an email column
        for i, line in enumerate(all_lines):
            tokens = [t.strip().lower() for t in line.split(",")]
            if any(t in {"email", "e-mail", "email id", "email_id", "email address", "email_address"} for t in tokens):
                header_start = i
                break
        reader = csv.DictReader(all_lines[header_start:])
        rows: List[Dict[str, str]] = []
        for row in reader:
            # Preserve original keys
            normalized = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
            # Also add sanitized aliases: lowercase, spaces and non-alnum to underscore
            # This allows referencing fields like "Company Name" as {{ company_name }} in templates
            aliases: Dict[str, str] = {}
            for k, v in list(normalized.items()):
                if not isinstance(k, str):
                    continue
                alias = "".join([c if c.isalnum() else "_" for c in k.strip().lower()])
                if alias and alias not in normalized and alias not in aliases:
                    aliases[alias] = v
            # Provide common convenience aliases
            # Map typical email column names to a unified 'email'
            for candidate in ("email", "e_mail", "mail", "email_id", "emailaddress", "email_address", "Email"):
                if candidate in normalized and normalized.get(candidate):
                    aliases.setdefault("email", normalize_email(normalized[candidate]))
            # Map company name variants to 'company'
            for candidate in ("company", "company_name", "Company Name", "organisation", "organization", "employer"):
                if candidate in normalized and normalized.get(candidate):
                    # Prefer an explicit 'company' key
                    aliases.setdefault("company", clean_person_value(normalized[candidate], "your company"))
                    # Ensure 'company_name' exists too
                    aliases.setdefault("company_name", clean_person_value(normalized[candidate], "your company"))
            # Derive hr_name from email local part when not present
            normalized.update(aliases)
            if normalized.get("email"):
                normalized["email"] = normalize_email(normalized["email"])
            if normalized.get("company"):
                normalized["company"] = smart_company_name(normalized["company"], normalized.get("email", ""))
            email_val = normalized.get("email") or normalized.get("Email")
            first_name = clean_person_value(normalized.get("first_name"), "")
            last_name = clean_person_value(normalized.get("last_name"), "")
            if not first_name or first_name == "Hiring Team":
                derived_first, derived_last = derive_name_from_email(str(email_val or ""))
                first_name = derived_first or "Hiring Team"
                last_name = last_name or derived_last
            normalized["first_name"] = first_name
            normalized["last_name"] = last_name
            normalized["hr_name"] = clean_person_value(normalized.get("hr_name"), first_name)
            normalized["company"] = smart_company_name(normalized.get("company"), normalized.get("email", ""))
            rows.append(normalized)
        return rows


def compute_sleep_seconds(args) -> float:
    if args.sleep_min is not None and args.sleep_max is not None and args.sleep_max >= args.sleep_min:
        return random.uniform(args.sleep_min, args.sleep_max)
    if args.sleep is not None:
        return float(args.sleep)
    # default 60s if nothing provided
    return 60.0


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.auth_only:
        if not os.path.exists(args.credentials):
            logging.error("Credentials file not found: %s", args.credentials)
            return 2
        get_gmail_service(args.credentials, args.token)
        logging.info("Gmail authentication complete. Token saved to %s", args.token)
        return 0

    if not args.html_template and not args.text_template:
        logging.error("You must provide at least one of --html-template or --text-template.")
        return 2

    if not os.path.exists(args.csv):
        logging.error("CSV file not found: %s", args.csv)
        return 2

    if not os.path.isdir(args.templates_dir):
        logging.error("Templates directory not found: %s", args.templates_dir)
        return 2

    if args.attachment:
        if args.attachment.lower() in ("none", "null", "undefined", ""):
            args.attachment = None
        elif not os.path.exists(args.attachment):
            logging.error("Attachment file not found: %s", args.attachment)
            return 2

    env = build_jinja_env(args.templates_dir)
    sender_profile = load_sender_profile(args.sender_profile)

    all_rows = read_csv_rows(args.csv)

    # Optionally process rows in reverse order (start from last row)
    if args.reverse:
        all_rows = list(reversed(all_rows))

    # Apply skip first, then limit
    if args.skip:
        rows = all_rows[args.skip:]
    else:
        rows = all_rows

    if args.limit is not None:
        rows = rows[:args.limit]

    service = None
    if not args.dry_run:
        if not os.path.exists(args.credentials):
            logging.error("Credentials file not found: %s", args.credentials)
            return 2
        service = get_gmail_service(args.credentials, args.token)

    # Load already-sent emails to prevent duplicates
    sent_emails = load_sent_emails()
    logging.info("Loaded %d already-sent emails for duplicate prevention", len(sent_emails))

    # Load campaign state
    state = load_campaign_state()
    state.update(
        {
            "status": "dry_run" if args.dry_run else "running",
            "csv": args.csv,
            "subject": args.subject,
            "attachment": args.attachment,
            "total_rows_in_file": len(all_rows),
            "rows_this_run": len(rows),
            "start_skip": args.skip,
            "batch_size": args.batch_size,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_campaign_state(state)
    
    processed = 0
    sent_this_run = 0
    failed_count = 0
    skipped_duplicates = 0
    stopped_for_batch = False
    
    for idx, row in enumerate(rows):
        absolute_index = args.skip + idx
        if not args.dry_run and args.batch_size and sent_this_run >= args.batch_size:
            stopped_for_batch = True
            state.update(
                {
                    "status": "batch_complete",
                    "resume_point": absolute_index,
                    "last_row_index": absolute_index,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            save_campaign_state(state)
            logging.info(
                "Batch limit reached after %d sends. Resume with --skip %d.",
                sent_this_run,
                absolute_index,
            )
            break

        try:
            render_row = {**sender_profile, **row}
            rendered = render_email(
                env=env,
                row=render_row,
                subject_template=args.subject,
                text_template_name=args.text_template,
                html_template_name=args.html_template,
                email_column=args.email_column,
            )

            if args.personalize:
                rendered = personalize_with_gemini(rendered, row, args)

            rendered.to_address = normalize_email(rendered.to_address)
            if not is_valid_email(rendered.to_address):
                logging.warning("SKIPPED (invalid email): %s", rendered.to_address or row)
                record_failed_email(absolute_index, rendered.to_address, "invalid_email", row)
                failed_count += 1
                state.update(
                    {
                        "failed_this_run": failed_count,
                        "last_row_index": absolute_index + 1,
                        "resume_point": absolute_index + 1,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                save_campaign_state(state)
                continue
            
            # MX RECORD CHECK: Skip if domain has no MX records
            if not has_valid_mx_record(rendered.to_address):
                logging.warning("SKIPPED (no MX record): %s", rendered.to_address)
                record_failed_email(absolute_index, rendered.to_address, "no_mx_record", row)
                failed_count += 1
                state.update(
                    {
                        "failed_this_run": failed_count,
                        "last_row_index": absolute_index + 1,
                        "resume_point": absolute_index + 1,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                save_campaign_state(state)
                continue
            
            # DUPLICATE CHECK: Skip if already sent
            email_lower = rendered.to_address.lower()
            if email_lower in sent_emails:
                logging.info("SKIPPED (duplicate): %s", rendered.to_address)
                skipped_duplicates += 1
                state.update(
                    {
                        "skipped_duplicates_this_run": skipped_duplicates,
                        "last_row_index": absolute_index + 1,
                        "resume_point": absolute_index + 1,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                save_campaign_state(state)
                continue
            
            raw, preview = create_mime_message_with_attachment(
                sender=args.from_address,
                to_address=rendered.to_address,
                subject=rendered.subject,
                text_body=rendered.text_body,
                html_body=rendered.html_body,
                attachment_path=args.attachment,
                cc=rendered.cc,
                bcc=rendered.bcc,
            )
        except Exception as exc:  # noqa: BLE001
            logging.exception("Skipping row due to render/build error: %s", exc)
            record_failed_email(absolute_index, row.get(args.email_column, ""), str(exc)[:200], row)
            failed_count += 1
            state.update(
                {
                    "failed_this_run": failed_count,
                    "last_row_index": absolute_index + 1,
                    "resume_point": absolute_index + 1,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            save_campaign_state(state)
            continue

        if args.dry_run:
            logging.info("[DRY-RUN] To=%s Subject=%s", rendered.to_address, rendered.subject)
            if args.attachment:
                logging.info("[DRY-RUN] Attachment: %s", args.attachment)
            logging.debug("\n%s\n", preview)
            state.update(
                {
                    "dry_run_rendered": state.get("dry_run_rendered", 0) + 1,
                    "last_row_index": absolute_index + 1,
                    "resume_point": absolute_index + 1,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            save_campaign_state(state)
        else:
            try:
                # Informative pre-send log so terminal shows live status
                logging.info("SEND %s | %s", rendered.to_address[:30], rendered.subject[:40])
                message_id = send_via_gmail(service, user_id="me", raw_message=raw)
                logging.info("✓ SENT %s (id=%s)", rendered.to_address, message_id[:8])
                # Record sent email to prevent future duplicates
                record_sent_email(rendered.to_address)
                sent_emails.add(email_lower)
                sent_this_run += 1
                
                # Update state
                state.update(
                    {
                        "sent_this_run": sent_this_run,
                        "sent_total_logged": len(sent_emails),
                        "last_success_email": rendered.to_address,
                        "last_row_index": absolute_index + 1,
                        "resume_point": absolute_index + 1,
                        "status": "running",
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                save_campaign_state(state)
                
                time.sleep(compute_sleep_seconds(args))
                
            except HttpError as e:
                error_str = str(e)
                is_rate_limit, retry_secs = handle_rate_limit_error(error_str)
                
                if is_rate_limit:
                    # Rate limited - save state and exit for auto-resume
                    logging.error("✗ RATE_LIMITED: %s", rendered.to_address)
                    state["status"] = "rate_limited"
                    state["failed_this_run"] = failed_count
                    state["last_error"] = "Rate limit exceeded"
                    state["retry_after"] = (datetime.now() + timedelta(seconds=retry_secs)).isoformat()
                    state["resume_point"] = absolute_index
                    state["last_row_index"] = absolute_index
                    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    save_campaign_state(state)
                    
                    if args.auto_resume:
                        logging.info("Auto-resume enabled. Waiting for quota reset...")
                        wait_mins = retry_secs // 60
                        logging.info(f"Waiting {wait_mins} minutes before retry...")
                        # Don't actually wait in background - let external script handle it
                        return 1  # Exit with code 1 to signal rate limit
                    else:
                        logging.info("Paused. Resume with: python quick_cli.py r <csv> <email>")
                        return 1
                else:
                    # Other error - log and continue
                    logging.exception("✗ ERROR %s: %s", rendered.to_address, str(e)[:50])
                    record_failed_email(absolute_index, rendered.to_address, str(e)[:200], row)
                    failed_count += 1
                    state["failed_this_run"] = failed_count
                    state["last_row_index"] = absolute_index + 1
                    state["resume_point"] = absolute_index + 1
                    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    save_campaign_state(state)
                    continue
            except Exception as exc:  # noqa: BLE001
                logging.exception("✗ ERROR %s: %s", rendered.to_address, str(exc)[:50])
                record_failed_email(absolute_index, rendered.to_address, str(exc)[:200], row)
                failed_count += 1
                state["failed_this_run"] = failed_count
                state["last_row_index"] = absolute_index + 1
                state["resume_point"] = absolute_index + 1
                state["updated_at"] = datetime.now().isoformat(timespec="seconds")
                save_campaign_state(state)
                continue
                
        processed += 1

    state["status"] = "batch_complete" if stopped_for_batch else "completed"
    state["processed_this_run"] = processed
    state["sent_this_run"] = sent_this_run
    state["failed_this_run"] = failed_count
    state["skipped_duplicates_this_run"] = skipped_duplicates
    state["sent_total_logged"] = len(sent_emails)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_campaign_state(state)
    
    logging.info(
        "Processed %d rows (sent %d, skipped %d duplicates, %d failed)",
        processed,
        sent_this_run,
        skipped_duplicates,
        failed_count,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
