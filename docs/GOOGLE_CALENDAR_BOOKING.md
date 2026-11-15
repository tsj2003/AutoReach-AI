# Native Google Calendar meeting booking (Attainly)

Attainly can create real Google Calendar events (with Google Meet when available)
and email invites to interested prospects — Gojiberry-style native booking, not
only a Calendly / Cal.com link.

## Connect Calendar

1. Ensure `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` are set (same OAuth client as Gmail).
2. In [Google Cloud Console](https://console.cloud.google.com/):
   - Enable **Google Calendar API**
   - OAuth consent screen includes:
     - `https://www.googleapis.com/auth/calendar.events`
     - `https://www.googleapis.com/auth/calendar.freebusy` (optional but used for slot picking)
   - Authorized redirect URIs include:
     - `https://YOUR_DOMAIN/api/mailboxes/connect/callback`
     - `https://YOUR_DOMAIN/api/calendar/connect/callback`
     - Production Azure app:
       - `https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/api/mailboxes/connect/callback`
       - `https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/api/calendar/connect/callback`
3. In the app: **Integrations → Connect Google Calendar** (or Unibox CTA).
   - This re-consents the Gmail mailbox with expanded Calendar scopes.
   - Tokens stay on the mailbox row (`credentials_json`), encrypted like Gmail.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/calendar/status` | `connected`, `email`, `scopes`, `needs_reconsent` |
| POST | `/api/calendar/connect/start` | Returns Google OAuth `authorization_url` |
| GET | `/api/calendar/connect/callback` | Saves tokens onto mailbox |
| GET | `/api/calendar/freebusy` | Next open 30‑min slots (working hours) |
| POST | `/api/calendar/book` | Create event + Meet + `sendUpdates=all` |
| POST | `/api/inbox/{reply_id}/book-meeting` | Book from Unibox interested reply |

### Book body (`POST /api/calendar/book`)

```json
{
  "prospect_email": "pat@example.com",
  "prospect_name": "Pat",
  "start_iso": "2026-06-03T16:00:00+00:00",
  "end_iso": "2026-06-03T16:30:00+00:00",
  "title": "Attainly intro",
  "description": "Optional",
  "timezone": "America/New_York",
  "campaign_id": "optional",
  "prospect_id": "optional",
  "reply_id": "optional"
}
```

## Unibox flow

1. Reply classified **interested** / meeting-intent.
2. Operator clicks **Book on Google Calendar** (or Connect CTA if scopes missing).
3. Backend picks next free slot (or uses `start_iso`), creates Calendar event with Meet,
   emails the invite, marks prospect `booked`, and stores on `prospect.raw`:
   - `meeting_booked_at`
   - `gcal_event_id`
   - `meet_link`
   - `gcal_html_link`
4. Suggested reply is updated to a booking confirmation the operator can send.

AI drafts for meeting-intent replies include proposed freebusy slots when Calendar
is connected; otherwise they fall back to the campaign `booking_url`.

## Deploy note

Ship this in the next container image build. If an ACR push is mid-flight for the
logo / $89 agent work, finish code + tests here and include Calendar in the next
image — do not race a parallel ACR deploy.

Local verification:

```bash
pytest tests/test_google_calendar.py -q
```
