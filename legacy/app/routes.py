from flask import Blueprint, render_template, jsonify, request, current_app, session, redirect, url_for
from pathlib import Path
import json
import os
import re
import csv
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
import urllib.parse
import urllib.request
import urllib.error
import razorpay

from app.models import db, User, UserProfile, GoogleAuthToken, Campaign, Contact, CampaignLog, CampaignStep, ContactReplyDraft
from app.worker import CampaignExecutor, is_valid_email
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.text import MIMEText
import base64
import logging

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)
api_bp = Blueprint("api", __name__)

# Razorpay API Config
# Initialized per request dynamically or configured using:
# RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET environment variables.

# ==================== HELPERS ====================

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not get_current_user():
            session.pop('user_id', None)
            return redirect(url_for('main.login_page'))
        return f(*args, **kwargs)
    return decorated_function

def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not get_current_user():
            session.pop('user_id', None)
            return jsonify({"error": "Unauthorized. Please log in first."}), 401
        return f(*args, **kwargs)
    return decorated_function


def default_sender_profile():
    return {
        "name": "",
        "title": "",
        "company": "",
        "phone": "",
        "website": "",
        "linkedin": "",
        "github": "",
        "links": "",
        "signature": "Best,\n{{ sender_name }}",
    }

# ==================== WEB ROUTES ====================

@main_bp.route("/")
def index():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template("landing.html")

@main_bp.route("/mic-animation.riv")
def mic_animation():
    from flask import send_from_directory, current_app
    import os
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'mic-animation.riv')

@main_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")
        
        if not email or not password:
            return render_template("landing.html", error="Email and password are required.")
            
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return render_template("landing.html", error="User with this email already exists.")
            
        # Create user
        new_user = User(email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        # Initialize profile
        profile = UserProfile(user_id=new_user.id, signature="Best,\n{{ sender_name }}")
        db.session.add(profile)
        
        # Initialize a default Campaign for onboarding
        campaign = Campaign(
            user_id=new_user.id,
            name="My First Campaign",
            subject_template="Quick note for {{ company }}",
            text_template='Hi {{ first_name or "there" }},\n\nI wanted to reach out about {{ company or "your company" }}.\n\n{{ sender_signature }}'
        )
        db.session.add(campaign)
        db.session.commit()
        
        # Track signup event
        try:
            from app.services.analytics import track, identify
            identify(new_user.id, {'email': new_user.email, 'tier': 'free'})
            track(new_user.id, 'user_signed_up', {'method': 'email'})
        except Exception:
            pass
        
        session['user_id'] = new_user.id
        return redirect(url_for('main.dashboard'))
        
    return render_template("landing.html")

@main_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")
        
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return render_template("landing.html", error="Invalid email or password.")
        
        # Track login event
        try:
            from app.services.analytics import track
            track(user.id, 'user_logged_in')
        except Exception:
            pass
            
        session['user_id'] = user.id
        return redirect(url_for('main.dashboard'))
        
    return render_template("landing.html")


@main_bp.route("/logout")
def logout():
    session.pop('user_id', None)
    return redirect(url_for('main.index'))

@main_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("landing.html")

# ==================== Google OAuth Flow ====================

@api_bp.route("/auth/google")
@api_login_required
def api_auth_google():
    # Use client details from environments
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    # Fallback to local file values if env not set (for backwards compat / easy testing)
    if not client_id or not client_secret:
        cred_file = current_app.config["PROJECT_ROOT"] / "credentials.json"
        if cred_file.exists():
            try:
                with open(cred_file) as f:
                    data = json.load(f)
                    web = data.get("web") or data.get("installed")
                    client_id = web.get("client_id")
                    client_secret = web.get("client_secret")
            except Exception:
                pass

    if not client_id or not client_secret:
        return jsonify({"error": "Google OAuth credentials not configured on server. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables."}), 400

    redirect_uri = request.url_root.rstrip('/') + url_for('api.api_auth_google_callback')
    
    # Force custom ports to standard URLs or resolve if run inside a tunnel
    # Gmail API requires redirect URIs to match exact config in Google Console
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/postmaster.readonly openid",
        "access_type": "offline",
        "prompt": "consent"
    }
    
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return redirect(auth_url)

