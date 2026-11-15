import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from app import create_app
from app.models import db, User, UserProfile, Campaign, CampaignStep, Contact, GoogleAuthToken
from app.worker import CampaignExecutor, classify_reply_with_gemini, personalize_with_gemini

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
        # tables are created by create_app under :memory:
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
def setup_user(app):
    """Sets up a test user, profile, campaigns, and tokens."""
    user = User(email="test_user@example.com")
    user.set_password("password123")
    user.tier = "pro"
    db.session.add(user)
    db.session.commit()

    profile = UserProfile(user_id=user.id, name="Tarandeep", company="AutoReach Inc.", signature="Best,\nTarandeep")
    db.session.add(profile)

    token = GoogleAuthToken(
        user_id=user.id,
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test_client_id",
        client_secret="test_client_secret",
        scopes="https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.readonly"
    )
    db.session.add(token)

    campaign = Campaign(
        id=1,
        user_id=user.id,
        name="Outreach Sequence",
        subject_template="Quick question for {{ company }}",
        text_template="Hi {{ first_name }},\n\nInterested in scaling with AutoReach?\n\n{{ sender_signature }}",
        status="idle",
        personalize_enabled=True,
        gemini_api_key="mock_gemini_key"
    )
    db.session.add(campaign)
    db.session.commit()

    return user, campaign

def test_unauthorized_access(client):
    res = client.get("/api/campaigns/1/steps")
    assert res.status_code == 401
    assert "Unauthorized" in res.get_json()["error"]

def test_campaign_steps_crud(client, setup_user):
    user, campaign = setup_user
    
    with client.session_transaction() as sess:
        sess['user_id'] = user.id

    # 1. Create step 1
    res = client.post(f"/api/campaigns/{campaign.id}/steps", json={
        "subject_template": "Step 1: Introduction",
        "text_template": "Hi {{ first_name }}, this is step 1.",
        "delay_days": 0
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    step1_id = data["step"]["id"]
    assert data["step"]["step_number"] == 1
    assert data["step"]["delay_days"] == 0

    # Create step 2
    res = client.post(f"/api/campaigns/{campaign.id}/steps", json={
        "subject_template": "Step 2: Follow up",
        "text_template": "Hi {{ first_name }}, this is step 2.",
        "delay_days": 3
    })
    assert res.status_code == 200
    data = res.get_json()
    step2_id = data["step"]["id"]
    assert data["step"]["step_number"] == 2
    assert data["step"]["delay_days"] == 3

    # 2. Get steps
    res = client.get(f"/api/campaigns/{campaign.id}/steps")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["steps"]) == 2
    assert data["steps"][0]["id"] == step1_id
    assert data["steps"][1]["id"] == step2_id

    # 3. Update step 2
    res = client.put(f"/api/campaigns/{campaign.id}/steps/{step2_id}", json={
        "delay_days": 5,
        "subject_template": "Updated Step 2 Subject"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["step"]["delay_days"] == 5
    assert data["step"]["subject_template"] == "Updated Step 2 Subject"

    # 4. Delete step 1 and verify reordering
    res = client.delete(f"/api/campaigns/{campaign.id}/steps/{step1_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True

    # Get steps again, check step 2 has become step number 1
    res = client.get(f"/api/campaigns/{campaign.id}/steps")
    data = res.get_json()
    assert len(data["steps"]) == 1
    assert data["steps"][0]["id"] == step2_id
    assert data["steps"][0]["step_number"] == 1

def test_campaign_contacts_and_metrics(client, setup_user):
    user, campaign = setup_user
    
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        
    contact1 = Contact(
        campaign_id=campaign.id,
        email="lead1@example.com",
        first_name="Alice",
        status="pending",
        current_step=1
    )
    contact2 = Contact(
        campaign_id=campaign.id,
        email="lead2@example.com",
        first_name="Bob",
        status="replied",
        current_step=2
    )
    db.session.add_all([contact1, contact2])
    db.session.commit()
    
    res = client.get(f"/api/campaigns/{campaign.id}/contacts")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["contacts"]) == 2
    assert data["metrics"]["pending"] == 1
    assert data["metrics"]["replied"] == 1
    assert data["metrics"]["step_1_pending"] == 1
    assert data["metrics"]["step_2_replied"] == 1

@patch('urllib.request.urlopen')
def test_classify_reply_with_gemini(mock_urlopen):
    # Mocking Gemini response for "auto" classification
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"classification": "auto"}'
                }]
            }
        }]
    }).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    
    classification = classify_reply_with_gemini("Out of Office auto reply", "api_key")
    assert classification == "auto"

    # Mocking Gemini response for "manual" classification
    mock_resp.read.return_value = json.dumps({
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"classification": "manual"}'
                }]
            }
        }]
    }).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    
    classification = classify_reply_with_gemini("Thanks for reaching out, let's call.", "api_key")
    assert classification == "manual"

@patch('urllib.request.urlopen')
def test_personalize_with_gemini(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"subject": "Custom Subj", "body": "Custom Body"}'
                }]
            }
        }]
    }).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    
    subj, body = personalize_with_gemini(
        subject="Generic Subject",
        body="Generic Body",
        row={"first_name": "Alice"},
        api_key="some_key",
        model="gemini-2.0-flash",
        custom_instruction=""
    )
    assert subj == "Custom Subj"
    assert body == "Custom Body"

