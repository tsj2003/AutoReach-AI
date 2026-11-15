"""RSS/Atom feed connector — lawful public feed ingestion."""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

from engine.security.safe_fetch import SafeFetchError, is_safe_fetch_url, safe_fetch
from engine.signals.connectors.base import ConnectorCapabilities, ConnectorCursor, SignalConnector
from engine.signals.events import ConnectorHealth, ConnectorStatus, SignalEvidence, SignalEvent, SignalFreshness
from engine.signals.extraction import extract_signal_candidate
from engine.signals.registry import get_signal_registry

logger = logging.getLogger(__name__)

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_RSS_MAX_ENTRIES = 100
_STRIP_TAGS = re.compile(r"<[^>]+>")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        dt = parsedate_to_datetime(value.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _strip_html(text: str) -> str:
    return _STRIP_TAGS.sub(" ", text or "").strip()


class RSSSignalConnector(SignalConnector):
    """Fetch and parse RSS 2.0 / Atom feeds into normalized SignalEvents."""

    CONNECTOR_KIND = "rss"
    DEFAULT_POLLING_SECONDS = 900  # 15 min — near-real-time, not real-time

    def __init__(
        self,
        *,
        source_id: str,
        feed_url: str | None = None,
        allowed_signal_types: list[str] | None = None,
        max_entries: int = 50,
    ) -> None:
        self._source_id = source_id
        self._feed_url = (feed_url or "").strip()
        self._allowed = {get_signal_registry().normalize(t) or t for t in (allowed_signal_types or [])}
        self._allowed = {t for t in self._allowed if t}
        self._max_entries = min(max_entries, _RSS_MAX_ENTRIES)
        self._last_error: str | None = None
        self._registry = get_signal_registry()

    @property
    def connector_kind(self) -> str:
        return self.CONNECTOR_KIND

    def capabilities(self) -> ConnectorCapabilities:
        configured = bool(self._feed_url and is_safe_fetch_url(self._feed_url))
        return ConnectorCapabilities(
            connector_kind=self.CONNECTOR_KIND,
            label="RSS / Atom feed",
            freshness=SignalFreshness.NEAR_REAL_TIME,
            polling_interval_seconds=self.DEFAULT_POLLING_SECONDS,
            supports_webhook=False,
            requires_credentials=False,
            configured=configured,
            supported_signal_types=tuple(self._registry.list_keys()),
        )

    def health(self) -> ConnectorHealth:
        if not self._feed_url:
            return ConnectorHealth(
                source_id=self._source_id,
                connector_kind=self.CONNECTOR_KIND,
                status=ConnectorStatus.NOT_CONFIGURED,
                message="NOT CONFIGURED — feed URL missing",
                freshness=SignalFreshness.NEAR_REAL_TIME,
            )
        if not is_safe_fetch_url(self._feed_url):
            return ConnectorHealth(
                source_id=self._source_id,
                connector_kind=self.CONNECTOR_KIND,
                status=ConnectorStatus.ERROR,
                message="Feed URL blocked by SSRF policy",
                freshness=SignalFreshness.NEAR_REAL_TIME,
            )
        if self._last_error:
            return ConnectorHealth(
                source_id=self._source_id,
                connector_kind=self.CONNECTOR_KIND,
                status=ConnectorStatus.ERROR,
                message=self._last_error,
                freshness=SignalFreshness.NEAR_REAL_TIME,
            )
        return ConnectorHealth(
            source_id=self._source_id,
            connector_kind=self.CONNECTOR_KIND,
            status=ConnectorStatus.HEALTHY,
            message="RSS connector ready",
            freshness=SignalFreshness.NEAR_REAL_TIME,
        )

    def fetch_events(
        self,
        *,
        tenant_id: str,
        cursor: ConnectorCursor,
        limit: int = 100,
    ) -> tuple[list[SignalEvent], ConnectorCursor]:
        if not self._feed_url or not is_safe_fetch_url(self._feed_url):
            self._last_error = "NOT CONFIGURED or URL blocked"
            return [], ConnectorCursor(
                last_cursor=cursor.last_cursor,
                error_state=self._last_error,
                retry_count=cursor.retry_count + 1,
            )

        try:
            result = safe_fetch(self._feed_url)
        except SafeFetchError as exc:
            self._last_error = str(exc)
            logger.warning("RSS fetch failed source=%s: %s", self._source_id, exc)
            return [], ConnectorCursor(
                last_cursor=cursor.last_cursor,
                error_state=self._last_error,
                retry_count=cursor.retry_count + 1,
            )

        if result.status_code >= 400:
            self._last_error = f"HTTP {result.status_code} from feed"
            return [], ConnectorCursor(
                last_cursor=cursor.last_cursor,
                error_state=self._last_error,
                retry_count=cursor.retry_count + 1,
            )

        try:
            entries = self._parse_feed(result.content)
        except ET.ParseError as exc:
            self._last_error = f"Malformed feed XML: {exc}"
            return [], ConnectorCursor(
                last_cursor=cursor.last_cursor,
                error_state=self._last_error,
                retry_count=cursor.retry_count + 1,
            )

        seen_ids = set()
        if cursor.last_cursor:
            seen_ids.update(cursor.last_cursor.split(","))

        events: list[SignalEvent] = []
        new_ids: list[str] = []
        now = datetime.now(timezone.utc)
        allowed = self._allowed or None

        for entry in entries[: self._max_entries]:
            entry_id = entry["id"]
            if entry_id in seen_ids:
                continue
            candidate = extract_signal_candidate(
                title=entry["title"],
                description=entry.get("description", ""),
                link=entry.get("link"),
                allowed_signal_types=allowed,
            )
            if candidate is None:
                continue
            canonical = self._registry.normalize(candidate.signal_type)
            if canonical is None:
                continue

            source_event_id = hashlib.sha256(entry_id.encode()).hexdigest()[:24]
            event_id = hashlib.sha256(
                f"{tenant_id}|{self._source_id}|{source_event_id}".encode()
            ).hexdigest()[:32]

            occurred_at = entry.get("published") or now
            evidence = SignalEvidence(
                summary=candidate.summary,
                source_url=candidate.source_url,
                matched_reason=candidate.matched_reason,
                raw_excerpt=candidate.raw_excerpt,
            )
            events.append(
                SignalEvent(
                    id=event_id,
                    tenant_id=tenant_id,
                    source_id=self._source_id,
                    source_event_id=source_event_id,
                    signal_type=canonical,
                    entity_type="company",
                    entity_id=candidate.company_domain,
                    company_domain=candidate.company_domain,
                    company_name=candidate.company_name,
                    person_identifier=None,
                    occurred_at=occurred_at,
                    observed_at=now,
                    confidence=candidate.confidence,
                    evidence=evidence,
                    source_url=candidate.source_url,
                    raw_payload={"feed_entry_id": entry_id, "feed_url": self._feed_url},
                    metadata={"connector": self.CONNECTOR_KIND, "feed_title": entry.get("feed_title")},
                    freshness=SignalFreshness.NEAR_REAL_TIME,
                )
            )
            new_ids.append(entry_id)
            if len(events) >= limit:
                break

        self._last_error = None
        combined_cursor = ",".join((seen_ids | set(new_ids)))
        # Keep cursor bounded
        if len(combined_cursor) > 8000:
            combined_cursor = combined_cursor[-8000:]

        new_cursor = ConnectorCursor(
            last_cursor=combined_cursor or cursor.last_cursor,
            last_success_at=now,
            last_event_at=events[-1].occurred_at if events else cursor.last_event_at,
            error_state=None,
            retry_count=0,
        )
        return events, new_cursor

    def rate_limit_delay_seconds(self) -> float:
        return 1.0

    @staticmethod
    def _parse_feed(content: bytes) -> list[dict[str, Any]]:
        root = ET.fromstring(content)
        tag = root.tag.split("}")[-1].lower()

        if tag == "feed":
            return RSSSignalConnector._parse_atom(root)
        if tag == "rss":
            return RSSSignalConnector._parse_rss(root)
        raise ET.ParseError(f"Unsupported feed root element: {tag}")

    @staticmethod
    def _parse_atom(root: ET.Element) -> list[dict[str, Any]]:
        feed_title = (root.findtext("atom:title", namespaces=_ATOM_NS) or "").strip()
        entries: list[dict[str, Any]] = []
        for item in root.findall("atom:entry", _ATOM_NS):
            entry_id = (item.findtext("atom:id", namespaces=_ATOM_NS) or "").strip()
            title = (item.findtext("atom:title", namespaces=_ATOM_NS) or "").strip()
            link_el = item.find("atom:link[@rel='alternate']", _ATOM_NS) or item.find("atom:link", _ATOM_NS)
            link = link_el.get("href") if link_el is not None else None
            summary = item.findtext("atom:summary", namespaces=_ATOM_NS) or item.findtext(
                "atom:content", namespaces=_ATOM_NS
            ) or ""
            published = _parse_datetime(item.findtext("atom:published", namespaces=_ATOM_NS))
            if published is None:
                published = _parse_datetime(item.findtext("atom:updated", namespaces=_ATOM_NS))
            if not entry_id:
                entry_id = hashlib.sha256(f"{title}|{link}".encode()).hexdigest()[:16]
            entries.append({
                "id": entry_id,
                "title": title,
                "description": _strip_html(summary),
                "link": link,
                "published": published,
                "feed_title": feed_title,
            })
        return entries

    @staticmethod
    def _parse_rss(root: ET.Element) -> list[dict[str, Any]]:
        channel = root.find("channel")
        if channel is None:
            return []
        feed_title = (channel.findtext("title") or "").strip()
        entries: list[dict[str, Any]] = []
        for item in channel.findall("item"):
            guid = (item.findtext("guid") or item.findtext("link") or "").strip()
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip() or None
            description = _strip_html(item.findtext("description") or "")
            published = _parse_datetime(item.findtext("pubDate"))
            if not guid:
                guid = hashlib.sha256(f"{title}|{link}".encode()).hexdigest()[:16]
            entries.append({
                "id": guid,
                "title": title,
                "description": description,
                "link": link,
                "published": published,
                "feed_title": feed_title,
            })
        return entries
