from playwright.sync_api import Page, expect

def test_upload_contacts(authenticated_page: Page, tmp_path):
    page = authenticated_page
    
    # Wait for Alpine init() to finish loading campaigns
    page.wait_for_timeout(2000)
    
    # Go to contacts tab
    page.locator("aside button", has_text="contacts").click()
    expect(page.locator("h3", has_text="Lead List Ingestion")).to_be_visible()
    
    # Create a dummy csv file with a proper header
    d = tmp_path / "sub"
    d.mkdir()
    p = d / "test.csv"
    p.write_text("email,first_name\ntest1@example.com,John\ntest2@example.com,Jane\ntest1@example.com,John")
    
    # Upload via input and wait for the async API response
    with page.expect_response("**/api/upload-contacts", timeout=15000) as response_info:
        page.locator("input#fileUpload").set_input_files(p)
    
    response = response_info.value
    assert response.status == 200
    
    # Verify the results in UI
    ready_locator = page.locator("span", has_text="Imported Successfully").locator("xpath=following-sibling::span")
    expect(ready_locator).to_have_text("2", timeout=5000)
    
def test_save_template(authenticated_page: Page):
    page = authenticated_page
    
    # Wait for Alpine init() to finish loading campaigns
    page.wait_for_timeout(2000)
    
    # Go to templates tab
    page.locator("aside button", has_text="templates").click()
    expect(page.locator("h3", has_text="Content Studio")).to_be_visible()
    
    # Add a step and wait for the async API response
    with page.expect_response("**/api/campaigns/*/steps", timeout=10000) as response_info:
        page.locator("button", has_text="Add Step").click()
    
    response = response_info.value
    assert response.status == 200
    
    # Wait for loadSteps() to complete and render the editor
    subject_input = page.locator("input[x-model='selectedStep.subject_template']")
    expect(subject_input).to_be_visible(timeout=10000)
    
    # Type into inputs
    subject_input.fill("Test Subject")
    page.locator("textarea[x-model='selectedStep.text_template']").fill("Hello {{ name }},\n\nTesting playwright.")
    
    # Save Campaign Templates
    page.locator("button", has_text="Save Step Templates").click()
    
    # Should see success toast
    expect(page.locator(".fixed.bottom-6.right-6", has_text="Step templates saved successfully")).to_be_visible(timeout=5000)
