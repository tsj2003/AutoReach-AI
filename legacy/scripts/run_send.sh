#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: ./run_send.sh <csv-path> [additional-flags]"
  echo "Example dry-run: ./run_send.sh '23800+ HR Emails with Recruitment Agencies Contacts - 2800+ HR's Outreach list - Recently updated (1).csv' --dry-run --reverse --limit 5"
  echo "To actually send, omit --dry-run. The script will prompt for confirmation." 
  exit 1
fi

CSV="$1"
shift

# If --dry-run was not provided, ask for confirmation before sending real emails
ARGS=" $* "
if [[ "$ARGS" != *" --dry-run "* ]]; then
  read -p "No --dry-run provided; this will SEND real emails. Continue? (y/N) " ans
  if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
    echo "Aborted by user. Add --dry-run to preview without sending."
    exit 1
  fi
fi

echo "Running mailer with CSV: $CSV"

python3 bulk_mail_with_attachment.py \
  --csv "$CSV" \
  --text-template templates/application_inquiry_v2.txt.j2 \
  --html-template templates/application_inquiry.html.j2 \
  --subject "SDE Application | IIT Bombay Intern + Top 0.5% Meta Hacker Cup" \
  "$@"
