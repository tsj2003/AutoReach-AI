#!/usr/bin/env python3
"""
Create a smaller, safer list with realistic HR email addresses
"""

import csv
import random

def create_safe_hr_list():
    """Create a smaller, safer list of HR contacts"""
    
    # Real HR email patterns from major companies
    real_hr_emails = [
        "hr@google.com", "careers@microsoft.com", "talent@amazon.com",
        "hr@apple.com", "recruiting@meta.com", "jobs@netflix.com",
        "hr@tesla.com", "careers@uber.com", "talent@airbnb.com",
        "hr@spotify.com", "jobs@slack.com", "recruiting@zoom.com",
        "hr@salesforce.com", "careers@adobe.com", "talent@oracle.com",
        "hr@ibm.com", "jobs@intel.com", "recruiting@cisco.com",
        "hr@nvidia.com", "careers@amd.com", "talent@qualcomm.com",
        "hr@paypal.com", "jobs@square.com", "recruiting@stripe.com",
        "hr@shopify.com", "careers@zendesk.com", "talent@hubspot.com",
        "hr@atlassian.com", "jobs@canva.com", "recruiting@figma.com",
        "hr@notion.com", "careers@linear.com", "talent@vercel.com",
        "hr@supabase.com", "jobs@planetscale.com", "recruiting@railway.com",
        "hr@render.com", "careers@fly.io", "talent@netlify.com",
        "hr@vercel.com", "jobs@supabase.com", "recruiting@planetscale.com"
    ]
    
    # Create 100 safe contacts
    safe_contacts = []
    companies = [
        "Google", "Microsoft", "Amazon", "Apple", "Meta", "Netflix",
        "Tesla", "Uber", "Airbnb", "Spotify", "Slack", "Zoom",
        "Salesforce", "Adobe", "Oracle", "IBM", "Intel", "Cisco",
        "NVIDIA", "AMD", "Qualcomm", "PayPal", "Square", "Stripe",
        "Shopify", "Zendesk", "HubSpot", "Atlassian", "Canva", "Figma",
        "Notion", "Linear", "Vercel", "Supabase", "PlanetScale", "Railway",
        "Render", "Fly.io", "Netlify", "Vercel", "Supabase", "PlanetScale"
    ]
    
    for i in range(100):
        email = real_hr_emails[i % len(real_hr_emails)]
        company = companies[i % len(companies)]
        first_name = f"HR{i+1:02d}"
        last_name = "Recruiter"
        
        safe_contacts.append({
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'company': company,
            'job_title': 'HR Recruiter',
            'location': 'Remote'
        })
    
    # Write safe CSV
    with open('/Users/tarandeepsinghjuneja/email/hr_contacts_safe.csv', 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['email', 'first_name', 'last_name', 'company', 'job_title', 'location']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(safe_contacts)
    
    print(f"Created safe CSV with {len(safe_contacts)} HR contacts")
    print("Sample contacts:")
    for i, contact in enumerate(safe_contacts[:5]):
        print(f"  {i+1}. {contact['first_name']} {contact['last_name']} - {contact['email']} - {contact['company']}")

if __name__ == "__main__":
    create_safe_hr_list()
