# 🚀 SDE Outreach Campaign - Ready to Launch

## Campaign Details
- **Target**: 2,332 HR emails
- **Subject**: Final Year @ VIT | IIT Bombay Intern | Meta Hacker Cup Rank 186
- **Personalization**: Dynamic greeting with HR name extracted from email
- **Templates**: Professional HTML + Plain text
- **Attachment**: Resume (required before sending)

---

## ⚡ Quick Start

### Step 1: Prepare Resume
Place your resume file in the project root:
```bash
cp ~/your-resume.pdf ./CV_backend_Tarandeep_Singh_Juneja.pdf
```

### Step 2: Set Gmail Settings
Make sure you have:
- `credentials.json` (OAuth client ID from Google Cloud)
- `token.json` (will be generated on first run)

### Step 3: Launch Campaign

**Start sending:**
```bash
./q s hr_emails.csv tarandeepsinghjuneja@gmail.com
```

Or with custom batch size (emails per day):
```bash
./q s hr_emails.csv tarandeepsinghjuneja@gmail.com 500
```

---

## 📊 Monitor Campaign

**Check status anytime:**
```bash
./q t
```

**View recent logs:**
```bash
./q l          # Last 20 lines
./q l 50       # Last 50 lines
```

**Live log stream:**
```bash
watch -n 5 "./q l 15"
```

---

## ⏹ Control Campaign

**Pause campaign:**
```bash
./q x
```

**Resume after pause:**
```bash
./q r hr_emails.csv tarandeepsinghjuneja@gmail.com
```
- Auto-detects rate limit window
- Waits for quota reset
- Auto-resumes when ready

---

## 📝 Email Template Reference

### Subject (Dynamic):
```
Final Year @ VIT | IIT Bombay Intern | Meta Hacker Cup Rank 186
```

### Body Personalization:
```
Hi {{ hr_name }},    ← Auto-extracted from email prefix
...
Thanks for your time, {{ hr_name }}!
```

### Name Extraction Examples:
- `akanksha.puri@sourcefuse.com` → `Akanksha`
- `akhil@ibhubs.co` → `Akhil`
- `albino@pixis.ai` → `Albino`

### Email Content:
✓ Meta Hacker Cup Rank 186 mention  
✓ IIT Bombay FOSSEE internship  
✓ Project highlights (MailMantra, DocuGenAI, BillBuddy)  
✓ Tech stack showcase  
✓ Portfolio, GitHub, LinkedIn links  
✓ Resume attachment  
✓ Professional tone with personal touch  

---

## 📈 Campaign Metrics

### Expected Timeline
- **Total emails**: 2,332
- **Daily batch**: 450 (Gmail limit)
- **Days needed**: ~6 days (with safety delays)
- **Delay between emails**: 90-150 seconds (random)

### Tracking
- `hr_emails.csv` - Input list
- `sent_emails.txt` - Track sent emails (prevents duplicates)
- `.campaign_state.json` - Campaign progress & state
- `campaign.log` - Detailed one-line logs

---

## 🛡️ Safety Features

✅ **Duplicate Prevention**
- Emails already sent are skipped
- Uses `sent_emails.txt` for tracking

✅ **Rate Limit Protection**
- Respects Gmail API limits
- Auto-stops on quota exceeded
- Auto-resumes after 24h when quota resets

✅ **Error Handling**
- Logs all failures
- Continues on non-critical errors
- Saves state on every send

✅ **Resume Point**
- Tracks progress in `.campaign_state.json`
- Resume from exact stopping point
- No duplicate sends

---

## 🔧 Advanced Options

### Dry Run (Preview without sending):
```bash
python bulk_mail_with_attachment.py \
  --csv hr_emails.csv \
  --subject "Final Year @ VIT | IIT Bombay Intern | Meta Hacker Cup Rank 186" \
  --html-template templates/tsj_outreach.html.j2 \
  --text-template templates/tsj_outreach.txt.j2 \
  --from tarandeepsinghjuneja@gmail.com \
  --attachment CV_backend_Tarandeep_Singh_Juneja.pdf \
  --dry-run \
  --limit 5
```

### Skip First N Emails (resume from middle):
```bash
./q s hr_emails.csv tarandeepsinghjuneja@gmail.com 450
# Internally uses --skip to resume from saved point
```

---

## 📞 Support

If emails fail:
1. Check `.campaign_state.json` for error details
2. View `campaign.log` for detailed logs
3. Use `./q l 50` to see recent activity
4. Verify resume attachment exists

---

**Ready? Launch with:** `./q s hr_emails.csv tarandeepsinghjuneja@gmail.com`
