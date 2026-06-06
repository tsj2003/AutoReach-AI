import re
from playwright.sync_api import Page, expect

def test_dashboard_loads(authenticated_page: Page):
    page = authenticated_page
    
    # Check title
    expect(page).to_have_title(re.compile("AutoReach - Cold Outreach Cockpit"))
    
    # Find the campaign progress card on the dashboard page
    expect(page.locator("h3", has_text="Campaign Delivery Progress")).to_be_visible()
    
    # Verify the cards are rendered
    expect(page.get_by_text("Total Leads")).to_be_visible()

def test_navigation_tabs(authenticated_page: Page):
    page = authenticated_page
    
    # Click Contacts tab
    page.locator("aside button", has_text="contacts").click()
    expect(page.locator("h3", has_text="Lead List Ingestion")).to_be_visible()
    
    # Click Templates tab 
    page.locator("aside button", has_text="templates").click()
    expect(page.locator("h3", has_text="Content Studio")).to_be_visible()

    # Click Auth tab 
    page.locator("aside button", has_text="auth").click()
    expect(page.locator("h3", has_text="APIs & Integrations Configuration")).to_be_visible()