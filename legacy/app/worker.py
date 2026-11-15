import threading
import time
import random
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import base64
import os
import re
import urllib.parse
import urllib.request
import urllib.error

from jinja2 import Template

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.models import db, Campaign, Contact, CampaignLog, GoogleAuthToken, UserProfile, User, CampaignStep, ContactReplyDraft


logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")

try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

def is_valid_email(email: str) -> bool:
    if not email or not EMAIL_RE.match(email):
        return False
    email = email.lower()
    if email.endswith('.c') or '..' in email or email.startswith('.') or email.endswith('.'):
        return False
    if len(email) > 254:
        return False
    domain = email.split('@')[1]
    if domain.endswith('.') or '-' in domain.split('.')[-1]:
        return False
    return True

def has_valid_mx_record(email: str) -> bool:
    if not DNS_AVAILABLE:
        return True
    try:
        domain = email.split('@')[-1]
        dns.resolver.resolve(domain, 'MX', tcp=False, lifetime=2.0)
        return True
    except Exception:
        return False

def personalize_with_gemini(subject: str, body: str, row: dict, api_key: str, model: str, custom_instruction: str) -> tuple:
    """Rewrite cold email subject and body with Gemini."""
    if not api_key:
        raise ValueError("Gemini API key is required for Pro personalization.")

    instruction = custom_instruction or (
        "Rewrite this cold email for one recipient. Keep it truthful, concise, warm, "
        "and professional. Do not invent facts, offers, roles, metrics, or relationships. "
        "Preserve the sender's intent, links, dates, and attachments."
    )
    prompt = (
        f"{instruction}\n"
        'Return strict JSON with keys "subject" and "body" only.\n\n'
        f"Recipient context:\n{json.dumps(row, ensure_ascii=True)}\n\n"
        f"Current subject:\n{subject}\n\n"
        f"Current body:\n{body}"
    )
    
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model)}:generateContent"
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
    
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    
    rewritten = json.loads(text)
    new_subject = str(rewritten.get("subject") or subject).strip()
    new_body = str(rewritten.get("body") or body).strip()
    return new_subject, new_body

def classify_reply_with_gemini(snippet: str, api_key: str) -> str:
    """Classify if a reply is an out-of-office auto-reply or a manual reply."""
    if not api_key:
        return "manual" # Fallback to manual if no API key
    
    prompt = (
        "Classify this incoming email reply. Tell me if it is an automatic Out-of-Office "
        "reply, bounce back, or automated auto-response, versus a real manual human reply.\n\n"
        f"Email snippet:\n{snippet}\n\n"
        "Return strict JSON with key \"classification\" only, which must be either \"auto\" or \"manual\"."
    )
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }
    try:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        rewritten = json.loads(text)
        return str(rewritten.get("classification") or "manual").strip().lower()
    except Exception as e:
        logger.warning(f"Failed to classify reply with Gemini: {e}")
        return "manual"


def generate_reply_draft_with_gemini(snippet: str, original_subject: str, original_body: str, api_key: str) -> tuple:
    """Analyze incoming reply intent and draft a response using Gemini."""
    if not api_key:
        return "objection", "Please configure Gemini API Key to auto-draft objection responses."
        
    prompt = (
        "Analyze the incoming email reply snippet from a prospect in response to our cold outreach email.\n"
        "Classify the reply intent into one of these categories:\n"
        "1. 'interested': The prospect is interested, wants a call, demo, pricing, or more info.\n"
        "2. 'objection': The prospect has questions, objections, says they are busy right now, or raises concerns.\n"
        "3. 'unsubscribe': The prospect says 'no interest', 'remove me', 'stop', or is polite but uninterested.\n\n"
        "Draft a highly personalized, professional, and friendly response to handle this prospect's reply. "
        "If they are interested, suggest scheduling a call. If they raise an objection, handle it professionally. "
        "If they want to unsubscribe, write: 'Thanks for letting me know. I've removed you from our list.'\n\n"
        f"Original Subject: {original_subject}\n"
        f"Original Body: {original_body}\n"
        f"Incoming Reply: {snippet}\n\n"
        "Return strict JSON with keys \"classification\" and \"suggested_reply\" only."
    )
    
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }
    
    try:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        res_json = json.loads(text)
        classification = str(res_json.get("classification") or "objection").strip().lower()
        suggested_reply = str(res_json.get("suggested_reply") or "").strip()
        
        if classification not in ("interested", "objection", "unsubscribe"):
            classification = "objection"
            
        return classification, suggested_reply
    except Exception as e:
        logger.warning(f"Failed to analyze reply draft with Gemini: {e}")
        return "objection", "Failed to generate reply suggestion automatically."


