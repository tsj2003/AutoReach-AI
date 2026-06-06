"""
Google Postmaster Tools API integration for AutoReach-AI.
Monitors domain spam complaint rate and triggers auto-pause when threshold is exceeded.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def get_domain_spam_rate(credentials, domain: str) -> float | None:
    """
    Query Google Postmaster Tools for the domain's spam complaint rate.
    
    Args:
        credentials: google.oauth2.credentials.Credentials with postmaster.readonly scope.
        domain: The sender domain to check (e.g., 'example.com').
    
    Returns:
        Spam rate as a float (0.0 to 1.0), or None if unavailable.
    """
    try:
        from googleapiclient.discovery import build

        service = build('gmailpostmastertools', 'v1', credentials=credentials)

        # Query the last 3 days of traffic stats
        today = date.today()
        start_date = today - timedelta(days=3)

        name = f"domains/{domain}/trafficStats/{start_date.isoformat()}"

        try:
            result = service.domains().trafficStats().get(name=name).execute()
            spam_rate = result.get('spammyFeedbackLoops', [{}])
            
            # The API returns userReportedSpamRatio directly
            user_spam_ratio = result.get('userReportedSpamRatio', None)
            if user_spam_ratio is not None:
                return float(user_spam_ratio)

            # Fallback: try spamRate field
            direct_rate = result.get('spamRate', None)
            if direct_rate is not None:
                return float(direct_rate)

        except Exception as e:
            # Domain may not be registered in Postmaster Tools
            if '404' in str(e) or 'not found' in str(e).lower():
                logger.info(f"Domain {domain} not registered in Google Postmaster Tools")
                return None
            raise

    except ImportError:
        logger.warning("google-api-python-client not installed for Postmaster API")
        return None
    except Exception as e:
        logger.warning(f"Postmaster API check failed for {domain}: {e}")
        return None


def check_domain_health(credentials, domain: str) -> dict:
    """
    Full domain health check via Postmaster Tools.
    Returns structured health report.
    """
    spam_rate = get_domain_spam_rate(credentials, domain)

    health = {
        'domain': domain,
        'spam_rate': spam_rate,
        'status': 'unknown',
        'action': None,
    }

    if spam_rate is None:
        health['status'] = 'no_data'
        health['message'] = 'No Postmaster Tools data available for this domain.'
    elif spam_rate >= 0.003:  # 0.3% — fatal
        health['status'] = 'critical'
        health['action'] = 'force_pause'
        health['message'] = (
            f'CRITICAL: Spam rate {spam_rate*100:.2f}% exceeds Google\'s fatal 0.3% threshold. '
            f'Your sender reputation may be permanently damaged.'
        )
    elif spam_rate >= 0.0015:  # 0.15% — warning
        health['status'] = 'warning'
        health['action'] = 'safe_pause'
        health['message'] = (
            f'WARNING: Spam rate {spam_rate*100:.2f}% exceeds 0.15% threshold. '
            f'Campaign auto-paused to protect your domain.'
        )
    else:
        health['status'] = 'healthy'
        health['message'] = f'Domain health is good. Spam rate: {spam_rate*100:.3f}%'

    return health
