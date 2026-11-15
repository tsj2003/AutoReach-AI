import pytest
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from app import create_app
from app.models import db, User, UserProfile, Campaign, Contact, GoogleAuthToken, ContactReplyDraft
from app.worker import get_next_sending_token, CampaignExecutor

@pytest.fixture
def app():
    import os
    old_db_url = os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    app = create_app()
    app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False
    })
    
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()
        
    if old_db_url is not None:
        os.environ['DATABASE_URL'] = old_db_url
    else:
        os.environ.pop('DATABASE_URL', None)

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def setup_data(app):
    """Sets up a test user, campaign, and multiple mailboxes."""
    user = User(email="saas_user@example.com")
    user.set_password("password123")
    user.tier = "pro"
    db.session.add(user)
    db.session.commit()

    profile = UserProfile(user_id=user.id, name="SaaS User", company="AutoReach AI")
    db.session.add(profile)

    # Token 1 (Least recently used)
    token1 = GoogleAuthToken(
        user_id=user.id,
        email="sender1@gmail.com",
        access_token="token1",
        refresh_token="refresh1",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client_id",
        client_secret="client_secret",
        active=True,
        status="active",
        daily_sent_count=10,
        last_used_at=datetime.utcnow() - timedelta(hours=2)
    )
    # Token 2 (Most recently used)
    token2 = GoogleAuthToken(
        user_id=user.id,
        email="sender2@gmail.com",
        access_token="token2",
        refresh_token="refresh2",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client_id",
        client_secret="client_secret",
        active=True,
        status="active",
        daily_sent_count=5,
        last_used_at=datetime.utcnow() - timedelta(hours=1)
    )
    # Token 3 (Hit safety limit of 50)
    token3 = GoogleAuthToken(
        user_id=user.id,
        email="sender3@gmail.com",
        access_token="token3",
        refresh_token="refresh3",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client_id",
        client_secret="client_secret",
        active=True,
        status="active",
        daily_sent_count=50,
        last_used_at=datetime.utcnow() - timedelta(hours=3)
    )
    # Token 4 (Quarantined)
    token4 = GoogleAuthToken(
        user_id=user.id,
        email="sender4@gmail.com",
        access_token="token4",
        refresh_token="refresh4",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client_id",
        client_secret="client_secret",
        active=False,
        status="reauth_required",
        daily_sent_count=0,
        last_used_at=None
    )
    db.session.add_all([token1, token2, token3, token4])

    campaign = Campaign(
        user_id=user.id,
        name="SaaS Sequence",
        subject_template="Enterprise subject for {{ company }}",
        text_template="Hi {{ first_name }},\n\nSaaS text.",
        status="idle",
        batch_size=10,
        sleep_min=1,
        sleep_max=2
    )
    db.session.add(campaign)
    db.session.commit()

    return user, campaign, [token1, token2, token3, token4]


def test_token_rotation_and_limits(app, setup_data):
    """Test get_next_sending_token rotates properly and respects daily limits."""
    user, campaign, tokens = setup_data

    # get_next_sending_token should pick the active eligible token with the oldest last_used_at
    # Out of token1 (used 2h ago), token2 (used 1h ago), token3 (limit hit), token4 (inactive):
    # It must select token1.
    token = get_next_sending_token(user.id)
    assert token is not None
    assert token.email == "sender1@gmail.com"

    # If token1 is now used, its last_used_at updates
    token.last_used_at = datetime.utcnow()
    db.session.commit()

    # Now token2 (used 1h ago) has the oldest last_used_at among active eligible tokens
    token = get_next_sending_token(user.id)
    assert token is not None
    assert token.email == "sender2@gmail.com"


