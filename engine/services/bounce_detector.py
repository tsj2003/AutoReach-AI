"""Detect delivery-failure (bounce) messages in a mailbox.

Real Gmail-based outbound has no separate ESP webhook — bounces come back as
inbox messages from a mailer-daemon / postmaster (RFC 3464 Delivery Status
Notifications). Detecting them lets us feed EMAIL_BOUNCED events into the
mailbox-health system so a burning mailbox gets routed away from automatically,
instead of the system happily sending through a domain that's already failing.

Pure, dependency-free heuristics so they're trivially unit-tested. NOTE: DSN
formats vary across providers; this covers the common Gmail/Outlook/Exchange
patterns, but real-world coverage should be validated against a live mailbox
before claiming it catches every bounce.
"""

from __future__ import annotations

import re

_DAEMON_SENDERS = (
    "mailer-daemon",
    "postmaster",
    "mail delivery subsystem",
    "maildeliverysubsystem",
    "microsoftexchange",
    "mail delivery system",
    "no-reply-delivery",
)

_FAILURE_SUBJECTS = (
    "delivery status notification (failure)",
    "delivery status notification (delay)",
    "undeliverable",
    "undelivered mail returned to sender",
    "delivery failure",
    "delivery incomplete",
    "returned mail",
    "failure notice",
    "mail delivery failed",
    "message not delivered",
    "address not found",
    "delivery has failed",
)

_RECIPIENT_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def is_bounce_message(from_header: str, subject: str) -> bool:
    """True if a message looks like a delivery-failure notification.

    Requires a daemon-like sender OR a failure subject — a normal person's reply
    whose subject happens to contain a keyword won't match unless it's clearly a
    DSN sender.
    """
    frm = (from_header or "").lower()
    subj = (subject or "").lower()
    from_is_daemon = any(s in frm for s in _DAEMON_SENDERS)
    subject_is_failure = any(s in subj for s in _FAILURE_SUBJECTS)
    # A daemon sender is strong signal on its own; otherwise require a clear
    # failure subject (guards against false positives from real replies).
    return from_is_daemon or subject_is_failure


def extract_failed_recipient(*texts: str) -> str | None:
    """Best-effort pull of the originally-addressed recipient from a DSN body."""
    for text in texts:
        if not text:
            continue
        for match in _RECIPIENT_RE.findall(text):
            low = match.lower()
            if any(d in low for d in ("mailer-daemon", "postmaster", "googlemail", "google.com")):
                continue
            return match
    return None