@patch('app.worker.classify_reply_with_gemini')
def test_check_replies_manual(mock_classify, app, setup_user):
    user, campaign = setup_user
    
    contact = Contact(
        campaign_id=campaign.id,
        email="lead_replied@example.com",
        status="sent",
        last_sent_at=datetime.utcnow() - timedelta(hours=2)
    )
    db.session.add(contact)
    db.session.commit()
    
    mock_gmail = MagicMock()
    mock_gmail.users().messages().list().execute.return_value = {
        'messages': [{'id': 'msg1'}]
    }
    
    mock_gmail.users().messages().get().execute.return_value = {
        'internalDate': str(int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000)),
        'snippet': "Yes, I am interested!"
    }
    
    mock_classify.return_value = "manual"
    
    executor = CampaignExecutor()
    executor._check_replies(campaign.id, "mock_key", gmail_service=mock_gmail)
    
    db.session.refresh(contact)
    assert contact.status == "replied"

@patch('app.worker.classify_reply_with_gemini')
def test_check_replies_out_of_office(mock_classify, app, setup_user):
    user, campaign = setup_user
    
    contact = Contact(
        campaign_id=campaign.id,
        email="lead_ooo@example.com",
        status="sent",
        last_sent_at=datetime.utcnow() - timedelta(hours=2),
        next_send_after=datetime.utcnow()
    )
    db.session.add(contact)
    db.session.commit()
    
    mock_gmail = MagicMock()
    mock_gmail.users().messages().list().execute.return_value = {
        'messages': [{'id': 'msg_ooo'}]
    }
    mock_gmail.users().messages().get().execute.return_value = {
        'internalDate': str(int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000)),
        'snippet': "Out of office till monday."
    }
    
    mock_classify.return_value = "auto"
    
    executor = CampaignExecutor()
    executor._check_replies(campaign.id, "mock_key", gmail_service=mock_gmail)
    
    db.session.refresh(contact)
    assert contact.status == "sent"
    assert contact.next_send_after > datetime.utcnow() + timedelta(days=4)

@patch('app.worker.Credentials')
@patch('app.worker.build')
def test_campaign_loop_progression(mock_build, mock_credentials, app, setup_user):
    user, campaign = setup_user
    
    step1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject_template="Step 1", text_template="Body 1", delay_days=0)
    step2 = CampaignStep(campaign_id=campaign.id, step_number=2, subject_template="Step 2", text_template="Body 2", delay_days=3)
    db.session.add_all([step1, step2])
    
    contact = Contact(
        campaign_id=campaign.id,
        email="progression@example.com",
        first_name="Charlie",
        status="pending",
        current_step=1,
        next_send_after=datetime.utcnow() - timedelta(minutes=1)
    )
    db.session.add(contact)
    db.session.commit()
    
    mock_creds_inst = MagicMock()
    mock_creds_inst.expired = False
    mock_creds_inst.refresh_token = "some_refresh_token"
    mock_credentials.return_value = mock_creds_inst
    
    mock_gmail = MagicMock()
    mock_build.return_value = mock_gmail
    
    import threading
    stop_event = threading.Event()
    
    mock_send = mock_gmail.users().messages().send().execute
    def side_effect_send(*args, **kwargs):
        stop_event.set()
        return {}
    mock_send.side_effect = side_effect_send
    
    executor = CampaignExecutor()
    with patch('app.worker.is_valid_email', return_value=True), \
         patch('app.worker.has_valid_mx_record', return_value=True):
        
        executor._run_campaign_loop(app, campaign.id, stop_event)
        
    db.session.refresh(contact)
    
    assert contact.current_step == 2
    assert contact.status == 'pending'
    assert contact.next_send_after > datetime.utcnow() + timedelta(days=2)
    assert mock_send.call_count == 1

@patch('app.worker.Credentials')
@patch('app.worker.build')
def test_campaign_loop_completion(mock_build, mock_credentials, app, setup_user):
    user, campaign = setup_user
    
    step1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject_template="Step 1", text_template="Body 1", delay_days=0)
    db.session.add(step1)
    
    contact = Contact(
        campaign_id=campaign.id,
        email="completion@example.com",
        first_name="Delta",
        status="pending",
        current_step=1,
        next_send_after=datetime.utcnow() - timedelta(minutes=1)
    )
    db.session.add(contact)
    db.session.commit()
    
    mock_creds_inst = MagicMock()
    mock_creds_inst.expired = False
    mock_creds_inst.refresh_token = "some_refresh_token"
    mock_credentials.return_value = mock_creds_inst
    
    mock_gmail = MagicMock()
    mock_build.return_value = mock_gmail
    
    import threading
    stop_event = threading.Event()
    
    mock_send = mock_gmail.users().messages().send().execute
    def side_effect_send(*args, **kwargs):
        stop_event.set()
        return {}
    mock_send.side_effect = side_effect_send
    
    executor = CampaignExecutor()
    with patch('app.worker.is_valid_email', return_value=True), \
         patch('app.worker.has_valid_mx_record', return_value=True):
         
        executor._run_campaign_loop(app, campaign.id, stop_event)
        
    db.session.refresh(contact)
    
    assert contact.status == 'completed'
    assert mock_send.call_count == 1