@api_bp.route("/auth/google/callback")
def api_auth_google_callback():
    if 'user_id' not in session:
        return "Authentication error: User session not found.", 401
    
    user_id = session['user_id']
    code = request.args.get("code")
    if not code:
        return "Authorization code missing.", 400

    # Retrieve credentials
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        cred_file = current_app.config["PROJECT_ROOT"] / "credentials.json"
        if cred_file.exists():
            try:
                with open(cred_file) as f:
                    data = json.load(f)
                    web = data.get("web") or data.get("installed")
                    client_id = web.get("client_id")
                    client_secret = web.get("client_secret")
            except Exception:
                pass

    if not client_id or not client_secret:
        return "Google client credentials missing on server.", 500

    redirect_uri = request.url_root.rstrip('/') + url_for('api.api_auth_google_callback')

    # Exchange authorization code for token
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    try:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(token_url, data=data, method="POST")
        with urllib.request.urlopen(req) as res:
            tokens = json.loads(res.read().decode("utf-8"))
    except Exception as e:
        return f"OAuth code exchange failed: {str(e)}", 500

    # Save to database
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token") # Offline access gives refresh token
    expires_in = tokens.get("expires_in", 3600)
    expiry = datetime.utcfromtimestamp(datetime.utcnow().timestamp() + expires_in)

    # Fetch user email using userinfo endpoint
    email = None
    try:
        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        req = urllib.request.Request(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(req) as res:
            userinfo = json.loads(res.read().decode("utf-8"))
            email = userinfo.get("email")
    except Exception as e:
        return f"Failed to retrieve user email from Google: {str(e)}", 500

    if not email:
        return "Could not retrieve email address associated with Google account.", 400

    token_record = GoogleAuthToken.query.filter_by(user_id=user_id, email=email).first()
    if not token_record:
        token_record = GoogleAuthToken(user_id=user_id, email=email)
        db.session.add(token_record)

    token_record.access_token = access_token
    if refresh_token:
        token_record.refresh_token = refresh_token
    token_record.token_uri = token_url
    token_record.client_id = client_id
    token_record.client_secret = client_secret
    token_record.scopes = tokens.get("scope", "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/postmaster.readonly openid")
    token_record.expiry = expiry
    token_record.active = True
    
    db.session.commit()
    
    return redirect(url_for('main.dashboard') + "?auth=success")


# ==================== CAMPAIGN & CONFIG API ====================

@api_bp.route("/campaigns")
@api_login_required
def api_list_campaigns():
    user = get_current_user()
    campaigns = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).all()
    
    return jsonify({
        "campaigns": [{
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "total_contacts": len(c.contacts),
            "sent_contacts": len([x for x in c.contacts if x.last_sent_at is not None]),
            "failed_contacts": len([x for x in c.contacts if x.status == 'failed']),
            "created_at": c.created_at.isoformat()
        } for c in campaigns]
    })

@api_bp.route("/campaign/create", methods=["POST"])
@api_login_required
def api_create_campaign():
    user = get_current_user()
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Campaign name is required"}), 400

    campaign = Campaign(
        user_id=user.id,
        name=name,
        subject_template="Quick note for {{ company }}",
        text_template='Hi {{ first_name or "there" }},\n\nI wanted to reach out about {{ company or "your company" }}.\n\n{{ sender_signature }}'
    )
    db.session.add(campaign)
    db.session.commit()

    return jsonify({"success": True, "campaign_id": campaign.id, "message": f"Campaign '{name}' created."})

@api_bp.route("/campaign/delete/<int:campaign_id>", methods=["POST"])
@api_login_required
def api_delete_campaign(campaign_id):
    user = get_current_user()
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    # Stop executor if running
    CampaignExecutor().stop_campaign(campaign_id)

    db.session.delete(campaign)
    db.session.commit()
    return jsonify({"success": True, "message": "Campaign deleted successfully."})

@api_bp.route("/status")
@api_login_required
def api_status():
    user = get_current_user()
    campaign_id = request.args.get("campaign_id", type=int)
    if not campaign_id:
        # Default to latest campaign
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"error": "No campaign found"}), 404

    total = len(campaign.contacts)
    sent = len([x for x in campaign.contacts if x.last_sent_at is not None])
    failed = len([x for x in campaign.contacts if x.status == 'failed'])
    remaining = len([x for x in campaign.contacts if x.status == 'pending'])
    
    progress = (sent / total * 100) if total > 0 else 0
    running = CampaignExecutor().is_running(campaign.id)

    return jsonify({
        "user_id": user.id,
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "status": campaign.status if running else ("stopped" if campaign.status in ("running", "stopped") else campaign.status),
        "total_contacts": total,
        "emails_sent": sent,
        "emails_failed": failed,
        "remaining": remaining,
        "progress_percent": round(progress, 1),
        "resume_point": campaign.resume_point,
        "batch_size": campaign.batch_size,
        "sleep_min": campaign.sleep_min,
        "sleep_max": campaign.sleep_max,
        "personalize_enabled": campaign.personalize_enabled,
        "campaign_subject": campaign.subject_template or "Quick note for {{ company }}",
        "process_running": running,
        "user_tier": user.tier,
        "updated_at": campaign.updated_at.isoformat()
    })

