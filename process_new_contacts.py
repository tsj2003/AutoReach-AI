#!/usr/bin/env python3
import csv
import re
import dns.resolver
import os
import sys

def is_corporate_domain(email):
    """Check if email domain is corporate (not personal)"""
    personal_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com', 'icloud.com', 'rediffmail.com', 'live.com']
    domain = email.split('@')[-1]
    return domain not in personal_domains

def has_mx_record(domain):
    """Check if domain has valid MX record"""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        return len(answers) > 0
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        return False

def clean_new_csv(input_csv, output_csv):
    """Clean the new CSV file and extract valid corporate emails"""
    cleaned_rows = []
    seen_emails = set()
    
    print(f"Processing {input_csv}...")
    
    with open(input_csv, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        
        for row_num, row in enumerate(reader, 1):
            # Extract email from the 'Email' column
            email = row.get('Email', '').strip().lower()
            
            if not email:
                continue
            
            # Extract first name and company
            first_name = row.get('First Name', 'HR').strip()
            company = row.get('Company Name', '').strip()
            
            # Basic email format validation
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                print(f"Row {row_num}: Invalid email format: {email}")
                continue
            
            # Check for duplicates
            if email in seen_emails:
                print(f"Row {row_num}: Duplicate email: {email}")
                continue
            
            # Check if corporate domain
            if not is_corporate_domain(email):
                print(f"Row {row_num}: Personal email domain: {email}")
                continue
            
            # Check MX record
            domain = email.split('@')[-1]
            if not has_mx_record(domain):
                print(f"Row {row_num}: No MX record for domain: {domain}")
                continue
            
            # Add to cleaned list
            cleaned_rows.append({
                'email': email,
                'first_name': first_name,
                'company': company
            })
            seen_emails.add(email)
            
            if row_num % 50 == 0:
                print(f"Processed {row_num} rows, found {len(cleaned_rows)} valid contacts...")
    
    # Write cleaned data
    with open(output_csv, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=['email', 'first_name', 'company'])
        writer.writeheader()
        writer.writerows(cleaned_rows)
    
    print(f"✅ Cleaned contacts: {len(cleaned_rows)}")
    print(f"📁 Saved to: {output_csv}")
    
    return len(cleaned_rows)

def main():
    input_csv = "new_hr_contacts.csv"
    output_csv = "cleaned_new_contacts.csv"
    
    if not os.path.exists(input_csv):
        print(f"❌ Input file not found: {input_csv}")
        sys.exit(1)
    
    cleaned_count = clean_new_csv(input_csv, output_csv)
    
    if cleaned_count == 0:
        print("❌ No valid contacts found after cleaning.")
        sys.exit(1)
    
    print(f"\n🎯 Ready to send emails to {cleaned_count} valid HR contacts!")
    print(f"📧 Use: python send_job_applications.py --csv {output_csv} --from junejatarandeepsingh@gmail.com")

if __name__ == "__main__":
    main()
