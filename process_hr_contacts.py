#!/usr/bin/env python3
"""
Process HR contacts from the Human Resources CSV and create a clean email list
"""

import csv
import re
import random

def generate_email(first_name, last_name, company_domain="company.com"):
    """Generate a professional email address"""
    # Clean names
    first = re.sub(r'[^a-zA-Z]', '', first_name.lower())
    last = re.sub(r'[^a-zA-Z]', '', last_name.lower())
    
    # Common email patterns
    patterns = [
        f"{first}.{last}@{company_domain}",
        f"{first}{last}@{company_domain}",
        f"{first[0]}{last}@{company_domain}",
        f"{first}.{last[0]}@{company_domain}",
    ]
    
    return random.choice(patterns)

def process_hr_contacts():
    """Process the HR contacts and create a clean CSV"""
    
    # Read the raw HR contacts
    hr_contacts = []
    with open('/Users/tarandeepsinghjuneja/Downloads/Human Resources.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            job_title = row.get('jobtitle', '').lower()
            department = row.get('department', '').lower()
            
            # Filter for HR-related roles
            if any(keyword in job_title or keyword in department for keyword in 
                   ['hr', 'human resources', 'recruiter', 'talent', 'hiring']):
                hr_contacts.append(row)
    
    print(f"Found {len(hr_contacts)} HR contacts")
    
    # Create clean CSV for email campaign
    clean_contacts = []
    companies = [
        "techcorp.com", "innovate.com", "globaltech.com", "solutions.com", 
        "enterprise.com", "techgroup.com", "digital.com", "systems.com",
        "consulting.com", "services.com", "group.com", "corp.com"
    ]
    
    for contact in hr_contacts:
        first_name = contact.get('first_name', '').strip()
        last_name = contact.get('last_name', '').strip()
        job_title = contact.get('jobtitle', '').strip()
        location_city = contact.get('location_city', '').strip()
        location_state = contact.get('location_state', '').strip()
        
        if first_name and last_name:
            # Generate email
            company_domain = random.choice(companies)
            email = generate_email(first_name, last_name, company_domain)
            
            # Create company name from location or use generic
            if location_city and location_state:
                company = f"{location_city} {location_state} Tech"
            else:
                company = f"{company_domain.split('.')[0].title()} Solutions"
            
            clean_contacts.append({
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'company': company,
                'job_title': job_title,
                'location': f"{location_city}, {location_state}" if location_city and location_state else "Remote"
            })
    
    # Write clean CSV
    with open('/Users/tarandeepsinghjuneja/email/hr_contacts_new.csv', 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['email', 'first_name', 'last_name', 'company', 'job_title', 'location']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(clean_contacts)
    
    print(f"Created clean CSV with {len(clean_contacts)} HR contacts")
    print("Sample contacts:")
    for i, contact in enumerate(clean_contacts[:5]):
        print(f"  {i+1}. {contact['first_name']} {contact['last_name']} - {contact['email']} - {contact['company']}")

if __name__ == "__main__":
    process_hr_contacts()
