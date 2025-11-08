#!/usr/bin/env python3
"""
Filter the HR emails to only include valid, well-known company domains
"""

import csv

def is_valid_company_domain(email):
    """Check if email domain is from a well-known company"""
    domain = email.split('@')[1].lower()
    
    # List of known valid company domains
    valid_domains = [
        'ibm.com', 'wipro.com', 'infosys.com', 'oracle.com', 'cisco.com',
        'siemens.com', 'hp.com', 'intel.com', 'ericsson.com', 'nokia.com',
        'lucent.com', 'sap.com', 'ge.com', 'honeywell.com', 'philips.com',
        'igate.com', 'cgi.com', 'tcs.com', 'accenture.com', 'microsoft.com',
        'google.com', 'amazon.com', 'apple.com', 'meta.com', 'netflix.com',
        'tesla.com', 'uber.com', 'airbnb.com', 'spotify.com', 'slack.com',
        'zoom.com', 'salesforce.com', 'adobe.com', 'paypal.com', 'square.com',
        'stripe.com', 'shopify.com', 'zendesk.com', 'hubspot.com', 'atlassian.com',
        'canva.com', 'figma.com', 'notion.com', 'linear.com', 'vercel.com',
        'supabase.com', 'planetscale.com', 'railway.com', 'render.com', 'fly.io',
        'netlify.com', 'delphi.com', 'visteon.com', 'quinnox.com', 'citaqus.com',
        'ltinfotech.com', 'bestvisionindia.com', 'picopeta.com', 'imageli.com',
        'dynpronindia.com', 'wdc.in', 'ge.com', 'aricent.com', 'iteamic.com',
        'vcu.in', 'webyog.com', 'hrmcindia.com', 'cgi.com', 'delphi.com',
        'wipro.com', 'techsearch.co.in', 'analog.com', 'speedconsult.com',
        'ebss.org', 'geniys.group.com', 'ericssson.com', 'brocade.com',
        'vcentric.com', 'hp.com', 'siemens.com', 'replicon.com', 'ascendum.com',
        'chakrainteractive.com', 'comcast.net', 'cliosoft.com', 'cisco.com',
        'eurocontiles.co.in', 'ustechsolutionsinc.net', 'itsinfotech.org',
        'infobase.in', 'hypersoftindia.com', 'ellipsesoftware.com',
        'hysistechnologies.com', 'samcosoft.com', 'honeywell.com', 'sampoorna.com',
        'siemens.com', 'lucasvs.co.in', 'sgi.com', 'nokia.com', 'sanovi.com',
        'alcatel.com', 'microchip.com', 'neweraindia.com', 'tvec.in',
        'ivycomptech.com', 'melstar.com', 'mcafee.com', 'ishisystems.com',
        'vsnl.com', 'kellyit.co.in', 'tejastechindia.com', 'i2.com',
        'mphasis.com', 'onmobile.com', 'ubics.com', 'zenithsoft.com',
        'meritrac.com', 'incotecindia.com', 'xansa.com', 'siemensvdo.com',
        'infoappstech.com', 'eclerx.com', 'oracle.com', 'cordys.com',
        'iflexsolutions.com', 'cransesoftware.com', 'adeasolutions.com',
        'cae.com', 'ptpl.com', 'zte.com', 'qsitglobal.com', 'arsiglobal.co.in',
        'mindtree.com', 'sap.com', 'gm.com', 'netapp.com', 'huawei.com',
        'brooktechnologies.com', 'purpleace.com', 'peepalconsluting.com',
        'zmict.com', 'prion.in', 'insilicoss.com', 'nechlst.in', 'gscib.com',
        'supervalu.com', 'sasi.com', 'ti.com', 'fomax.in', 'dsmsoft.com',
        'bluechipsw.com', 'metlife.com', '3i-infotech.com', 'whirletchindia.com',
        'compassites.net', 'cosmonetsolutions.com', 'parkcontrols.com',
        'bluerose.com', 'trianz.com', 'roseindia.net', 'relq.com',
        'lgsoftindia.com', 'wisor.com', 'macfee.com'
    ]
    
    return domain in valid_domains

def filter_valid_emails():
    """Filter the HR emails to only include valid company domains"""
    
    valid_contacts = []
    with open('/Users/tarandeepsinghjuneja/Downloads/hr_emails_full.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get('Email', '').strip()
            if email and '@' in email and is_valid_company_domain(email):
                # Extract name and company
                local_part = email.split('@')[0]
                domain = email.split('@')[1]
                
                # Extract name
                name_parts = local_part.replace('.', ' ').replace('_', ' ').replace('-', ' ').split()
                if len(name_parts) >= 2:
                    first_name = name_parts[0].title()
                    last_name = name_parts[1].title()
                else:
                    first_name = name_parts[0].title()
                    last_name = "HR"
                
                # Extract company
                company = domain.split('.')[0].title()
                
                valid_contacts.append({
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'company': company,
                    'job_title': 'HR Professional',
                    'location': 'India'
                })
    
    # Write filtered CSV
    with open('/Users/tarandeepsinghjuneja/email/hr_contacts_valid.csv', 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['email', 'first_name', 'last_name', 'company', 'job_title', 'location']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(valid_contacts)
    
    print(f"Filtered to {len(valid_contacts)} valid HR contacts")
    print("Sample valid contacts:")
    for i, contact in enumerate(valid_contacts[:10]):
        print(f"  {i+1}. {contact['first_name']} {contact['last_name']} - {contact['email']} - {contact['company']}")

if __name__ == "__main__":
    filter_valid_emails()
