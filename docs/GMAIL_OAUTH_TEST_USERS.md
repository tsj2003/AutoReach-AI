# Gmail OAuth testers (connect today)

Google is blocking Gmail connect on Attainly live because the OAuth app is
**External + Testing**. Only Google accounts listed as **Test users** can
consent. This is not a bug in Attainly, and you do **not** need to publish or
verify the app to connect testers today.

**Observed error:** `Access blocked: azurecontainerapps.io has not completed the Google verification process` / `403: access_denied`.

**Live app:** https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io

**OAuth client ID (web):** `563902063253-nu42osiloetfam53jlm7tuv2taq3esvg.apps.googleusercontent.com`

Use this client ID in the project picker so you edit the same Google Cloud
project the live app uses.

## 1. Add Test users (do this first)

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Top bar **project picker** → select the project that owns the client ID above (project number `563902063253`).
3. Open the consent / audience screen using whichever nav your console shows:
   - **APIs & Services → OAuth consent screen**, or
   - **Google Auth platform → Audience**
4. Confirm **User type** = **External** and **Publishing status** = **Testing**.
5. **Test users → + Add users** → add:
   - `junnejatarandeepsingh@gmail.com`
   - `tarandeepjuneja11@gmail.com` (if that account is also used to connect)
6. **Save**. Wait 1–5 minutes.

Do **not** click **Publish app** to unblock testers. Publishing + Google
verification for Gmail scopes is a later production step.

## 2. Confirm Authorized redirect URIs

1. **APIs & Services → Credentials**, or **Google Auth platform → Clients**.
2. Open the **Web application** OAuth 2.0 Client ID that matches the client ID above.
3. **Authorized redirect URIs** must include (add any missing, then **Save**):

```text
https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/api/mailboxes/connect/callback
https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/api/calendar/connect/callback
http://127.0.0.1:8765/api/mailboxes/connect/callback
http://127.0.0.1:8765/api/calendar/connect/callback
http://127.0.0.1:8765/oauth/google/callback
```

The live Mailboxes **Connect Gmail** button starts
`POST /api/mailboxes/connect/start` with

`redirect_uri = https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/api/mailboxes/connect/callback`.

Optional: **Authorized JavaScript origins** may include

`https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io`

## 3. Retry Connect Gmail

1. Sign in to Attainly live as the operator.
2. **Operations → Mailboxes → Connect Gmail** (or Integrations → Gmail).
3. Sign in to Google as **exactly** the Test user email you added.
4. Testing apps show **Google hasn't verified this app**. That warning is
   expected. Click **Advanced → Go to … (unsafe)** and Allow.
5. A leftover **403 access_denied** means that Google account is still not on
   the Test users list (wrong project, typo, or not saved yet). Recheck step 1.

## Workaround

There is **no SMTP / Gmail App Password fallback** in the Mailboxes or
Integrations UI. BYOC (`client_id` / `client_secret` on
`POST /api/mailboxes/connect/start`) exists in the API only; the live UI does
not expose it. Adding Test users is the way to connect Gmail today.

## Later (not required today)

When you want any Google user (not just testers) to connect, publish the
consent screen and complete Google's verification for Gmail/sensitive scopes.
That review can take days to weeks. Keep the app in Testing until then.
