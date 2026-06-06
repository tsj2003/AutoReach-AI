# ⚡ AutoReach Quick Commands

## Usage

### START Campaign
```bash
python quick_cli.py s emails.csv myemail@gmail.com
# Or: ./q s emails.csv myemail@gmail.com
```

### STOP Campaign
```bash
python quick_cli.py x
# Or: ./q x
```

### Check STATUS
```bash
python quick_cli.py t
# Or: ./q t
```

### View LOGS (last 20 lines)
```bash
python quick_cli.py l
python quick_cli.py l 30  # Show last 30 lines
# Or: ./q l
```

### RESUME (if paused by rate limit)
```bash
python quick_cli.py r emails.csv myemail@gmail.com
# Or: ./q r emails.csv myemail@gmail.com
# Auto-waits for quota reset before resuming
```

### Clear LOGS
```bash
python quick_cli.py c
# Or: ./q c
```

---

## Features

✅ **Super Short Commands**
- `s` = Start
- `x` = Stop
- `t` = Status
- `l` = Logs
- `r` = Resume
- `c` = Clear

✅ **One-Line Compact Logging**
```
[14:23:45] ✓ SENT user@example.com        40 chars subject
[14:23:46] ⊘ SKIP admin@corp.com          (already sent)
[14:25:12] ✗ ERROR hr@company.com         Invalid email format
[16:00:00] ⏸ RATE_LIMITED - resuming in 24h
```

✅ **Auto-Stop on Error**
- Stops immediately when rate limit hit
- Saves progress (sent count, where to resume)
- Returns exit code 1 for automation

✅ **Auto-Resume on Quota Reset**
- Detects rate limit from Gmail API
- Schedules retry after quota window
- Resumes automatically when time passes
- Tracks everything in `.campaign_state.json`

✅ **Fast Status Checks**
- Shows sent/failed/remaining
- Shows if currently running
- Shows rate limit countdown

---

## Log Format Reference

| Status | Meaning | Example |
|--------|---------|---------|
| ✓ SENT | Email sent successfully | `[14:23:45] ✓ SENT user@example.com` |
| ⊘ SKIP | Already sent before | `[14:23:46] ⊘ SKIP admin@corp.com` |
| ✗ ERROR | Failed to send | `[14:25:12] ✗ ERROR hr@company.com` |
| ⏸ RATE_LIMIT | Quota exceeded | `[16:00:00] ⏸ RATE_LIMIT - resuming in 24h` |
| ▶ START | Campaign started | `[08:00:00] ▶ START emails.csv` |
| ⏹ STOP | Campaign stopped | `[09:30:00] ⏹ STOP (manual)` |
| ⤴ RESUME | Campaign resumed | `[10:00:00] ⤴ RESUME from point 450` |
| ✓ COMPLETE | Campaign finished | `[17:00:00] ✓ COMPLETE (500 sent)` |

---

## State File

Campaign state is automatically saved to `.campaign_state.json`:
```json
{
  "status": "running",
  "total": 5000,
  "sent": 450,
  "failed": 2,
  "retry_after": "2026-02-15T16:00:00",
  "process_id": 12345
}
```

## Tips

1. **Running in background forever?**
   ```bash
   nohup python quick_cli.py s emails.csv myemail@gmail.com &
   ```

2. **Check logs while running:**
   ```bash
   watch -n 5 "python quick_cli.py l 10"
   ```

3. **Resume after terminal closes:**
   ```bash
   python quick_cli.py r emails.csv myemail@gmail.com
   # Auto-detects rate limit window and waits
   ```

4. **Batch Size (emails per day):**
   ```bash
   python quick_cli.py s emails.csv myemail@gmail.com 500
   ```