@api_bp.route("/config")
@api_login_required
def api_config():
    user = get_current_user()
    campaign_id = request.args.get("campaign_id", type=int)
    if not campaign_id:
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"error": "No campaign found"}), 404

    tokens = GoogleAuthToken.query.filter_by(user_id=user.id).all()
    token_ready = len(tokens) > 0 and any(t.active for t in tokens)
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    
    # Format profile dict
    profile_dict = default_sender_profile()
    if profile:
        profile_dict.update({
            "name": profile.name or "",
            "title": profile.title or "",
            "company": profile.company or "",
            "phone": profile.phone or "",
            "website": profile.website or "",
            "linkedin": profile.linkedin or "",
            "github": profile.github or "",
            "links": profile.links or "",
            "signature": profile.signature or "Best,\n{{ sender_name }}",
        })

    return jsonify({
        "user_id": user.id,
        "campaign_id": campaign.id,
        "subject": campaign.subject_template or "Quick note for {{ company }}",
        "text_template": campaign.text_template or "",
        "html_template": campaign.html_template or "",
        "credentials_uploaded": bool(os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_SECRET") or (current_app.config["PROJECT_ROOT"] / "credentials.json").exists()),
        "token_ready": token_ready,
        "auth_status": "Connected" if token_ready else "Needs configuration",
        "tokens": [{
            "id": t.id,
            "email": t.email,
            "active": t.active,
            "status": t.status,
            "daily_sent_count": t.daily_sent_count,
            "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None
        } for t in tokens],
        "personalize_enabled": campaign.personalize_enabled,
        "personalization_model": campaign.personalization_model or "gemini-2.0-flash",
        "personalization_prompt": campaign.personalization_prompt or "",
        "gemini_key_saved": bool(campaign.gemini_api_key or os.getenv("GEMINI_API_KEY")),
        "batch_size": campaign.batch_size,
        "sleep_min": campaign.sleep_min,
        "sleep_max": campaign.sleep_max,
        "attachment": campaign.attachment_path or "",
        "attachment_uploaded": bool(campaign.attachment_path),
        "sender_profile": profile_dict,
        "user_tier": user.tier
    })

@api_bp.route("/logs")
@api_login_required
def api_logs():
    user = get_current_user()
    campaign_id = request.args.get("campaign_id", type=int)
    lines = request.args.get("lines", 50, type=int)
    
    if not campaign_id:
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"logs": []})

    logs = CampaignLog.query.filter_by(campaign_id=campaign.id).order_by(CampaignLog.id.desc()).limit(lines).all()
    parsed = []
    
    # Reverse to read chronologically in dashboard terminal
    for log in reversed(logs):
        parsed.append({
            "raw": f"[{log.timestamp.strftime('%H:%M:%S')}] {log.message}",
            "type": log.type
        })
        
    return jsonify({"logs": parsed})

@api_bp.route("/campaign/update", methods=["POST"])
@api_login_required
def api_update_campaign():
    user = get_current_user()
    data = request.get_json()
    campaign_id = data.get("campaign_id")
    
    if not campaign_id:
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    # Update sending params
    if "batch_size" in data:
        campaign.batch_size = int(data["batch_size"])
    if "sleep_min" in data:
        campaign.sleep_min = int(data["sleep_min"])
    if "sleep_max" in data:
        campaign.sleep_max = int(data["sleep_max"])
    if "resume_point" in data:
        campaign.resume_point = int(data["resume_point"])
    if "subject" in data:
        campaign.subject_template = str(data["subject"])
    if "attachment" in data:
        campaign.attachment_path = str(data["attachment"])
    if "personalize_enabled" in data:
        campaign.personalize_enabled = bool(data["personalize_enabled"])
    if "personalization_model" in data:
        campaign.personalization_model = str(data["personalization_model"])
    if "personalization_prompt" in data:
        campaign.personalization_prompt = str(data["personalization_prompt"])
    if "gemini_api_key" in data and data["gemini_api_key"]:
        campaign.gemini_api_key = str(data["gemini_api_key"])
        
    # Save profile if present
    if "sender_profile" in data and isinstance(data["sender_profile"], dict):
        profile = UserProfile.query.filter_by(user_id=user.id).first()
        if not profile:
            profile = UserProfile(user_id=user.id)
            db.session.add(profile)
        
        prof_data = data["sender_profile"]
        profile.name = str(prof_data.get("name", ""))
        profile.title = str(prof_data.get("title", ""))
        profile.company = str(prof_data.get("company", ""))
        profile.phone = str(prof_data.get("phone", ""))
        profile.website = str(prof_data.get("website", ""))
        profile.linkedin = str(prof_data.get("linkedin", ""))
        profile.github = str(prof_data.get("github", ""))
        profile.links = str(prof_data.get("links", ""))
        profile.signature = str(prof_data.get("signature", ""))

    db.session.commit()
    return jsonify({"success": True, "message": "Campaign parameters updated successfully."})

