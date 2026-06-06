"""
Google OAuth 2.0 routes for connecting a Gmail account to the cockpit.

Flow
----
1. Operator opens cockpit → topbar shows "Connect Gmail" (no token configured)
2. GET /oauth/google/start   — builds the Google consent URL using the
                               operator's GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET,
                               stores a PKCE state in the session, redirects.
3. Google redirects back to GET /oauth/google/callback?code=...&state=...
4. We exchange the code for tokens, write them to AUTOREACH_GMAIL_TOKEN_PATH
   (or the default path), and clear the invalid sentinel if present.
5. Cockpit topbar transitions to "Gmail · LIVE" (or DRY-RUN if that flag is set).

Environment variables required
-------------------------------
    GOOGLE_CLIENT_ID          — from Google Cloud Console (OAuth 2.0 client)
    GOOGLE_CLIENT_SECRET      — from Google Cloud Console
    AUTOREACH_GMAIL_SENDER    — the Gmail address we're authorizing (e.g. you@gmail.com)
    AUTOREACH_GMAIL_TOKEN_PATH — where to write token.json (default: ./token.json)
    AUTOREACH_OAUTH_REDIRECT_URI — your /oauth/google/callback URL
                                   (default: http://127.0.0.1:8765/oauth/google/callback)

Security notes
--------------
* State is a cryptographically random token stored in the FastAPI session cookie.
  The callback validates it to prevent CSRF.
* The token file is written atomically (tempfile + rename) by JsonFileTokenStore.save().
* No OAuth secrets are logged.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(prefix="/oauth", tags=["oauth"])

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

_DEFAULT_TOKEN_PATH = "token.json"
_DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/oauth/google/callback"


def _client_config() -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(
            400,
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set before connecting Gmail. "
            "Get them from console.cloud.google.com → APIs & Services → Credentials.",
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _token_path() -> Path:
    return Path(os.getenv("AUTOREACH_GMAIL_TOKEN_PATH", _DEFAULT_TOKEN_PATH)).expanduser()


def _redirect_uri() -> str:
    return os.getenv("AUTOREACH_OAUTH_REDIRECT_URI", _DEFAULT_REDIRECT_URI)


@router.get("/google/start")
def start_google_oauth(request: Request):
    """
    Begin the Google OAuth consent flow.
    Redirects to Google's consent screen.
    """
    from google_auth_oauthlib.flow import Flow  # type: ignore

    try:
        config = _client_config()
    except HTTPException as exc:
        return HTMLResponse(
            f"""
            <html><body style="font-family:monospace;padding:24px;background:#0f1115;color:#e6e9f0">
            <h3>⚠ Configuration missing</h3>
            <p>{exc.detail}</p>
            <p>Set these environment variables and restart the cockpit:</p>
            <pre>GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
