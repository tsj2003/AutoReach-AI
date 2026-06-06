# AutoReach-AI: Complete Application Context

## 1. Overview
**AutoReach-AI** is a custom cold-emailing and campaign management automation tool built to streamline job application outreach (specifically targeting SDE/Software Engineering HRs and recruiters). It manages email templating, batch sending, rate limiting, attachments, and campaign state tracking visually through a modern web UI.

## 2. Technical Stack
- **Backend:** Python 3, Flask (Web Server backend)
- **Frontend:** HTML5, Tailwind CSS (via CDN, using inline styling for SaaS-like Dark Mode/Glassmorphism UI inspired by "Wispr Flow"), Alpine.js (Lightweight reactive state management)
- **Templating:** Jinja2 (Used strictly for email parsing with explicit `{% raw %}` tags in web routes to separate from Alpine.js)
- **Authentication:** Google OAuth 2.0 (Gmail API) using `credentials.json` and `token.json`.
- **Testing:** Pytest & Playwright (End-to-End Headless UI testing)

## 3. Core Architecture & Files

### Engine / Core Logic
- **`bulk_mail_with_attachment.py`**: The main powerhouse script that handles Gmail API authentication, reads the target CSV, renders the personalized Jinja emails (both HTML and Plain Text), tracks send success, applies delays (rate limiting), and appends the resume attachment.
- **`campaign_manager.py` / `campaign_status.py`**: Reads `.yaml` campaign configurations (like `campaigns/sde_outreach.yaml`) to structure outreach rules, API limits, and target bases.
- **`utils.py`**: Helper functions for text processing, email extraction, etc.
- **`run.py`**: The CLI entry point that spawns both the Web Dashboard (`python3 run.py web`) and background polling/worker processes.

### Web Server (Flask)
- **`app/routes.py`**: Handles all the API backends for the web interface. Routes include:
  - `/api/status`: Fetches live data from `.campaign_state.json`.
  - `/api/campaign/start` & `/api/campaign/pause`: Modifies campaign state triggers.
  - `/upload-contacts`: Handles CSV/txt ingestion for the queue.
  - `/save-template`: Modifies the `.j2` email templates securely.
- **`app/templates/dashboard.html`**: The unified single-page application heavily stylized with Tailwind & Alpine. Contains tabs for Dashboard overview, Contact Lead ingestion, Templates configuration, and Auth settings.

### Data Storage & State
- **`.campaign_state.json`**: Acts as a lightweight, live database. It tracks:
  - `status` (running/paused/idle/completed)
  - `sent`, `failed`, `total` counts
  - `resume_point`: Exact index of the CSV to continue from, preventing duplicate emails.
- **`out/hr_reachout_list.csv`**: The active queue of emails to process. Currently holds 29 highly-curated VIP targets. 
- **`campaigns/`**: Houses the `.yaml` config configurations (e.g., `sde_outreach.yaml`).

### Email Templates
Located in `templates/`:
- **`tsj_outreach.txt.j2`** / **`tsj_outreach.html.j2`**: The active templates. They use Jinja parameter injection (e.g., `{{ name }}`, `{{ company }}`) to map CSV columns into the email body dynamically.

### Testing
Located in `tests/`:
- **`test_dashboard.py`** & **`test_features.py`**: Playwright testing suites verifying UI rendering, navigation, file uploads, and template saving logic. Run via `pytest`.

## 4. Workflows

**1. Data Ingestion:**
The user parses raw lists (e.g., scraped PDFs) into a CSV formatted with an `email` header (currently `out/hr_reachout_list.csv`). 

**2. Campaign Start:**
The user hits "Start Engine" from the UI. `app/routes.py` triggers a background thread invoking `bulk_mail_with_attachment.py`.

**3. Execution & Tracking:**
The engine targets the first available row in `.campaign_state.json`'s `resume_point`. It renders the Jinja template, attaches the specified PDF (`Tarandeep_Resume_SDE.pdf`), and sends it via Gmail API. It then increments the `resume_point`, updates the state, logs the success, and sleeps to avoid Google API rate limits.

**4. Visual Updates:**
The frontend uses Alpine.js to poll `/api/status` every 2 seconds, reactively updating the progressive bar, success rates, and active states on the user's screen without a browser refresh.

## 5. Recent Overhauls
- **UI Modernization:** Complete refit of the frontend to a "Wispr Flow" inspired glassmorphic aesthetic.
- **Template Safety:** Solved backend rendering faults by wrapping Alpine.js `x-data` inputs inside `{% raw %}` tags so Flask doesn't try to parse JS variables as Python template variables.
- **E2E Playwright Integration:** Added a headless Chromium browser testing infrastructure.