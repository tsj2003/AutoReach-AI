# HR Outreach Campaign Plan

Pivot the AutoReach engine to run a live job outreach campaign to 100 target HR contacts from the cleaned Downloads CSV list.

## Proposed Changes

### Components

#### [NEW] [send_hr_outreach.py](file:///Users/tarandeepsinghjuneja/AutoReach-AI/scripts/send_hr_outreach.py)
A Python script that:
1. Opens the engine storage `autoreach_engine.db`.
2. Reads and cleans the `hr_contacts.csv` list (validating emails, filtering duplicates, and checking against existing database contacts).
3. Creates a new Engagement (`hr_outreach_100`) and Outbound Agent.
4. Selects the first 100 cleaned contacts.
5. Personalizes and schedules 100 `JobKind.EMAIL_SEND` tasks, setting their `scheduled_for` times spaced out by a random interval of 60 to 120 seconds.
6. Attaches `Tarandeep_Resume_AI (1).pdf` to each email.
7. Executes the jobs in a loops with progress reporting, updating status and cost ledgers.

## Verification Plan

### Dry-Run Verification
- Run `python scripts/send_hr_outreach.py --dry-run` to verify that all 100 jobs are correctly planned, templates are formatted, and attachments are validated without sending real emails.

### Live Launch
- Run `python scripts/send_hr_outreach.py --live` to begin executing the actual email sending sequence.