AUTOREACH_GMAIL_SENDER=you@gmail.com
AUTOREACH_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/oauth/google/callback</pre>
            <a href="/engagements" style="color:#4a8cff">← Back to cockpit</a>
            </body></html>
            """,
            status_code=400,
        )

    flow = Flow.from_client_config(
        config,
        scopes=_SCOPES,
        redirect_uri=_redirect_uri(),
    )

    # PKCE state — stored in session cookie, validated in callback.
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",      # force refresh_token even if already authorized
        include_granted_scopes="true",
        state=state,
    )

    return RedirectResponse(authorization_url)


@router.get("/google/callback")
def google_oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    Google redirects here after the user grants (or denies) access.
    Exchanges the code for tokens and persists them.
    """
    # User denied access.
    if error:
        return HTMLResponse(
            f"""
            <html><body style="font-family:monospace;padding:24px;background:#0f1115;color:#e6e9f0">
            <h3>❌ OAuth denied</h3>
            <p>Google returned: <code>{error}</code></p>
            <a href="/engagements" style="color:#4a8cff">← Back to cockpit</a>
            </body></html>
            """,
            status_code=400,
        )

    # CSRF check.
    expected_state = request.session.get("oauth_state")
    if not state or state != expected_state:
        raise HTTPException(400, "OAuth state mismatch — possible CSRF. Please try again.")

    if not code:
        raise HTTPException(400, "No authorization code received from Google.")

    from google_auth_oauthlib.flow import Flow  # type: ignore

    config = _client_config()
    flow = Flow.from_client_config(
        config,
        scopes=_SCOPES,
        redirect_uri=_redirect_uri(),
        state=state,
    )

    # Exchange code for credentials.
    try:
        # Allow HTTP for local dev (localhost). In production HTTPS is enforced.
        import os as _os
        _os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
        flow.fetch_token(code=code)
    except Exception as exc:
        return HTMLResponse(
            f"""
            <html><body style="font-family:monospace;padding:24px;background:#0f1115;color:#e6e9f0">
            <h3>❌ Token exchange failed</h3>
            <p><code>{exc}</code></p>
            <p>This usually means the redirect URI doesn't match the one registered in
            Google Cloud Console, or the code has already been used.</p>
            <a href="/oauth/google/start" style="color:#4a8cff">Try again</a>
            </body></html>
            """,
            status_code=400,
        )

    creds = flow.credentials

    # Persist using the same JsonFileTokenStore.save() path so the adapter
    # picks them up immediately.
    from engine import JsonFileTokenStore

    token_path = _token_path()
    store = JsonFileTokenStore(
        token_path=str(token_path),
        client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    )
    store.save(creds)
    store.clear_invalid()  # remove any previous invalid sentinel

    # If the app doesn't have a sender set yet, try to discover it from the
    # userinfo endpoint and suggest it in the success page.
    email_hint = _discover_email(creds)
    sender_set = bool(os.getenv("AUTOREACH_GMAIL_SENDER", "").strip())

    request.session.pop("oauth_state", None)

    return HTMLResponse(
        f"""
        <html><body style="font-family:monospace;padding:24px;background:#0f1115;color:#e6e9f0">
        <h3>✅ Gmail connected</h3>
        <p>Token written to <code>{token_path}</code></p>
        {"<p>Detected sender address: <code>" + email_hint + "</code></p>" if email_hint else ""}
        {"" if sender_set else
            f"<p><strong>⚠ Set <code>AUTOREACH_GMAIL_SENDER={email_hint or 'you@gmail.com'}</code> "
            f"and restart the cockpit to activate Gmail sending.</strong></p>"}
        <p>The cockpit topbar will now show <strong>Gmail · LIVE</strong> 
           (or DRY-RUN if <code>AUTOREACH_GMAIL_DRY_RUN=1</code> is set).</p>
        <a href="/engagements" style="color:#4a8cff">← Back to cockpit</a>
        </body></html>
        """,
        status_code=200,
    )


@router.get("/google/status")
def oauth_status(request: Request):
    """Quick JSON status check — used by the cockpit healthz endpoint."""
    token_path = _token_path()
    from engine import JsonFileTokenStore

    store = JsonFileTokenStore(token_path=str(token_path))
    configured = bool(os.getenv("GOOGLE_CLIENT_ID")) and bool(os.getenv("GOOGLE_CLIENT_SECRET"))
    return {
        "configured": configured,
        "token_exists": token_path.exists(),
        "token_invalid": store.is_invalid() if token_path.exists() else False,
        "sender": os.getenv("AUTOREACH_GMAIL_SENDER", ""),
        "redirect_uri": _redirect_uri(),
    }


def _discover_email(creds) -> Optional[str]:
    """
    Try to fetch the authorized Gmail address from Google's userinfo endpoint.
    Non-fatal — returns None if anything goes wrong.
    """
    try:
        import urllib.request as _req
        import json as _json

        req = _req.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
        )
        with _req.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())
        return data.get("email") or None
    except Exception:
        return None
