#!/usr/bin/env python3
"""
Process the real HR emails CSV and create a clean email list
"""

import csv
import re

def extract_company_from_email(email):
    """Extract company name from email domain"""
    domain = email.split('@')[1].split('.')[0]
    
    # Map common domains to company names
    company_map = {
        'ibm': 'IBM',
        'wipro': 'Wipro',
        'infosys': 'Infosys',
        'oracle': 'Oracle',
        'cisco': 'Cisco',
        'siemens': 'Siemens',
        'hp': 'HP',
        'intel': 'Intel',
        'ericssson': 'Ericsson',
        'nokia': 'Nokia',
        'lucent': 'Lucent',
        'sap': 'SAP',
        'ge': 'General Electric',
        'honeywell': 'Honeywell',
        'philips': 'Philips',
        'igate': 'iGATE',
        'cgi': 'CGI',
        'wipro': 'Wipro',
        'tcs': 'TCS',
        'accenture': 'Accenture'
    }
    
    return company_map.get(domain.lower(), domain.title())

def extract_name_from_email(email):
    """Extract name from email address"""
    local_part = email.split('@')[0]
    
    # Remove common prefixes/suffixes
    name = local_part.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    
    # Split into parts
    parts = name.split()
    
    if len(parts) >= 2:
        first_name = parts[0].title()
        last_name = parts[1].title()
    else:
        first_name = parts[0].title()
        last_name = "HR"
    
    return first_name, last_name

def process_real_hr_emails():
    """Process the real HR emails CSV"""
    
    # Read the real HR emails
    hr_contacts = []
    with open('/Users/tarandeepsinghjuneja/Downloads/hr_emails_full.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get('Email', '').strip()
            if email and '@' in email:
                first_name, last_name = extract_name_from_email(email)
                company = extract_company_from_email(email)
                
                hr_contacts.append({
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'company': company,
                    'job_title': 'HR Professional',
                    'location': 'India'
                })
    
    # Write clean CSV
    with open('/Users/tarandeepsinghjuneja/email/hr_contacts_real.csv', 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['email', 'first_name', 'last_name', 'company', 'job_title', 'location']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(hr_contacts)
    
    print(f"Processed {len(hr_contacts)} real HR contacts")
    print("Sample contacts:")
    for i, contact in enumerate(hr_contacts[:10]):
        print(f"  {i+1}. {contact['first_name']} {contact['last_name']} - {contact['email']} - {contact['company']}")

if __name__ == "__main__":
    process_real_hr_emails()
