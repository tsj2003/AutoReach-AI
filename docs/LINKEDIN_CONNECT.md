# LinkedIn connect (Gojiberry-style Voyager seat)

Attainly’s LinkedIn outreach matches Gojiberry’s model: a **LinkedIn seat** (session cookies) powers visit / like / comment / connection request / DM. Official “Sign In with LinkedIn” OAuth cannot send those actions on LinkedIn’s self-serve API, so the working path is the Voyager seat.

## Connect a seat

1. Open **Operations → LinkedIn**.
2. Prefer **Chrome extension**:
   - Download `/api/linkedin/chrome-extension.zip`
   - Chrome → `chrome://extensions` → Developer mode → Load unpacked → `attainly-linkedin-helper`
   - Generate a pairing token in Attainly
   - Stay signed into LinkedIn → Connect in the popup
3. Or **Cookie paste**: DevTools → Application → Cookies → `li_at` + `JSESSIONID`.

Cookies are Fernet-encrypted on `linkedin_seats`.

## Campaign sequence

When a seat is connected and the campaign sequence includes LinkedIn steps, the planner creates `linkedin.action` jobs. Approve them like email. Without a seat, LinkedIn steps collapse to email (`skipInvitationAfterDays` / no-seat fallback).

Supported step kinds (from campaign sequence / UI):

| UI / kind | Voyager action |
|-----------|----------------|
| `VISIT_PROFILE` | visitProfile |
| `LIKE_POSTS` | likePosts |
| `COMMENT_ON_POST` | commentOnPost |
| `LINKEDIN_CONNECT` / `CONNECTION_NOTE` | invitation / invitationNote |
| `LINKEDIN_MESSAGE` | message (optional multi-bubble) |
| `EMAIL` | Gmail mailbox send |

Prospects need a `linkedin_url` on the contact for LinkedIn steps; email steps need an email.

## Risk note

Voyager automation can trigger LinkedIn restrictions if you over-send. Keep daily limits conservative and use HITL approval.