@api_bp.route("/save-template", methods=["POST"])
@api_login_required
def api_save_template():
    user = get_current_user()
    data = request.get_json() or {}
    campaign_id = data.get("campaign_id")
    
    if not campaign_id:
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
        
    if 'text' in data:
        campaign.text_template = data['text']
    if 'html' in data:
        campaign.html_template = data['html']
    if 'subject' in data:
        campaign.subject_template = data['subject']
        
    db.session.commit()
    return jsonify({"success": True, "message": "Outreach template saved."})

@api_bp.route("/upload-contacts", methods=["POST"])
@api_login_required
def api_upload_contacts():
    user = get_current_user()
    campaign_id = request.form.get("campaign_id", type=int)
    
    if not campaign_id:
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    
    # Parse CSV contents
    raw_count = 0
    dupes_count = 0
    invalid_count = 0
    valid_contacts = []
    seen_emails = set()
    
    # Load already imported contacts for this campaign to prevent duplicates
    existing_contacts = Contact.query.filter_by(campaign_id=campaign.id).all()
    for c in existing_contacts:
        seen_emails.add(c.email.lower())

    try:
        content = file.read().decode('utf-8', errors='ignore').splitlines()
        header_start = 0
        for i, line in enumerate(content):
            tokens = [t.strip().lower() for t in line.split(",")]
            if any(t in {"email", "e-mail", "email id", "email_id", "email address", "email_address"} for t in tokens):
                header_start = i
                break
        
        reader = csv.DictReader(content[header_start:])
        for row in reader:
            raw_count += 1
            # Parse rows into normalized structures
            normalized = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
            
            # Find email key
            email_val = None
            for key in ("email", "e_mail", "mail", "email_id", "emailaddress", "email_address", "Email"):
                if key in normalized and normalized[key]:
                    email_val = normalized[key].strip().lower()
                    break
                    
            if not email_val:
                # Find any email matches in values
                for val in normalized.values():
                    match = re.search(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}', str(val))
                    if match:
                        email_val = match.group(0).lower()
                        break
            
            if not email_val or not is_valid_email(email_val):
                invalid_count += 1
                continue
                
            if email_val in seen_emails:
                dupes_count += 1
                continue
                
            seen_emails.add(email_val)
            
            # Extract names & company
            first_name = normalized.get("first_name", "")
            last_name = normalized.get("last_name", "")
            company = normalized.get("company", normalized.get("company_name", ""))
            
            contact = Contact(
                campaign_id=campaign.id,
                email=email_val,
                first_name=first_name,
                last_name=last_name,
                company=company,
                status='pending'
            )
            contact.set_raw_data(normalized)
            valid_contacts.append(contact)

        # Save to DB
        if valid_contacts:
            db.session.add_all(valid_contacts)
            db.session.commit()

    except Exception as e:
        return jsonify({"error": f"Failed parsing contacts file: {str(e)}"}), 500

    return jsonify({
        "success": True,
        "message": f"Successfully imported {len(valid_contacts)} new leads to campaign '{campaign.name}'.",
        "stats": {
            "raw_count": raw_count,
            "dupes": dupes_count,
            "invalid": invalid_count,
            "ready": len(valid_contacts),
            "filename": filename,
            "rejected_samples": []
        }
    })

@api_bp.route("/upload-attachment", methods=["POST"])
@api_login_required
def api_upload_attachment():
    user = get_current_user()
    campaign_id = request.form.get("campaign_id", type=int)
    
    if not campaign_id:
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    upload_name = secure_filename(file.filename)
    allowed_ext = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
    ext = Path(upload_name).suffix.lower()
    if ext not in allowed_ext:
        return jsonify({"error": "Upload a PDF, DOC, DOCX, TXT, PNG, or JPG file."}), 400

    # User-specific attachment path
    upload_dir = current_app.config["PROJECT_ROOT"] / "out" / "attachments" / str(user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_path = upload_dir / upload_name
    file.save(saved_path)

    # Relative path stored in DB
    campaign.attachment_path = str(saved_path.relative_to(current_app.config["PROJECT_ROOT"]))
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Attachment saved: {upload_name}",
        "attachment": campaign.attachment_path,
    })

