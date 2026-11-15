import pytest
import uuid
from playwright.sync_api import Page

@pytest.fixture
def authenticated_page(page: Page):
    # Print console errors/logs
    page.on("console", lambda msg: print(f"CONSOLE ({msg.type}): {msg.text}"))
    
    # Generate a unique test user
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    
    # Go to signup page
    page.goto("http://localhost:8080/signup")
    
    # Fill in signup form
    page.locator("input#email").fill(email)
    page.locator("input#password").fill(password)
    page.locator("button[type='submit']").click()
    
    # Wait for the dashboard redirect
    page.wait_for_url("**/dashboard")
    
    yield page

