from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    tier = db.Column(db.String(20), default='free') # 'free', 'basic', 'pro'
    razorpay_customer_id = db.Column(db.String(120), nullable=True)
    razorpay_subscription_id = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    profile = db.relationship('UserProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    tokens = db.relationship('GoogleAuthToken', backref='user', lazy=True, cascade="all, delete-orphan")
    campaigns = db.relationship('Campaign', backref='user', lazy=True, cascade="all, delete-orphan")

    @property
    def token(self):
        return self.tokens[0] if self.tokens else None

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class UserProfile(db.Model):
    __tablename__ = 'user_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    title = db.Column(db.String(100), nullable=True)
    company = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    website = db.Column(db.String(200), nullable=True)
    linkedin = db.Column(db.String(200), nullable=True)
    github = db.Column(db.String(200), nullable=True)
    links = db.Column(db.Text, nullable=True) # Line-separated extra links
    signature = db.Column(db.Text, nullable=True)

class GoogleAuthToken(db.Model):
    __tablename__ = 'google_auth_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    daily_sent_count = db.Column(db.Integer, default=0)
    last_used_at = db.Column(db.DateTime, nullable=True)
    active = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(30), default='active') # 'active', 'reauth_required'
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    token_uri = db.Column(db.String(256), nullable=False)
    client_id = db.Column(db.String(256), nullable=False)
    client_secret = db.Column(db.String(256), nullable=False)
    scopes = db.Column(db.Text, nullable=True) # comma separated
    expiry = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_uri": self.token_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scopes": self.scopes.split(',') if self.scopes else []
        }

class Campaign(db.Model):
    __tablename__ = 'campaigns'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    subject_template = db.Column(db.String(200), nullable=True)
    text_template = db.Column(db.Text, nullable=True)
    html_template = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='idle') # 'idle', 'running', 'paused', 'completed', 'batch_complete'
    resume_point = db.Column(db.Integer, default=0)
    batch_size = db.Column(db.Integer, default=100)
    sleep_min = db.Column(db.Integer, default=180)
    sleep_max = db.Column(db.Integer, default=240)
    personalize_enabled = db.Column(db.Boolean, default=False)
    personalization_model = db.Column(db.String(50), default='gemini-2.0-flash')
    personalization_prompt = db.Column(db.Text, nullable=True)
    gemini_api_key = db.Column(db.String(256), nullable=True)
    attachment_path = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    contacts = db.relationship('Contact', backref='campaign', lazy=True, cascade="all, delete-orphan")
    logs = db.relationship('CampaignLog', backref='campaign', lazy=True, cascade="all, delete-orphan")
    steps = db.relationship('CampaignStep', backref='campaign', lazy=True, cascade="all, delete-orphan", order_by="CampaignStep.step_number")

class CampaignStep(db.Model):
    __tablename__ = 'campaign_steps'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    step_number = db.Column(db.Integer, default=1)
    subject_template = db.Column(db.String(200), nullable=True)
    text_template = db.Column(db.Text, nullable=True)
    html_template = db.Column(db.Text, nullable=True)
    delay_days = db.Column(db.Integer, default=3) # Delay after previous step

class Contact(db.Model):
    __tablename__ = 'contacts'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    company = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='pending') # 'pending', 'sent', 'failed', 'replied', 'completed', 'unsubscribed'
    error_reason = db.Column(db.String(256), nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    sender_email = db.Column(db.String(120), nullable=True)
    raw_data_json = db.Column(db.Text, nullable=True) # Full CSV row parameters stored as JSON
    current_step = db.Column(db.Integer, default=1)
    last_sent_at = db.Column(db.DateTime, nullable=True)
    next_send_after = db.Column(db.DateTime, default=datetime.utcnow)
    unsubscribe_token = db.Column(db.String(64), unique=True, nullable=True)


    def get_raw_data(self):
        if self.raw_data_json:
            try:
                return json.loads(self.raw_data_json)
            except Exception:
                pass
        return {}

    def set_raw_data(self, data):
        self.raw_data_json = json.dumps(data)

class CampaignLog(db.Model):
    __tablename__ = 'campaign_logs'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    type = db.Column(db.String(20), default='info') # 'info', 'success', 'warning', 'error'
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ContactReplyDraft(db.Model):
    __tablename__ = 'contact_reply_drafts'
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id'), unique=True, nullable=False)
    reply_snippet = db.Column(db.Text, nullable=True)
    classification = db.Column(db.String(50), nullable=True) # 'interested', 'objection', 'unsubscribe', etc.
    suggested_reply = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending') # 'pending', 'sent', 'discarded'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    contact = db.relationship('Contact', backref=db.backref('reply_draft', uselist=False, cascade="all, delete-orphan"))
