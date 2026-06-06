# ⚡ Command Cheatsheet

## One-Time Setup
```bash
# Copy your resume
cp ~/Downloads/your-resume.pdf ./CV_backend_Tarandeep_Singh_Juneja.pdf

# Setup OAuth (first time only)
# - Download credentials.json from Google Cloud Console
# - Place in project root
```

## Campaign Commands

### LAUNCH
```bash
./q s hr_emails.csv tarandeepsinghjuneja@gmail.com
# Sends to 2,332 HR emails
# Daily limit: 450 emails
# Expected duration: ~6 days
```

### STATUS & LOGS
```bash
./q t          # Show status (sent, failed, remaining)
./q l          # Show last 20 logs
./q l 50       # Show last 50 logs
watch -n 5 "./q l 15"  # Live stream logs
```

### CONTROL
```bash
./q x          # Stop campaign
./q r hr_emails.csv tarandeepsinghjuneja@gmail.com  # Resume
./q c          # Clear old logs
```

## What Gets Personalized

### Email Greeting
```
Hi {{ hr_name }},

Examples:
- akanksha.puri@sourcefuse.com → "Hi Akanksha,"
- akhil@ibhubs.co → "Hi Akhil,"
- john.doe@company.com → "Hi John,"
```

### Email Closing
```
Thanks for your time, {{ hr_name }}!
```

## Email Subject (Same for All)
```
Final Year @ VIT | IIT Bombay Intern | Meta Hacker Cup Rank 186
```

## File Structure
```
AutoReach-AI/
├── hr_emails.csv                    ← 2,332 HR emails
├── sent_emails.txt                  ← Auto-generated tracking
├── campaign.log                     ← Detailed one-line logs
├── .campaign_state.json             ← Progress state
├── CV_backend_Tarandeep_Singh_Juneja.pdf  ← Your resume (required)
├── templates/
│   ├── tsj_outreach.html.j2        ← HTML email template
│   └── tsj_outreach.txt.j2         ← Plain text template
└── q                               ← Quick command script
```

## Expected Results

### Per Day
- **Emails sent**: 450 (Gmail limit)
- **Success rate**: ~95-98% (based on email validity)
- **Time taken**: 75-150 minutes (with safety delays)

### Total Campaign (2,332 emails)
- **Duration**: ~6 days
- **Expected responses**: 2-5% (typical for cold email)
- **Expected meetings**: 5-15 potential conversations

## If Things Go Wrong

### Campaign stopped/paused?
```bash
./q t        # Check status
./q r hr_emails.csv tarandeepsinghjuneja@gmail.com  # Resume
```

### Rate limited (sent 450 emails)?
```bash
# System auto-detects and stops
# Check status:
./q t
# It will show rate limit countdown
# Auto-resume when quota resets (24h later)
./q r hr_emails.csv tarandeepsinghjuneja@gmail.com
# Waits automatically for quota reset, then resumes!
```

### Check what went wrong?
```bash
./q l 100    # View last 100 log entries
cat campaign.log | grep "ERROR"  # Show only errors
```

## Performance Tips

1. **First run slower?** (testing)
   - Let it send 10-20 emails first
   - Check if emails are landing in inboxes
   - Look for bounces in Gmail

2. **Steady progress?** 
   - Monitor with: `watch -n 5 "./q t"`
   - Check logs periodically: `./q l`

3. **Avoid blocks?**
   - 450 emails/day is safe limit
   - Default 90-150s delay per email
   - System auto-stops on rate limit

4. **Resume anytime?**
   - Can stop/resume multiple times
   - Won't send duplicates
   - Tracks all progress automatically

## Next Steps After Campaign

1. **Monitor inbox** for responses
2. **Track metrics**: sent vs engaged
3. **Follow up** with interested parties
4. **Refine message** based on response patterns
5. **Run campaigns** for other roles/companies

---

**Ready to launch?** Run: `./q s hr_emails.csv tarandeepsinghjuneja@gmail.com`
