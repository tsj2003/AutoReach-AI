# Job Application Email Campaign - Ready to Launch

## 📊 Campaign Details
- **Total HR Contacts**: 1,809 HR professionals
- **Email Address**: junejatarandeepsingh@gmail.com
- **Delay Between Emails**: 1 minute (60 seconds)
- **Batch Size**: 10 emails per batch
- **Resume**: Automatically attached to every email
- **Format**: Simple, professional email template

## 📧 Email Features
- **Personalized**: Each email uses HR person's first name and company
- **Subject**: "Software Development Opportunities - [Company Name]"
- **Content**: Professional software development inquiry
- **Attachment**: Your resume PDF automatically attached
- **Simple Format**: Clean, humanized email without fancy styling

## 🚀 Ready to Send Commands

### Test First (Safe - No Sending):
```bash
cd /Users/tarandeepsinghjuneja/email
source .venv/bin/activate
python send_job_applications.py --csv hr_contacts_new.csv --from junejatarandeepsingh@gmail.com --dry-run --batch-size 5
```

### Send Small Test (5 emails):
```bash
python send_job_applications.py --csv hr_contacts_new.csv --from junejatarandeepsingh@gmail.com --batch-size 5
```

### Send Full Campaign (1,809 emails):
```bash
python send_job_applications.py --csv hr_contacts_new.csv --from junejatarandeepsingh@gmail.com
```

## ⏱️ Timing Information
- **1 minute delay** between each email
- **Total time for full campaign**: ~30 hours (1,809 emails × 1 minute)
- **Batches**: 181 batches of 10 emails each
- **Delay between batches**: 1-2 minutes

## 📋 Sample Contacts
1. Regen Nafzger - regen.n@enterprise.com - Cleveland Ohio Tech
2. Lola Burrells - lolaburrells@techgroup.com - Pittsburgh Pennsylvania Tech  
3. Hamel Edgeler - hamel.edgeler@techcorp.com - Cleveland Ohio Tech
4. Peta Gosson - pgosson@digital.com - Cleveland Ohio Tech
5. Lenka Astridge - lenka.a@systems.com - Cleveland Ohio Tech

## ✅ What's Configured
- ✅ 1,809 HR contacts from your CSV
- ✅ 1-minute delays between emails
- ✅ Resume automatically attached
- ✅ Simple email template
- ✅ Personalized with names and companies
- ✅ Your email: junejatarandeepsingh@gmail.com

## 🎯 Ready to Launch!
The campaign is ready to send professional job application emails to 1,809 HR professionals with 1-minute delays between each email.
