#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

SKIP="${1:-0}"
LOG_FILE="campaign_screen.log"

exec >> "$LOG_FILE" 2>&1

echo "==== Campaign started at $(date) with skip=$SKIP ===="

python3 bulk_mail_with_attachment.py \
  --csv out/hr_reachout_list.csv \
  --subject "SDE 2026 | VIT CSE | IIT Bombay Intern" \
  --text-template templates/tsj_outreach.txt.j2 \
  --html-template templates/tsj_outreach.html.j2 \
  --attachment Tarandeep_Resume_SDE.pdf \
  --sleep-min 90 \
  --sleep-max 150 \
  --batch-size 450 \
  --skip "$SKIP"