@api_bp.route("/campaign/start", methods=["POST"])
@api_login_required
def api_start_campaign():
    user = get_current_user()
    campaign_id = request.json.get("campaign_id") if request.json else None
    
    if not campaign_id:
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    # Pre-flight DNS check — block launch if sender domain DNS is broken
    try:
        from app.services.dns_validator import validate_sender_dns
        active_tokens = GoogleAuthToken.query.filter_by(
            user_id=user.id, active=True, status='active'
        ).all()
        for tok in active_tokens:
            if '@' in (tok.email or ''):
                domain = tok.email.split('@')[1]
                dns_result = validate_sender_dns(domain)
                if dns_result.get('available') and not dns_result.get('overall_pass'):
                    missing = []
                    fixes = {}
                    for check in ('spf', 'dkim', 'dmarc'):
                        if not dns_result[check]['valid']:
                            missing.append(check.upper())
                            fixes[check] = dns_result[check].get('fix', '')
                    return jsonify({
                        "error": f"DNS authentication incomplete for {domain}. Missing: {', '.join(missing)}. "
                                 f"Fix these records before launching to protect your sender reputation.",
                        "dns_result": dns_result,
                        "missing_records": missing,
                        "fixes": fixes
                    }), 400
                break  # Only check the first active token's domain
    except Exception as dns_err:
        # Don't block launch if DNS check itself fails
        pass

    # Trigger worker
    executor = CampaignExecutor()
    started = executor.start_campaign(current_app._get_current_object(), campaign.id)
    if not started:
        return jsonify({"error": "Campaign already running."}), 400

    # Track campaign start
    try:
        from app.services.analytics import track
        track(user.id, 'campaign_started', {'campaign_id': campaign.id, 'campaign_name': campaign.name})
    except Exception:
        pass

    return jsonify({"success": True, "message": "Campaign launched! Background engine is active."})

@api_bp.route("/campaign/stop", methods=["POST"])
@api_login_required
def api_stop_campaign():
    user = get_current_user()
    campaign_id = request.json.get("campaign_id") if request.json else None
    
    if not campaign_id:
        campaign = Campaign.query.filter_by(user_id=user.id).order_by(Campaign.id.desc()).first()
    else:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()

    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    stopped = CampaignExecutor().stop_campaign(campaign.id)
    if not stopped:
        # Just ensure status in DB is paused
        campaign.status = 'paused'
        db.session.commit()

    return jsonify({"success": True, "message": "Campaign paused successfully."})

@api_bp.route("/sync-logs", methods=["POST"])
@api_login_required
def api_sync_logs():
    # Since DB models keep sync automatically, just return OK
    return jsonify({"success": True, "message": "Synced database point."})


# ==================== CAMPAIGN DRIP STEPS & CONTACTS API ====================

@api_bp.route("/campaigns/<int:campaign_id>/steps", methods=["GET"])
@api_login_required
def api_get_campaign_steps(campaign_id):
    user = get_current_user()
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
    
    steps = CampaignStep.query.filter_by(campaign_id=campaign.id).order_by(CampaignStep.step_number).all()
    return jsonify({
        "steps": [{
            "id": s.id,
            "campaign_id": s.campaign_id,
            "step_number": s.step_number,
            "subject_template": s.subject_template,
            "text_template": s.text_template,
            "html_template": s.html_template,
            "delay_days": s.delay_days
        } for s in steps]
    })

@api_bp.route("/campaigns/<int:campaign_id>/steps", methods=["POST"])
@api_login_required
def api_create_campaign_step(campaign_id):
    user = get_current_user()
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
        
    data = request.get_json() or {}
    
    max_step = db.session.query(db.func.max(CampaignStep.step_number)).filter_by(campaign_id=campaign.id).scalar()
    next_step_num = (max_step or 0) + 1
    
    step = CampaignStep(
        campaign_id=campaign.id,
        step_number=next_step_num,
        subject_template=data.get("subject_template", "Follow up: {{ subject }}"),
        text_template=data.get("text_template", "Hi {{ first_name }},\n\nJust following up on my last email.\n\nBest,\n{{ sender_name }}"),
        html_template=data.get("html_template", ""),
        delay_days=data.get("delay_days", 3)
    )
    
    db.session.add(step)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "step": {
            "id": step.id,
            "campaign_id": step.campaign_id,
            "step_number": step.step_number,
            "subject_template": step.subject_template,
            "text_template": step.text_template,
            "html_template": step.html_template,
            "delay_days": step.delay_days
        }
    })

