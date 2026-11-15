# Attainly LinkedIn Connector (Chrome)

Hassle-free LinkedIn pairing. No password is typed into Attainly.

1. In Attainly go to **Integrations → LinkedIn → Chrome extension**.
2. Download `attainly-linkedin-helper.zip` and unzip it.
3. Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → select this folder.
4. Generate a pairing token in Attainly and paste it into the extension popup.
5. Stay signed into LinkedIn in the same Chrome profile, then click **Connect**.

The extension only reads `li_at` and `JSESSIONID` cookies and posts them to
`POST /api/linkedin/connect-by-token`. Attainly encrypts them with Fernet.

Cookie-paste remains available on the **Cookie paste** tab if you cannot install the extension.
