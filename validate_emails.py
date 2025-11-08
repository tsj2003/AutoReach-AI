#!/usr/bin/env python3
import csv
import re
import dns.resolver
import smtplib
import socket
from email.mime.text import MIMEText

def validate_email_syntax(email):
    """Basic email syntax validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def check_mx_record(domain):
    """Check if domain has valid MX record"""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        return len(answers) > 0
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        return False

def check_smtp_connection(email):
    """Check if SMTP server accepts the email (without sending)"""
    try:
        domain = email.split('@')[1]
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(mx_records[0].exchange)
        
        # Connect to SMTP server
        server = smtplib.SMTP(mx_record, 25, timeout=10)
        server.quit()
        return True
    except:
        return False

def is_well_known_company(email):
    """Check if it's a well-known company domain"""
    well_known_domains = [
        'tcs.com', 'infosys.com', 'wipro.com', 'hcl.com', 'techmahindra.com',
        'capgemini.com', 'accenture.com', 'cognizant.com', 'lntinfotech.com',
        'mphasis.com', 'hexaware.com', 'virtusa.com', 'ust-global.com',
        'genpact.com', 'exlservice.com', 'wns.com', 'nttdata.com',
        'prolifics.com', 'cyient.com', 'valuelabs.com', 'neudesic.com',
        'bahwancybertek.com', 'peoplestrong.com', 'adp.com'
    ]
    domain = email.split('@')[1].lower()
    return domain in well_known_domains

def validate_emails(input_csv, output_csv):
    """Validate emails and create a clean list"""
    valid_emails = []
    invalid_emails = []
    
    print("🔍 Validating email addresses...")
    
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for i, row in enumerate(reader, 1):
            email = row['email'].strip().lower()
            first_name = row['first_name']
            company = row['company']
            
            print(f"Checking {i}: {email}")
            
            # Step 1: Basic syntax check
            if not validate_email_syntax(email):
                print(f"  ❌ Invalid syntax: {email}")
                invalid_emails.append({'email': email, 'reason': 'Invalid syntax'})
                continue
            
            # Step 2: Check if well-known company
            if not is_well_known_company(email):
                print(f"  ⚠️  Unknown company domain: {email}")
                invalid_emails.append({'email': email, 'reason': 'Unknown company domain'})
                continue
            
            # Step 3: Check MX record
            domain = email.split('@')[1]
            if not check_mx_record(domain):
                print(f"  ❌ No MX record: {email}")
                invalid_emails.append({'email': email, 'reason': 'No MX record'})
                continue
            
            # If all checks pass
            valid_emails.append({
                'email': email,
                'first_name': first_name,
                'company': company
            })
            print(f"  ✅ Valid: {email}")
    
    # Write valid emails
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['email', 'first_name', 'company'])
        writer.writeheader()
        writer.writerows(valid_emails)
    
    print(f"\n📊 Results:")
    print(f"✅ Valid emails: {len(valid_emails)}")
    print(f"❌ Invalid emails: {len(invalid_emails)}")
    print(f"📁 Saved valid emails to: {output_csv}")
    
    return len(valid_emails)

if __name__ == "__main__":
    input_file = "cleaned_new_contacts.csv"
    output_file = "validated_contacts.csv"
    
    valid_count = validate_emails(input_file, output_file)
    
    if valid_count > 0:
        print(f"\n🎯 Ready to send to {valid_count} validated contacts!")
    else:
        print("\n❌ No valid contacts found!")
