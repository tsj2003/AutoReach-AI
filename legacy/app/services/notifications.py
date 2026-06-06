import os
import sys
import smtplib
from email.mime.text import MIMEText
import logging

logger = logging.getLogger(__name__)

def send_critical_alert(user_email, campaign_name, error_message):
    """
    Sends a critical campaign alert to the user's registration email.
    If central SMTP settings are unconfigured, prints the error & email payload to sys.stderr.
    """
    subject = f"AutoReach Alert: Campaign '{campaign_name}' Paused"
    body = (
        f"Hello,\n\n"
        f"This is an automated system alert from AutoReach-AI.\n\n"
        f"Your campaign '{campaign_name}' has been paused because all connected mailboxes "
        f"have encountered authentication errors or have been quarantined.\n\n"
        f"Error Details:\n{error_message}\n\n"
        f"Please log in to your dashboard to re-authenticate your mailboxes and resume your campaign.\n\n"
        f"Best regards,\n"
        f"AutoReach Infrastructure Shield"
    )

    # Load central SMTP settings
    smtp_host = os.getenv("SYSTEM_SMTP_HOST")
    smtp_port_str = os.getenv("SYSTEM_SMTP_PORT", "587")
    smtp_user = os.getenv("SYSTEM_SMTP_USER")
    smtp_password = os.getenv("SYSTEM_SMTP_PASSWORD")
    from_email = os.getenv("SYSTEM_FROM_EMAIL", "alerts@autoreach-ai.com")

    is_configured = bool(smtp_host and smtp_user and smtp_password)

    if not is_configured:
        # Fallback to sys.stderr
        err_msg = (
            f"\n--- SYSTEM CRITICAL ALERT FALLBACK ---\n"
            f"To: {user_email}\n"
            f"From: {from_email}\n"
            f"Subject: {subject}\n"
            f"Body:\n{body}\n"
            f"--------------------------------------\n"
        )
        print(err_msg, file=sys.stderr)
        logger.warning("Central SMTP not configured. Notification dumped to sys.stderr.")
        return False

    try:
        smtp_port = int(smtp_port_str)
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = user_email

        # Send email using standard smtplib
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [user_email], msg.as_string())
        
        logger.info(f"Critical alert successfully sent to {user_email}")
        return True
    except Exception as e:
        # In case of any SMTP send failure, also fallback to sys.stderr so execution is not blocked
        err_msg = (
            f"\n--- SYSTEM CRITICAL ALERT (SMTP SEND FAILED) ---\n"
            f"Error during SMTP send: {e}\n"
            f"To: {user_email}\n"
            f"From: {from_email}\n"
            f"Subject: {subject}\n"
            f"Body:\n{body}\n"
            f"----------------------------------------------\n"
        )
        print(err_msg, file=sys.stderr)
        logger.exception("Failed to send SMTP alert. Dumped to sys.stderr.")
        return False
