"""LinkedIn dispatch provider boundary."""

from __future__ import annotations


class LinkedInProvider:
    """Minimal LinkedIn executor interface for future channel automation."""

    def __init__(self, *, session_token: str) -> None:
        self.session_token = session_token

    async def send_connection_request(self, *, profile_url: str, message: str) -> bool:
        return True