def scrape_website_homepage(domain_or_url: str) -> dict:
    """Scrapes the homepage of the given domain or URL using urllib, returning title, description, and text."""
    if not domain_or_url:
        return {}
    
    domain_or_url = domain_or_url.strip().lower()
    
    # Skip generic domains
    generic_domains = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'protonmail.com', 
                       'aol.com', 'icloud.com', 'zoho.com', 'yandex.com', 'mail.com', 'gmx.com',
                       'google.com', 'microsoft.com', 'apple.com'}
    
    clean_domain = domain_or_url
    if "://" in clean_domain:
        clean_domain = clean_domain.split("://", 1)[1]
    clean_domain = clean_domain.split("/", 1)[0]
    if clean_domain.startswith("www."):
        clean_domain = clean_domain[4:]
        
    if clean_domain in generic_domains:
        return {}
        
    url = domain_or_url
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html_bytes = response.read(500 * 1024)
            html = html_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.warning(f"Failed to scrape {url}: {e}")
        if url.startswith("https://"):
            url_http = "http://" + url[8:]
            try:
                req = urllib.request.Request(url_http, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    html_bytes = response.read(500 * 1024)
                    html = html_bytes.decode('utf-8', errors='ignore')
            except Exception as e2:
                logger.warning(f"Failed fallback scrape to {url_http}: {e2}")
                return {}
        else:
            return {}
            
    title = ""
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()
        
    description = ""
    desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html, re.IGNORECASE | re.DOTALL)
    if not desc_match:
        desc_match = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', html, re.IGNORECASE | re.DOTALL)
    if not desc_match:
        desc_match = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', html, re.IGNORECASE | re.DOTALL)
        
    if desc_match:
        description = desc_match.group(1).strip()
        
    html_clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.IGNORECASE | re.DOTALL)
    html_clean = re.sub(r'<style[^>]*>.*?</style>', '', html_clean, flags=re.IGNORECASE | re.DOTALL)
    html_clean = re.sub(r'<[^>]+>', ' ', html_clean)
    html_clean = html_clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    html_clean = re.sub(r'\s+', ' ', html_clean).strip()
    
    body_text = html_clean[:2000]
    return {
        "title": title,
        "description": description,
        "body_text": body_text
    }


from app.services.notifications import send_critical_alert

logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def get_next_sending_token(user_id):
    """Retrieve the next GoogleAuthToken to send from, rotating using round-robin and enforcing 50 emails/day."""
    tokens = GoogleAuthToken.query.filter_by(user_id=user_id, active=True, status='active').all()
    if not tokens:
        return None
        
    now_utc = datetime.utcnow()
    for t in tokens:
        if t.last_used_at:
            if t.last_used_at.date() < now_utc.date():
                t.daily_sent_count = 0
                db.session.commit()
        else:
            t.daily_sent_count = 0
            db.session.commit()
            
    eligible_tokens = [t for t in tokens if t.daily_sent_count < 50]
    if not eligible_tokens:
        return None
        
    eligible_tokens.sort(key=lambda x: x.last_used_at or datetime.min)
    return eligible_tokens[0]

