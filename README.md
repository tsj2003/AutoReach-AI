## Bulk Gmail Sender (CSV + Jinja)

This folder contains a ready-to-run Python script to send personalized emails through the Gmail API using data from a CSV and Jinja2 templates. An optional Google Apps Script is also provided to send from a Google Sheet.

### Prerequisites
- Python 3.9+
- A Google Cloud project with Gmail API enabled
- OAuth 2.0 Client ID (Desktop) JSON downloaded as `credentials.json`

### Install
```bash
cd /Users/tarandeepsinghjuneja/email
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Files
- `bulk_mail.py`: CLI to send emails from CSV using Gmail API
- `recipients.sample.csv`: Example CSV with columns: `email,name,action_url,subject,cc,bcc`
- `templates/email.html.j2`: HTML Jinja template
- `templates/email.txt.j2`: Text Jinja template
- `requirements.txt`: Dependencies

### Prepare OAuth
1. Go to Google Cloud Console → APIs & Services → Credentials.
2. Create OAuth client ID (Desktop) and download JSON to `credentials.json` in this folder.
3. First run opens a browser to authorize; a `token.json` is stored for future runs.

### CSV Format
- Required: `email`
- Optional: `name`, `action_url`, `subject`, `cc`, `bcc` (and any additional fields referenced by your templates)

### Dry run (no sending)
```bash
python bulk_mail.py \
  --csv recipients.sample.csv \
  --subject "Welcome, {{ name }}!" \
  --html-template templates/email.html.j2 \
  --text-template templates/email.txt.j2 \
  --dry-run --verbose
```

### Send emails
```bash
python bulk_mail.py \
  --csv recipients.sample.csv \
  --subject "Welcome, {{ name }}!" \
  --html-template templates/email.html.j2 \
  --text-template templates/email.txt.j2 \
  --from you@example.com \
  --sleep 0.4
```
Notes:
- `--from` must be your Gmail or a verified alias in your account.
- You can omit `--subject` if your CSV includes a `subject` column.
- Use `--limit` to test on the first N rows.

### Gmail sending limits
Respect Gmail sending limits; add delay via `--sleep`. If you hit errors, increase the delay.

### Optional: Google Apps Script (Sheets → Gmail)
If you prefer Sheets instead of Python, create a Google Sheet with headers like `email,name,subject,action_url` and add an Apps Script with the following code.

```javascript
function sendBulkEmails() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const rows = sheet.getDataRange().getValues();
  const headers = rows.shift();

  const colIndex = (name) => headers.indexOf(name);
  const idxEmail = colIndex('email');
  const idxName = colIndex('name');
  const idxSubject = colIndex('subject');
  const idxAction = colIndex('action_url');

  if (idxEmail < 0 || idxSubject < 0) {
    throw new Error('Headers must include email and subject');
  }

  rows.forEach(r => {
    const to = r[idxEmail];
    const name = idxName >= 0 ? r[idxName] : '';
    const subject = r[idxSubject];
    const actionUrl = idxAction >= 0 ? r[idxAction] : '';

    const htmlBody = `Hi ${name || 'there'},<br><br>` +
      `This is a sample personalized email.` +
      (actionUrl ? `<br><br><a href="${actionUrl}">View details</a>` : '') +
      `<br><br>Thanks,<br>Your Team`;

    GmailApp.sendEmail(to, subject, '', { htmlBody });
  });
}
```

Grant permissions when prompted. Consider quotas in Apps Script too.

$ source /Users/tarandeepsinghjuneja/email/.venv/bin/activate && python /Users/tarandeepsinghjuneja/email/send_job_applications.py --csv /Users/tarandeepsinghjuneja/email/hr_contacts_safe.csv --from junejatarandeepsingh@gmail.com --batch-size 50 --delay-min 60 --delay-max 120 --email-sleep-min 100 --email-sleep-max 180 | cat