@api_bp.route("/campaigns/<int:campaign_id>/steps/<int:step_id>", methods=["PUT"])
@api_login_required
def api_update_campaign_step(campaign_id, step_id):
    user = get_current_user()
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
        
    step = CampaignStep.query.filter_by(id=step_id, campaign_id=campaign.id).first()
    if not step:
        return jsonify({"error": "Step not found"}), 404
        
    data = request.get_json() or {}
    if "subject_template" in data:
        step.subject_template = data["subject_template"]
    if "text_template" in data:
        step.text_template = data["text_template"]
    if "html_template" in data:
        step.html_template = data["html_template"]
    if "delay_days" in data:
        step.delay_days = int(data["delay_days"])
        
    db.session.commit()
    
    return jsonify({
        "success": True,
        "step": {
            "id": step.id,
            "campaign_id": step.campaign_id,
            "step_number": step.step_number,
            "subject_template": step.subject_template,
            "text_template": step.text_template,
            "html_template": step.html_template,
            "delay_days": step.delay_days
        }
    })

@api_bp.route("/campaigns/<int:campaign_id>/steps/<int:step_id>", methods=["DELETE"])
@api_login_required
def api_delete_campaign_step(campaign_id, step_id):
    user = get_current_user()
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
        
    step = CampaignStep.query.filter_by(id=step_id, campaign_id=campaign.id).first()
    if not step:
        return jsonify({"error": "Step not found"}), 404
        
    db.session.delete(step)
    db.session.commit()
    
    # Reorder remaining steps
    remaining_steps = CampaignStep.query.filter_by(campaign_id=campaign.id).order_by(CampaignStep.step_number).all()
    for idx, s in enumerate(remaining_steps):
        s.step_number = idx + 1
    db.session.commit()
    
    return jsonify({"success": True, "message": "Step deleted and remaining steps reordered."})

@api_bp.route("/campaigns/<int:campaign_id>/contacts")
@api_login_required
def api_campaign_contacts(campaign_id):
    user = get_current_user()
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
        
    contacts = Contact.query.filter_by(campaign_id=campaign.id).all()
    
    step_metrics = {}
    for c in contacts:
        key = f"step_{c.current_step}_{c.status}"
        step_metrics[key] = step_metrics.get(key, 0) + 1
        step_metrics[c.status] = step_metrics.get(c.status, 0) + 1
        
    return jsonify({
        "contacts": [{
            "id": c.id,
            "email": c.email,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "company": c.company,
            "status": c.status,
            "current_step": c.current_step,
            "last_sent_at": c.last_sent_at.isoformat() if c.last_sent_at else None,
            "next_send_after": c.next_send_after.isoformat() if c.next_send_after else None,
            "raw_variables": c.get_raw_data()
        } for c in contacts],
        "metrics": step_metrics
    })



# ==================== RAZORPAY & SIMULATOR API ====================

@api_bp.route("/razorpay/create-order", methods=["POST"])
@api_login_required
def api_razorpay_create_order():
    user = get_current_user()
    price_tier = request.json.get("tier", "pro") # 'basic' or 'pro'
    
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    
    # Check if Razorpay keys are configured. If not, fallback to simulation mode.
    if not key_id or not key_secret or key_id == "rzp_test_mock":
        user.tier = price_tier
        db.session.commit()
        return jsonify({
            "simulation": True,
            "url": url_for("main.dashboard") + "?payment=success"
        })
        
    amount_in_paise = 49900 if price_tier == "pro" else 29900
    
    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        order_data = {
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": f"receipt_{user.id}_{int(datetime.utcnow().timestamp())}",
            "payment_capture": 1
        }
        order = client.order.create(data=order_data)
        
        user.razorpay_subscription_id = order['id']
        db.session.commit()
        
        return jsonify({
            "success": True,
            "simulation": False,
            "key": key_id,
            "amount": order['amount'],
            "currency": order['currency'],
            "order_id": order['id'],
            "user_email": user.email,
            "user_name": user.profile.name if (user.profile and user.profile.name) else user.email.split('@')[0]
        })
    except Exception as e:
        return jsonify({"error": f"Razorpay Order Error: {str(e)}"}), 500


@api_bp.route("/razorpay/verify-payment", methods=["POST"])
@api_login_required
def api_razorpay_verify_payment():
    user = get_current_user()
    data = request.get_json() or {}
    
    payment_id = data.get("razorpay_payment_id")
    order_id = data.get("razorpay_order_id")
    signature = data.get("razorpay_signature")
    price_tier = data.get("tier", "pro")
    
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    
    if not key_id or not key_secret or key_id == "rzp_test_mock":
        user.tier = price_tier
        db.session.commit()
        return jsonify({"success": True, "message": "Simulated verification success"})
        
    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        # Verify payment signature
        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        client.utility.verify_payment_signature(params_dict)
        
        user.tier = price_tier
        user.razorpay_customer_id = payment_id
        user.razorpay_subscription_id = order_id
        db.session.commit()
        
        return jsonify({"success": True, "message": "Payment verified successfully!"})
    except Exception as e:
        return jsonify({"error": f"Signature verification failed: {str(e)}"}), 400