class CampaignExecutor:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(CampaignExecutor, cls).__new__(cls)
                cls._instance.active_threads = {} # campaign_id -> {thread, stop_event}
                cls._instance._celery_task_ids = {} # campaign_id -> celery task id
            return cls._instance

    @staticmethod
    def _celery_available():
        """Check if Redis/Celery broker is reachable."""
        redis_url = os.getenv('REDIS_URL')
        if not redis_url:
            return False
        try:
            import redis as redis_lib
            r = redis_lib.Redis.from_url(redis_url, socket_connect_timeout=1)
            r.ping()
            return True
        except Exception:
            return False

    def start_campaign(self, app, campaign_id):
        if self._celery_available():
            return self._start_celery(campaign_id)
        return self._start_thread(app, campaign_id)

    def _start_celery(self, campaign_id):
        """Dispatch campaign execution to Celery task queue."""
        with self._lock:
            if campaign_id in self._celery_task_ids:
                return False
        try:
            from app.tasks import run_campaign_batch
            result = run_campaign_batch.delay(campaign_id)
            with self._lock:
                self._celery_task_ids[campaign_id] = result.id
            logger.info(f"Campaign {campaign_id} dispatched to Celery (task={result.id})")
            return True
        except Exception as e:
            logger.warning(f"Celery dispatch failed, falling back to thread: {e}")
            return False

    def _start_thread(self, app, campaign_id):
        """Fallback: run campaign in a background thread (dev mode)."""
        with self._lock:
            if campaign_id in self.active_threads:
                return False
            
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._run_campaign_loop,
                args=(app, campaign_id, stop_event),
                daemon=True
            )
            self.active_threads[campaign_id] = {
                'thread': thread,
                'stop_event': stop_event
            }
            thread.start()
            return True

    def stop_campaign(self, campaign_id):
        # Try Celery revoke first
        with self._lock:
            if campaign_id in self._celery_task_ids:
                try:
                    from app.celery_app import make_celery
                    celery = make_celery()
                    celery.control.revoke(self._celery_task_ids[campaign_id], terminate=True)
                except Exception as e:
                    logger.warning(f"Celery revoke failed: {e}")
                self._celery_task_ids.pop(campaign_id, None)
                return True
            # Fallback to thread stop
            if campaign_id in self.active_threads:
                self.active_threads[campaign_id]['stop_event'].set()
                self.active_threads.pop(campaign_id)
                return True
            return False

    def is_running(self, campaign_id):
        with self._lock:
            return campaign_id in self.active_threads or campaign_id in self._celery_task_ids


    def _log(self, campaign_id, log_type, message):
        log = CampaignLog(campaign_id=campaign_id, type=log_type, message=message)
        db.session.add(log)
        db.session.commit()

    def _check_replies(self, campaign_id, api_key, gmail_service=None):
        """Scan Gmail messages for any new replies from campaign contacts."""
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return

        if gmail_service:
            # Backwards compatibility/test cases: search all contacts in campaign
            contacts = Contact.query.filter(
                Contact.campaign_id == campaign_id,
                Contact.status.in_(['pending', 'sent', 'completed']),
                Contact.last_sent_at.isnot(None)
            ).all()
            self._scan_contacts_for_replies(campaign_id, contacts, gmail_service, api_key)
        else:
            # SaaS production: scan contacts matching each active inbox
            active_tokens = GoogleAuthToken.query.filter_by(user_id=campaign.user_id, active=True).all()
            for token in active_tokens:
                try:
                    creds = Credentials(
                        token=token.access_token,
                        refresh_token=token.refresh_token,
                        token_uri=token.token_uri,
                        client_id=token.client_id,
                        client_secret=token.client_secret,
                        scopes=token.scopes.split(',') if token.scopes else ["https://www.googleapis.com/auth/gmail.readonly"]
                    )
                    if creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                        token.access_token = creds.token
                        token.expiry = creds.expiry
                        db.session.commit()
                    token_gmail_service = build("gmail", "v1", credentials=creds)
                except Exception as e:
                    logger.warning(f"Failed to authenticate scanner for {token.email}: {e}")
                    continue

                contacts = Contact.query.filter(
                    Contact.campaign_id == campaign_id,
                    Contact.sender_email == token.email,
                    Contact.status.in_(['pending', 'sent', 'completed']),
                    Contact.last_sent_at.isnot(None)
                ).all()
                self._scan_contacts_for_replies(campaign_id, contacts, token_gmail_service, api_key)

    def _scan_contacts_for_replies(self, campaign_id, contacts, gmail_service, api_key):
        for contact in contacts:
            try:
                results = gmail_service.users().messages().list(
                    userId='me', q=f"from:{contact.email}"
                ).execute()
                messages = results.get('messages', [])
                
                has_replied = False
                reply_snippet = ""
                for msg in messages:
                    msg_details = gmail_service.users().messages().get(
                        userId='me', id=msg['id'], format='minimal'
                    ).execute()
                    internal_date = int(msg_details.get('internalDate', 0))
                    
                    if contact.last_sent_at:
                        last_sent_ms = int(contact.last_sent_at.timestamp() * 1000)
                        if internal_date > last_sent_ms:
                            reply_snippet = msg_details.get('snippet', '')
                            classification = "manual"
                            if api_key:
                                classification = classify_reply_with_gemini(reply_snippet, api_key)
                            
                            if classification == "auto":
                                contact.next_send_after = datetime.utcnow() + timedelta(days=5)
                                db.session.commit()
                                self._log(campaign_id, 'info', f"Detected out-of-office reply from {contact.email}. Delaying sequence by 5 days.")
                            else:
                                has_replied = True
                                break
                                
                if has_replied:
                    contact.status = 'replied'
                    db.session.commit()
                    self._log(campaign_id, 'success', f"✓ Reply detected from {contact.email}. Drip sequence paused.")
                    
                    # Generate reply draft suggestion via Gemini
                    existing_draft = ContactReplyDraft.query.filter_by(contact_id=contact.id).first()
                    if not existing_draft and api_key:
                        try:
                            self._log(campaign_id, 'info', f"Generating AI response draft for reply from {contact.email}...")
                            classification, suggested_reply = generate_reply_draft_with_gemini(
                                snippet=reply_snippet,
                                original_subject=contact.campaign.subject_template or "",
                                original_body=contact.campaign.text_template or "",
                                api_key=api_key
                            )
                            draft = ContactReplyDraft(
                                contact_id=contact.id,
                                reply_snippet=reply_snippet[:500],
                                classification=classification,
                                suggested_reply=suggested_reply,
                                status='pending'
                            )
                            db.session.add(draft)
                            db.session.commit()
                        except Exception as ex:
                            logger.warning(f"Failed to generate reply draft: {ex}")
            except Exception as e:
                logger.warning(f"Error checking replies for {contact.email}: {e}")

    def _run_campaign_loop(self, app, campaign_id, stop_event):
        with app.app_context():
            campaign = Campaign.query.get(campaign_id)
            if not campaign:
                return

            campaign.status = 'running'
            db.session.commit()
            
            self._log(campaign_id, 'info', "Starting outreach campaign...")

            # Get user info for tier checking
            user = User.query.get(campaign.user_id)
            is_pro = user.tier == 'pro' if user else False
            api_key = campaign.gemini_api_key or os.getenv("GEMINI_API_KEY")

            # Check if there are active Google mailboxes connected
            active_tokens = GoogleAuthToken.query.filter_by(user_id=campaign.user_id, active=True).all()
            if not active_tokens:
                self._log(campaign_id, 'error', "No active Google mailboxes connected. Go to settings to authorize your accounts.")
                campaign.status = 'paused'
                db.session.commit()
                self.stop_campaign(campaign_id)
                return

            # Load sender profile context
            profile = UserProfile.query.filter_by(user_id=campaign.user_id).first()
            sender_profile_dict = {}
            if profile:
                sender_profile_dict = {
                    "sender_name": profile.name or "",
                    "sender_title": profile.title or "",
                    "sender_company": profile.company or "",
                    "sender_phone": profile.phone or "",
                    "sender_website": profile.website or "",
                    "sender_linkedin": profile.linkedin or "",
                    "sender_github": profile.github or "",
                    "sender_links": profile.links or "",
                    "sender_signature": profile.signature or f"Best,\n{profile.name or ''}"
                }
            else:
                sender_profile_dict = {
                    "sender_name": "", "sender_title": "", "sender_company": "",
                    "sender_phone": "", "sender_website": "", "sender_linkedin": "",
                    "sender_github": "", "sender_links": "", "sender_signature": ""
                }

            while not stop_event.is_set():
                # 1. Run reply detection check
                try:
                    self._check_replies(campaign_id, api_key)
                except Exception as e:
                    self._log(campaign_id, 'warning', f"Reply detection error: {str(e)}")

                # 2. Fetch pending contacts that are ready to send
                now = datetime.utcnow()
                ready_contacts = Contact.query.filter(
                    Contact.campaign_id == campaign_id,
                    Contact.status == 'pending',
                    Contact.next_send_after <= now
                ).order_by(Contact.id).all()

                # Check if there are any pending contacts remaining at all
                any_pending = Contact.query.filter_by(campaign_id=campaign_id, status='pending').first()
                if not any_pending:
                    self._log(campaign_id, 'success', "Outreach campaign completed! All leads processed.")
                    campaign.status = 'completed'
                    db.session.commit()
                    self.stop_campaign(campaign_id)
                    return

                if not ready_contacts:
                    # None of the pending contacts are ready yet. Wait and check again.
                    for _ in range(30):
                        if stop_event.is_set():
                            break
                        time.sleep(1)
                    continue

                sent_this_run = 0
                for contact in ready_contacts:
                    if stop_event.is_set():
                        self._log(campaign_id, 'info', "Campaign execution paused by user.")
                        campaign.status = 'paused'
                        db.session.commit()
                        return

                    # Check batch size limit
                    if campaign.batch_size and sent_this_run >= campaign.batch_size:
                        self._log(campaign_id, 'warning', f"Daily batch limit of {campaign.batch_size} reached. Stopping for safety.")
                        campaign.status = 'batch_complete'
                        db.session.commit()
                        self.stop_campaign(campaign_id)
                        return

                    # Rotate mailbox and get next sending token
                    token_record = get_next_sending_token(campaign.user_id)
                    if not token_record:
                        # Check if any active/healthy tokens exist at all
                        total_active_tokens = GoogleAuthToken.query.filter_by(user_id=campaign.user_id, active=True, status='active').count()
                        if total_active_tokens == 0:
                            self._log(campaign_id, 'error', "All connected mailboxes have been quarantined due to auth errors. Campaign paused.")
                            campaign.status = 'paused_no_active_inbox'
                            db.session.commit()
                            
                            # Send central alert
                            try:
                                user = User.query.get(campaign.user_id)
                                if user and user.email:
                                    send_critical_alert(user.email, campaign.name, "No active connected mailboxes found. All connected pools require re-authentication.")
                            except Exception as alert_err:
                                logger.exception("Failed to send campaign pause alert")
                            
                            self.stop_campaign(campaign_id)
                            return
                        else:
                            self._log(campaign_id, 'error', "All active Google mailboxes have hit their 50 emails/day safety limit. Campaign paused.")
                            campaign.status = 'paused'
                            db.session.commit()
                            self.stop_campaign(campaign_id)
                            return

                    # Set up Gmail API Service for this rotated token
                    try:
                        creds = Credentials(
                            token=token_record.access_token,
                            refresh_token=token_record.refresh_token,
                            token_uri=token_record.token_uri,
                            client_id=token_record.client_id,
                            client_secret=token_record.client_secret,
                            scopes=token_record.scopes.split(',') if token_record.scopes else ["https://www.googleapis.com/auth/gmail.send"]
                        )
                        if creds.expired and creds.refresh_token:
                            creds.refresh(Request())
                            token_record.access_token = creds.token
                            token_record.expiry = creds.expiry
                            db.session.commit()
                        
                        gmail_service = build("gmail", "v1", credentials=creds)

                        # --- Postmaster Tools spam rate check ---
                        try:
                            from app.services.postmaster import get_domain_spam_rate
                            sender_domain = token_record.email.split('@')[1] if '@' in token_record.email else None
                            if sender_domain:
                                spam_rate = get_domain_spam_rate(creds, sender_domain)
                                if spam_rate is not None and spam_rate >= 0.0015:  # 0.15% threshold
                                    self._log(campaign_id, 'error',
                                        f"⚠️ SAFE PAUSE: Domain {sender_domain} spam rate is {spam_rate*100:.2f}% "
                                        f"(threshold: 0.15%). Pausing to protect sender reputation.")
                                    campaign.status = 'paused_high_spam_rate'
                                    db.session.commit()
                                    try:
                                        user = User.query.get(campaign.user_id)
                                        if user and user.email:
                                            send_critical_alert(user.email, campaign.name,
                                                f"Your domain {sender_domain} has a spam complaint rate of "
                                                f"{spam_rate*100:.2f}%. Campaign auto-paused to prevent permanent "
                                                f"damage. The fatal threshold is 0.30%.")
                                    except Exception:
                                        pass
                                    self.stop_campaign(campaign_id)
                                    return
                        except Exception as pm_err:
                            logger.debug(f"Postmaster check skipped: {pm_err}")

                    except Exception as e:
                        err_str = str(e).lower()
                        # Detect auth/credentials errors
                        is_auth_error = any(x in err_str for x in ("invalid_grant", "invalid_credentials", "token", "auth", "unauthorized", "expired", "revoked")) or "refresh" in err_str
                        
                        if is_auth_error:
                            self._log(campaign_id, 'error', f"Mailbox {token_record.email} auth revoked: {str(e)}")
                            token_record.active = False
                            token_record.status = 'reauth_required'
                            db.session.commit()
                            
                            # Check if other healthy tokens exist
                            total_active_tokens = GoogleAuthToken.query.filter_by(user_id=campaign.user_id, active=True, status='active').count()
                            if total_active_tokens == 0:
                                self._log(campaign_id, 'error', "All connected mailboxes have been quarantined due to auth errors. Campaign paused.")
                                campaign.status = 'paused_no_active_inbox'
                                db.session.commit()
                                
                                # Send alert
                                try:
                                    user = User.query.get(campaign.user_id)
                                    if user and user.email:
                                        send_critical_alert(user.email, campaign.name, f"Mailbox {token_record.email} failed auth: {str(e)}. No active mailboxes remaining.")
                                except Exception as alert_err:
                                    logger.exception("Failed to send campaign pause alert")
                                
                                self.stop_campaign(campaign_id)
                                return
                            else:
                                self._log(campaign_id, 'warning', f"Mailbox {token_record.email} quarantined. Rotating to remaining healthy mailboxes.")
                                continue
                        else:
                            self._log(campaign_id, 'error', f"Failed to authenticate with mailbox {token_record.email}: {str(e)}")
                            # Deactivate mailbox to prevent stuck loop
                            token_record.active = False
                            db.session.commit()
                            continue

                    # Validate email
                    email = contact.email
                    if not is_valid_email(email):
                        contact.status = 'failed'
                        contact.error_reason = 'Invalid email syntax'
                        db.session.commit()
                        self._log(campaign_id, 'error', f"Skipped: {email} (Invalid email format)")
                        continue

                    if not has_valid_mx_record(email):
                        contact.status = 'failed'
                        contact.error_reason = 'No valid MX records'
                        db.session.commit()
                        self._log(campaign_id, 'error', f"Skipped: {email} (MX check failed)")
                        continue

                    # Live Target Lookup - scrape homepage if not generic and personalize hook
                    scraped_data = {}
                    scrape_url = None
                    raw_data = contact.get_raw_data()
                    for k in ("website", "url", "domain"):
                        val = raw_data.get(k)
                        if val:
                            scrape_url = str(val).strip()
                            break
                    if not scrape_url and contact.company:
                        company_str = contact.company.strip()
                        if "." in company_str and " " not in company_str:
                            scrape_url = company_str
                    if not scrape_url and contact.email:
                        parts = contact.email.split("@")
                        if len(parts) == 2:
                            scrape_url = parts[1]

                    if scrape_url:
                        try:
                            self._log(campaign_id, 'info', f"Scraping homepage for {contact.email} ({scrape_url})...")
                            scraped_data = scrape_website_homepage(scrape_url)
                        except Exception as e:
                            logger.warning(f"Error scraping homepage for {scrape_url}: {e}")

                    # Prepare render context
                    row_context = contact.get_raw_data()
                    render_context = {**sender_profile_dict, **row_context}
                    # Explicitly pass recipient attributes
                    render_context.setdefault("first_name", contact.first_name or "")
                    render_context.setdefault("last_name", contact.last_name or "")
                    render_context.setdefault("company", contact.company or "")
                    render_context.setdefault("email", contact.email)

                    # Inject scraped page data into render context
                    render_context["target_site_title"] = scraped_data.get("title") or ""
                    render_context["target_site_description"] = scraped_data.get("description") or ""
                    render_context["target_site_text"] = scraped_data.get("body_text") or ""

                    # Determine step template
                    steps = CampaignStep.query.filter_by(campaign_id=campaign_id).order_by(CampaignStep.step_number).all()
                    if steps:
                        current_step_num = contact.current_step or 1
                        step = next((s for s in steps if s.step_number == current_step_num), None)
                        if not step:
                            # Contact has finished all steps
                            contact.status = 'completed'
                            db.session.commit()
                            continue
                        
                        subject_template = step.subject_template
                        text_template = step.text_template
                        html_template = step.html_template
                    else:
                        # Fallback to campaign level templates
                        subject_template = campaign.subject_template
                        text_template = campaign.text_template
                        html_template = campaign.html_template

                    # Render subject and body templates
                    try:
                        subject = Template(subject_template or "Hello {{ company }}").render(**render_context)
                        text_body = Template(text_template or "").render(**render_context)
                        html_body = Template(html_template or "").render(**render_context) if html_template else None
                    except Exception as e:
                        contact.status = 'failed'
                        contact.error_reason = f"Jinja rendering error: {str(e)}"
                        db.session.commit()
                        self._log(campaign_id, 'error', f"Failed template render for {email}: {str(e)}")
                        continue

                    # Apply Gemini Pro Personalization if enabled and user is PRO
                    if campaign.personalize_enabled and is_pro:
                        if api_key:
                            try:
                                self._log(campaign_id, 'info', f"Personalizing email for {email} using AI...")
                                original_text = text_body or html_body or ""
                                subject, text_body = personalize_with_gemini(
                                    subject=subject,
                                    body=original_text,
                                    row=render_context,
                                    api_key=api_key,
                                    model=campaign.personalization_model or "gemini-2.0-flash",
                                    custom_instruction=campaign.personalization_prompt
                                )
                                if html_body:
                                    escaped_body = text_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                                    html_body = f"<p>{escaped_body}</p>"
                            except Exception as e:
                                self._log(campaign_id, 'warning', f"AI Personalization failed for {email} ({str(e)}). Falling back to generic template.")

                    # AI Footprint Scrambler — defeat RETVec structural fingerprinting
                    if api_key and is_pro:
                        try:
                            from app.services.scrambler import scramble_email_structure
                            subject, text_body = scramble_email_structure(
                                subject, text_body, api_key,
                                model=campaign.personalization_model or 'gemini-2.0-flash'
                            )
                            if html_body:
                                escaped_body = text_body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                                html_body = f'<p>{escaped_body}</p>'
                            self._log(campaign_id, 'info', f'AI structure scramble applied for {email}')
                        except Exception as e:
                            self._log(campaign_id, 'warning', f'Scrambler failed for {email} ({e}). Sending with standard structure.')

                    # Ensure contact has an unsubscribe token
                    if not contact.unsubscribe_token:
                        import secrets
                        contact.unsubscribe_token = secrets.token_urlsafe(32)
                        db.session.commit()

                    # Build MIME email message
                    try:
                        mime_msg = MIMEMultipart("alternative") if html_body else MIMEText(text_body, "plain", "utf-8")
                        if html_body:
                            mime_msg.attach(MIMEText(text_body, "plain", "utf-8"))
                            mime_msg.attach(MIMEText(html_body, "html", "utf-8"))

                        # Handle attachment if configured
                        if campaign.attachment_path:
                            # Make absolute relative to project root if relative
                            project_root = app.config['PROJECT_ROOT']
                            full_path = Path(campaign.attachment_path)
                            if not full_path.is_absolute():
                                full_path = project_root / full_path
                            
                            if full_path.exists():
                                filename = full_path.name
                                msg_with_attachment = MIMEMultipart()
                                msg_with_attachment.attach(mime_msg)
                                
                                with open(full_path, "rb") as attachment_file:
                                    part = MIMEBase('application', 'octet-stream')
                                    part.set_payload(attachment_file.read())
                                
                                encoders.encode_base64(part)
                                part.add_header(
                                    'Content-Disposition',
                                    f'attachment; filename="{filename}"'
                                )
                                msg_with_attachment.attach(part)
                                mime_msg = msg_with_attachment
                            else:
                                self._log(campaign_id, 'warning', f"Attachment file not found at: {campaign.attachment_path}")

                        mime_msg["To"] = email
                        mime_msg["Subject"] = subject

                        # Inject RFC 8058 One-Click Unsubscribe headers
                        if contact.unsubscribe_token:
                            app_domain = os.getenv('APP_DOMAIN', 'localhost:8080')
                            unsub_url = f'https://{app_domain}/api/unsubscribe/{contact.unsubscribe_token}'
                            mime_msg['List-Unsubscribe'] = f'<{unsub_url}>'
                            mime_msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
                        
                        raw_msg = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
                    except Exception as e:
                        contact.status = 'failed'
                        contact.error_reason = f"MIME assembly error: {str(e)}"
                        db.session.commit()
                        self._log(campaign_id, 'error', f"Failed to assemble email for {email}: {str(e)}")
                        continue

                    # Send email via Gmail API
                    try:
                        gmail_service.users().messages().send(userId='me', body={"raw": raw_msg}).execute()
                        
                        contact.last_sent_at = datetime.utcnow()
                        contact.sent_at = contact.last_sent_at
                        contact.sender_email = token_record.email
                        
                        # Increment daily sent count and update last_used_at for the token
                        token_record.daily_sent_count += 1
                        token_record.last_used_at = datetime.utcnow()
                        
                        campaign.resume_point += 1
                        
                        # Sequence progression
                        next_step = None
                        if steps:
                            next_step = next((s for s in steps if s.step_number == contact.current_step + 1), None)
                        
                        if next_step:
                            contact.current_step += 1
                            contact.next_send_after = contact.last_sent_at + timedelta(days=next_step.delay_days)
                            self._log(campaign_id, 'success', f"✓ SENT Step {contact.current_step - 1} successfully from {token_record.email} to {email}. Next step scheduled in {next_step.delay_days} days.")
                        else:
                            contact.status = 'completed'
                            self._log(campaign_id, 'success', f"✓ SENT final step successfully from {token_record.email} to {email}. Drip sequence completed.")
                            
                        db.session.commit()
                        sent_this_run += 1
                    except Exception as e:
                        err_str = str(e)
                        is_rate_limit = "quotaExceeded" in err_str or "rateLimitExceeded" in err_str or "429" in err_str
                        is_auth_error = any(x in err_str.lower() for x in ("invalid_grant", "invalid_credentials", "token", "auth", "unauthorized", "expired", "revoked", "401"))
                        
                        if is_auth_error:
                            self._log(campaign_id, 'error', f"Mailbox {token_record.email} auth revoked during send: {err_str}")
                            token_record.active = False
                            token_record.status = 'reauth_required'
                            db.session.commit()
                            
                            # Keep contact pending so it can be retried with a healthy mailbox
                            contact.status = 'pending'
                            db.session.commit()
                            
                            # Check if other healthy tokens exist
                            total_active_tokens = GoogleAuthToken.query.filter_by(user_id=campaign.user_id, active=True, status='active').count()
                            if total_active_tokens == 0:
                                self._log(campaign_id, 'error', "All connected mailboxes have been quarantined due to auth errors. Campaign paused.")
                                campaign.status = 'paused_no_active_inbox'
                                db.session.commit()
                                
                                # Send alert
                                try:
                                    user = User.query.get(campaign.user_id)
                                    if user and user.email:
                                        send_critical_alert(user.email, campaign.name, f"Mailbox {token_record.email} failed auth during send: {err_str}. No active mailboxes remaining.")
                                except Exception as alert_err:
                                    logger.exception("Failed to send campaign pause alert")
                                
                                self.stop_campaign(campaign_id)
                                return
                            else:
                                self._log(campaign_id, 'warning', f"Mailbox {token_record.email} quarantined. Retrying with next healthy mailbox.")
                                continue
                        
                        contact.status = 'failed'
                        contact.error_reason = err_str[:250]
                        db.session.commit()
                        
                        if is_rate_limit:
                            self._log(campaign_id, 'error', f"Gmail rate limit hit! Pausing campaign. Reason: {err_str}")
                            campaign.status = 'paused'
                            db.session.commit()
                            self.stop_campaign(campaign_id)
                            return
                        else:
                            self._log(campaign_id, 'error', f"Failed to send to {email}: {err_str}")

                    # Random delay to prevent spam blocks
                    if contact != ready_contacts[-1]: # Not last contact
                        sleep_time = random.uniform(campaign.sleep_min or 180, campaign.sleep_max or 240)
                        self._log(campaign_id, 'info', f"Sleeping for {sleep_time:.1f}s before next send...")
                        
                        steps_count = int(sleep_time)
                        for _ in range(steps_count):
                            if stop_event.is_set():
                                self._log(campaign_id, 'info', "Campaign execution paused by user during sleep delay.")
                                campaign.status = 'paused'
                                db.session.commit()
                                return
                            time.sleep(1)
                        time.sleep(sleep_time - steps_count)