@patch('app.worker.Credentials')
@patch('app.worker.build')
@patch('app.worker.send_critical_alert')
def test_campaign_auth_error_quarantine(mock_alert, mock_build, mock_credentials, app, setup_data):
    """Test that auth/credential failure quarantines the token and alerts/pauses when pool is empty."""
    user, campaign, tokens = setup_data

    # Connect a pending contact
    contact = Contact(
        campaign_id=campaign.id,
        email="prospect@example.com",
        first_name="John",
        status="pending",
        current_step=1,
        next_send_after=datetime.utcnow() - timedelta(minutes=1)
    )
    db.session.add(contact)
    db.session.commit()

    # Mock Google OAuth to raise an auth/revocation error when building credentials or refreshing
    mock_creds_inst = MagicMock()
    mock_creds_inst.expired = True
    mock_creds_inst.refresh_token = "refresh_token"
    # Cause refresh() to throw an invalid_grant error
    from google.auth.exceptions import RefreshError
    mock_creds_inst.refresh.side_effect = RefreshError("invalid_grant: Token has been expired or revoked.")
    mock_credentials.return_value = mock_creds_inst

    # We will deactivate Token 2 and Token 3 so Token 1 is the only available token, causing a campaign pause when it fails.
    tokens[1].active = False
    tokens[1].status = "reauth_required"
    tokens[2].active = False
    tokens[2].status = "reauth_required"
    db.session.commit()

    import threading
    stop_event = threading.Event()
    executor = CampaignExecutor()

    with patch('app.worker.is_valid_email', return_value=True), \
         patch('app.worker.has_valid_mx_record', return_value=True):
        
        executor._run_campaign_loop(app, campaign.id, stop_event)

    # Token 1 should be quarantined: active=False, status='reauth_required'
    db.session.refresh(tokens[0])
    assert tokens[0].active is False
    assert tokens[0].status == 'reauth_required'

    # Contact status should be reset to 'pending' to retry with rotated mailbox later
    db.session.refresh(contact)
    assert contact.status == 'pending'

    # Campaign status should be paused_no_active_inbox
    db.session.refresh(campaign)
    assert campaign.status == 'paused_no_active_inbox'

    # Critical alert should be sent to the user's email
    mock_alert.assert_called_once()
    assert mock_alert.call_args[0][0] == "saas_user@example.com"
    assert "No active connected mailboxes" in mock_alert.call_args[0][2] or "failed auth" in mock_alert.call_args[0][2]


@patch('app.services.notifications.smtplib.SMTP')
def test_critical_alert_fallback(mock_smtp, app, capsys):
    """Test that send_critical_alert falls back to writing to sys.stderr if SMTP is unconfigured or fails."""
    from app.services.notifications import send_critical_alert

    # Unconfigured SMTP
    with patch.dict('os.environ', {}, clear=True):
        result = send_critical_alert("user@example.com", "My Campaign", "Auth failed")
        assert result is False
        
        captured = capsys.readouterr()
        assert "SYSTEM CRITICAL ALERT FALLBACK" in captured.err
        assert "To: user@example.com" in captured.err
        assert "My Campaign" in captured.err

    # Configured SMTP but fails on connection
    mock_smtp.side_effect = Exception("SMTP connection refused")
    with patch.dict('os.environ', {
        "SYSTEM_SMTP_HOST": "smtp.gmail.com",
        "SYSTEM_SMTP_PORT": "587",
        "SYSTEM_SMTP_USER": "test@gmail.com",
        "SYSTEM_SMTP_PASSWORD": "password"
    }):
        result = send_critical_alert("user@example.com", "My Campaign", "Auth failed")
        assert result is False
        
        captured = capsys.readouterr()
        # Should fallback to writing raw content to sys.stderr on exception
        assert "SYSTEM CRITICAL ALERT (SMTP SEND FAILED)" in captured.err
        assert "SMTP connection refused" in captured.err


def test_api_endpoints_user_id_and_draft_save(client, setup_data):
    """Test status/config endpoints return user_id, and reply-drafts/save saves edits."""
    user, campaign, tokens = setup_data

    # Log in test client
    with client.session_transaction() as sess:
        sess['user_id'] = user.id

    # Test status endpoint returns user_id
    res = client.get(f"/api/status?campaign_id={campaign.id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["user_id"] == user.id
    assert data["campaign_id"] == campaign.id

    # Test config endpoint returns user_id and token status
    res = client.get(f"/api/config?campaign_id={campaign.id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["user_id"] == user.id
    # Token 4 should have status 'reauth_required'
    t4 = next(t for t in data["tokens"] if t["email"] == "sender4@gmail.com")
    assert t4["status"] == "reauth_required"

    # Setup contact and a reply draft
    contact = Contact(
        campaign_id=campaign.id,
        email="replier@example.com",
        status="replied"
    )
    db.session.add(contact)
    db.session.commit()

    draft = ContactReplyDraft(
        contact_id=contact.id,
        reply_snippet="I'm too busy.",
        classification="objection",
        suggested_reply="Original AI suggested reply.",
        status="pending"
    )
    db.session.add(draft)
    db.session.commit()

    # Save edit via endpoint
    res = client.post(f"/api/reply-drafts/{draft.id}/save", json={
        "suggested_reply": "User modified response text."
    })
    assert res.status_code == 200
    assert res.get_json()["success"] is True

    # Verify database was updated
    db.session.refresh(draft)
    assert draft.suggested_reply == "User modified response text."

    # Verify authentication (non-existent user attempts to save)
    with client.session_transaction() as sess:
        sess['user_id'] = 999
    res = client.post(f"/api/reply-drafts/{draft.id}/save", json={
        "suggested_reply": "Hack attempt."
    })
    assert res.status_code == 401

    # Verify authorization (different valid user attempts to save)
    user2 = User(email="other_user@example.com")
    user2.set_password("password123")
    db.session.add(user2)
    db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = user2.id
    res = client.post(f"/api/reply-drafts/{draft.id}/save", json={
        "suggested_reply": "Hack attempt."
    })
    assert res.status_code == 403
