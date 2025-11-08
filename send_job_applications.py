#!/usr/bin/env python3
"""
Professional Job Application Email Sender
Sends personalized job application emails to HR contacts with spam filter avoidance
"""

import argparse
import csv
import logging
import os
import random
import sys
import time
from datetime import datetime

from bulk_mail_with_attachment import main as bulk_mail_main

def create_batches(csv_file, batch_size=10):
    """Split the CSV into smaller batches for better deliverability"""
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    batches = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        batch_file = f"batch_{i//batch_size + 1}.csv"
        with open(batch_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(batch)
        batches.append(batch_file)
    
    return batches

def send_batch(batch_file, from_email, delay_min=30, delay_max=60, email_sleep_min=60, email_sleep_max=60):
    """Send emails for a single batch with delays"""
    subject_template = "Application for Software Development Role at {{ company }}"
    
    # Add random delay to avoid pattern detection
    delay = random.uniform(delay_min, delay_max)
    logging.info(f"Waiting {delay:.1f} seconds before sending batch {batch_file}")
    time.sleep(delay)
    
    # Send the batch (TEXT ONLY, no attachment)
    args = [
        '--csv', batch_file,
        '--subject', subject_template,
        '--text-template', 'templates/cold_email.txt.j2',
        '--from', from_email,
        '--email-column', 'email',
        '--sleep-min', str(email_sleep_min),
        '--sleep-max', str(email_sleep_max),
        '--verbose'
    ]
    
    return bulk_mail_main(args)

def main():
    parser = argparse.ArgumentParser(description="Send professional job application emails")
    parser.add_argument("--csv", required=True, help="Path to HR contacts CSV")
    parser.add_argument("--from", dest="from_email", required=True, help="Your email address")
    parser.add_argument("--batch-size", type=int, default=10, help="Emails per batch (default: 10)")
    parser.add_argument("--delay-min", type=int, default=60, help="Minimum delay between batches in seconds")
    parser.add_argument("--delay-max", type=int, default=120, help="Maximum delay between batches in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails without sending")
    parser.add_argument("--email-sleep-min", type=int, default=60, help="Minimum per-email delay in seconds")
    parser.add_argument("--email-sleep-max", type=int, default=60, help="Maximum per-email delay in seconds")
    parser.add_argument("--start-batch", type=int, default=1, help="Start from batch number (for resuming)")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(f"job_applications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
            logging.StreamHandler()
        ]
    )
    
    if args.dry_run:
        logging.info("DRY RUN MODE - No emails will be sent")
        # Just run the first batch as dry run
        batches = create_batches(args.csv, args.batch_size)
        batch_file = batches[0]
        subject_template = "Application for Software Development Role at {{ company }}"
        
        dry_args = [
            '--csv', batch_file,
            '--subject', subject_template,
            '--text-template', 'templates/cold_email.txt.j2',
            '--from', args.from_email,
            '--email-column', 'email',
            '--sleep-min', str(args.email_sleep_min),
            '--sleep-max', str(args.email_sleep_max),
            '--dry-run',
            '--verbose'
        ]
        return bulk_mail_main(dry_args)
    
    # Create batches
    logging.info(f"Creating batches of {args.batch_size} emails each")
    batches = create_batches(args.csv, args.batch_size)
    logging.info(f"Created {len(batches)} batches")
    
    # Send batches
    successful_batches = 0
    failed_batches = 0
    
    for i, batch_file in enumerate(batches[args.start_batch - 1:], args.start_batch):
        logging.info(f"Processing batch {i}/{len(batches)}: {batch_file}")
        
        try:
            result = send_batch(
                batch_file,
                args.from_email,
                args.delay_min,
                args.delay_max,
                args.email_sleep_min,
                args.email_sleep_max,
            )
            if result == 0:
                successful_batches += 1
                logging.info(f"✅ Batch {i} completed successfully")
            else:
                failed_batches += 1
                logging.error(f"❌ Batch {i} failed")
        except Exception as e:
            failed_batches += 1
            logging.error(f"❌ Batch {i} failed with error: {e}")
        
        # Clean up batch file
        try:
            os.remove(batch_file)
        except:
            pass
    
    logging.info(f"📊 Summary: {successful_batches} successful, {failed_batches} failed batches")
    
    return 0 if failed_batches == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