@api_bp.route("/razorpay/webhook", methods=["POST"])
def razorpay_webhook():
    return "OK", 200


# Developer Sandbox upgrade shortcut
@api_bp.route("/sandbox/upgrade", methods=["POST"])
@api_login_required
def api_sandbox_upgrade():
    user = get_current_user()
    tier = request.json.get("tier", "pro")
    user.tier = tier
    db.session.commit()
    return jsonify({"success": True, "tier": user.tier, "message": f"Successfully simulated tier upgrade to {tier}."})


@api_bp.route("/auth/tokens/<int:token_id>/delete", methods=["POST"])
@api_login_required
def api_delete_token(token_id):
    user = get_current_user()
    token_record = GoogleAuthToken.query.filter_by(id=token_id, user_id=user.id).first()
    if not token_record:
        return jsonify({"error": "Inbox connection not found"}), 404
        
    db.session.delete(token_record)
    db.session.commit()
    return jsonify({"success": True, "message": "Inbox connection removed."})


@api_bp.route("/reply-drafts", methods=["GET"])
@api_login_required
def api_list_reply_drafts():
    user = get_current_user()
    campaigns = Campaign.query.filter_by(user_id=user.id).all()
    campaign_ids = [c.id for c in campaigns]
    if not campaign_ids:
        return jsonify({"drafts": []})
        
    drafts = ContactReplyDraft.query.join(Contact).filter(
        Contact.campaign_id.in_(campaign_ids),
        ContactReplyDraft.status == 'pending'
    ).order_by(ContactReplyDraft.created_at.desc()).all()
    
    return jsonify({
        "drafts": [{
            "id": d.id,
            "contact_id": d.contact_id,
            "contact_email": d.contact.email,
            "contact_name": f"{d.contact.first_name or ''} {d.contact.last_name or ''}".strip(),
            "campaign_name": d.contact.campaign.name,
            "reply_snippet": d.reply_snippet,
            "classification": d.classification,
            "suggested_reply": d.suggested_reply,
            "created_at": d.created_at.isoformat()
        } for d in drafts]
    })


@api_bp.route("/reply-drafts/<int:draft_id>/send", methods=["POST"])
@api_login_required
def api_send_reply_draft(draft_id):
    user = get_current_user()
    draft = ContactReplyDraft.query.get(draft_id)
    if not draft:
        return jsonify({"error": "Reply draft not found"}), 404
        
    if draft.contact.campaign.user_id != user.id:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json() or {}
    reply_text = data.get("reply_text", "").strip() or draft.suggested_reply
    if not reply_text:
        return jsonify({"error": "Reply message content cannot be empty"}), 400
        
    # Send reply via the same email that sent the original email (if active)
    sender_email = draft.contact.sender_email
    token_record = None
    if sender_email:
        token_record = GoogleAuthToken.query.filter_by(user_id=user.id, email=sender_email, active=True).first()
        
    if not token_record:
        # Fallback to any active token
        token_record = GoogleAuthToken.query.filter_by(user_id=user.id, active=True).first()
        
    if not token_record:
        return jsonify({"error": "No active Google mailbox connection found."}), 400
        
    # Get credentials & refresh if needed
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
    except Exception as e:
        return jsonify({"error": f"Failed to authenticate with sender mailbox: {str(e)}"}), 500
        
    # Find thread ID of previous messages to/from this contact
    thread_id = None
    try:
        results = gmail_service.users().messages().list(userId='me', q=f"to:{draft.contact.email}").execute()
        messages = results.get('messages', [])
        if messages:
            thread_id = messages[0].get('threadId')
    except Exception as ex:
        logger.warning(f"Failed to locate existing Gmail thread: {ex}")
        
    # Build MIME message
    try:
        mime_msg = MIMEText(reply_text, "plain", "utf-8")
        mime_msg["To"] = draft.contact.email
        
        # Get subject of original campaign
        subj = draft.contact.campaign.subject_template or "Outreach"
        if not subj.lower().startswith("re:"):
            subj = "Re: " + subj
        mime_msg["Subject"] = subj
        
        raw_msg = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
    except Exception as e:
        return jsonify({"error": f"Failed to construct MIME email: {str(e)}"}), 500
        
    # Send message
    try:
        body = {"raw": raw_msg}
        if thread_id:
            body["threadId"] = thread_id
            
        gmail_service.users().messages().send(userId='me', body=body).execute()
        
        draft.status = 'sent'
        db.session.commit()
        return jsonify({"success": True, "message": "Reply draft sent successfully."})
    except Exception as e:
        return jsonify({"error": f"Failed to send email via Gmail: {str(e)}"}), 500


