"""
Pre-flight DNS authentication validator for AutoReach-AI.
Checks SPF, DKIM, and DMARC records before allowing campaign launch.
"""

import logging

logger = logging.getLogger(__name__)

try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False
    logger.warning("dnspython not installed — DNS validation disabled")


def validate_sender_dns(domain: str) -> dict:
    """
    Check SPF, DKIM, DMARC records for a sender domain.
    Returns a dict with per-record results and an overall_pass flag.
    """
    results = {
        'domain': domain,
        'spf': {'found': False, 'record': None, 'valid': False, 'fix': ''},
        'dmarc': {'found': False, 'record': None, 'valid': False, 'fix': ''},
        'dkim': {'found': False, 'record': None, 'valid': False, 'fix': ''},
        'overall_pass': False,
        'available': DNS_AVAILABLE,
    }

    if not DNS_AVAILABLE:
        results['overall_pass'] = True  # Can't check, don't block
        return results

    # SPF Check — TXT record on root domain starting with "v=spf1"
    try:
        answers = dns.resolver.resolve(domain, 'TXT', lifetime=5.0)
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith('v=spf1'):
                results['spf'] = {'found': True, 'record': txt, 'valid': True, 'fix': ''}
                break
    except Exception:
        pass

    if not results['spf']['valid']:
        results['spf']['fix'] = (
            f'Add this TXT record to your DNS provider for {domain}:\n'
            f'Type: TXT\n'
            f'Host: @\n'
            f'Value: v=spf1 include:_spf.google.com ~all\n'
            f'TTL: 3600'
        )

    # DMARC Check — TXT record on _dmarc.domain starting with "v=DMARC1"
    try:
        answers = dns.resolver.resolve(f'_dmarc.{domain}', 'TXT', lifetime=5.0)
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith('v=DMARC1'):
                results['dmarc'] = {'found': True, 'record': txt, 'valid': True, 'fix': ''}
                break
    except Exception:
        pass

    if not results['dmarc']['valid']:
        results['dmarc']['fix'] = (
            f'Add this TXT record to your DNS provider:\n'
            f'Type: TXT\n'
            f'Host: _dmarc\n'
            f'Value: v=DMARC1; p=none; rua=mailto:dmarc@{domain}; pct=100\n'
            f'TTL: 3600'
        )

    # DKIM Check — try multiple common selectors
    selectors = ['google', 'default', 'selector1', 'selector2', 'k1', 'mail']
    for selector in selectors:
        try:
            answers = dns.resolver.resolve(
                f'{selector}._domainkey.{domain}', 'TXT', lifetime=3.0
            )
            for rdata in answers:
                txt = rdata.to_text().strip('"')
                if 'v=DKIM1' in txt or 'k=rsa' in txt or 'p=' in txt:
                    results['dkim'] = {
                        'found': True,
                        'record': txt[:120],
                        'valid': True,
                        'fix': '',
                    }
                    break
            if results['dkim']['found']:
                break
        except Exception:
            continue

    if not results['dkim']['valid']:
        results['dkim']['fix'] = (
            f'DKIM must be configured in your email provider (Google Workspace, etc.).\n'
            f'For Google Workspace:\n'
            f'1. Go to admin.google.com → Apps → Google Workspace → Gmail → Authenticate email\n'
            f'2. Click "Generate new record" and copy the TXT value\n'
            f'3. Add it as a TXT record at google._domainkey.{domain}'
        )

    results['overall_pass'] = all([
        results['spf']['valid'],
        results['dmarc']['valid'],
        results['dkim']['valid'],
    ])

    return results