@api_bp.route("/reply-drafts/<int:draft_id>/discard", methods=["POST"])
@api_login_required
def api_discard_reply_draft(draft_id):
    user = get_current_user()
    draft = ContactReplyDraft.query.get(draft_id)
    if not draft:
        return jsonify({"error": "Reply draft not found"}), 404
        
    if draft.contact.campaign.user_id != user.id:
        return jsonify({"error": "Unauthorized"}), 403
        
    draft.status = 'discarded'
    db.session.commit()
    return jsonify({"success": True, "message": "Reply draft discarded."})


@api_bp.route("/reply-drafts/<int:draft_id>/save", methods=["POST"])
@api_login_required
def api_save_reply_draft(draft_id):
    user = get_current_user()
    draft = ContactReplyDraft.query.get(draft_id)
    if not draft:
        return jsonify({"error": "Reply draft not found"}), 404
        
    if draft.contact.campaign.user_id != user.id:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json() or {}
    suggested_reply = data.get("suggested_reply", "").strip()
    if not suggested_reply:
        return jsonify({"error": "Suggested reply content cannot be empty"}), 400
        
    draft.suggested_reply = suggested_reply
    db.session.commit()
    return jsonify({"success": True, "message": "Reply draft saved successfully."})


# ==================== SEO ====================

@main_bp.route("/robots.txt")
def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /dashboard\n"
        "Disallow: /login\n"
        "Disallow: /signup\n"
        "\n"
        "Sitemap: https://autoreach-ai.com/sitemap.xml\n"
    )
    return content, 200, {"Content-Type": "text/plain"}


@main_bp.route("/sitemap.xml")
def sitemap_xml():
    pages = [
        {"url": "https://autoreach-ai.com/", "priority": "1.0"},
        {"url": "https://autoreach-ai.com/privacy", "priority": "0.3"},
        {"url": "https://autoreach-ai.com/terms", "priority": "0.3"},
        {"url": "https://autoreach-ai.com/refund-policy", "priority": "0.3"},
        {"url": "https://autoreach-ai.com/contact", "priority": "0.3"},
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in pages:
        xml += f'  <url><loc>{page["url"]}</loc><priority>{page["priority"]}</priority></url>\n'
    xml += '</urlset>'
    return xml, 200, {"Content-Type": "application/xml"}


# ==================== LEGAL PAGES ====================

@main_bp.route("/privacy")
def privacy_page():
    return render_template("landing.html")

@main_bp.route("/terms")
def terms_page():
    return render_template("landing.html")

@main_bp.route("/refund-policy")
def refund_policy_page():
    return render_template("landing.html")

@main_bp.route("/contact")
def contact_page():
    return render_template("landing.html")


# ==================== RFC 8058 UNSUBSCRIBE ====================

@api_bp.route("/unsubscribe/<token>", methods=["GET"])
def unsubscribe_get(token):
    """Human-facing unsubscribe confirmation page."""
    contact = Contact.query.filter_by(unsubscribe_token=token).first()
    if not contact:
        return "Invalid unsubscribe link.", 404

    # Mask email for privacy: j***@example.com
    email = contact.email
    at_idx = email.index('@')
    masked = email[0] + '***' + email[at_idx:]

    if contact.status != 'unsubscribed':
        contact.status = 'unsubscribed'
        db.session.commit()

    return render_template("landing.html", masked_email=masked)


@api_bp.route("/unsubscribe/<token>", methods=["POST"])
def unsubscribe_post(token):
    """RFC 8058 machine-initiated one-click unsubscribe."""
    contact = Contact.query.filter_by(unsubscribe_token=token).first()
    if not contact:
        return "", 404

    if contact.status != 'unsubscribed':
        contact.status = 'unsubscribed'
        db.session.commit()

    return "", 200


# ==================== DNS HEALTH CHECK ====================

@api_bp.route("/dns-check")
@api_login_required
def api_dns_check():
    """Check SPF, DKIM, DMARC records for a domain."""
    domain = request.args.get("domain", "").strip().lower()
    if not domain:
        return jsonify({"error": "domain parameter required"}), 400

    try:
        from app.services.dns_validator import validate_sender_dns
        result = validate_sender_dns(domain)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

