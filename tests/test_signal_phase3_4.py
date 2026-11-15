"""Phase 3–4: RSS connector, API, security, runtime integration tests."""

from __future__ import annotations

import textwrap
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app
from engine.core.types import Prospect
from engine.security.safe_fetch import SafeFetchResult, is_safe_fetch_url
from engine.signals.connectors.base import ConnectorCursor
from engine.signals.connectors.rss import RSSSignalConnector
from engine.signals.extraction import extract_signal_candidate
from engine.signals.prioritization import sort_prospects_by_priority
from engine.signals.repository import SignalRepository
from engine import open_storage


SAMPLE_RSS = textwrap.dedent(
    """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <title>Tech News</title>
      <item>
        <title>Acme Corp raises $10M Series B funding</title>
        <link>https://acme.com/news/series-b</link>
        <description>Acme Corp announced a Series B round.</description>
        <pubDate>Mon, 01 Sep 2026 12:00:00 GMT</pubDate>
        <guid>acme-series-b-001</guid>
      </item>
      <item>
        <title>Weather report for today</title>
        <link>https://example.com/weather</link>
        <description>Sunny skies expected.</description>
        <guid>weather-001</guid>
      </item>
    </channel></rss>"""
).strip()


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path / 'engine.db'}")


def _repo(storage) -> SignalRepository:
    store, _, _ = storage
    return SignalRepository(store._holder.engine)


class TestSSRFDefense:
    def test_blocks_localhost(self):
        assert not is_safe_fetch_url("http://127.0.0.1/feed.xml")
        assert not is_safe_fetch_url("http://localhost/rss")

    def test_allows_public_https_when_dns_resolves(self):
        from unittest.mock import patch
        with patch("engine.security.safe_fetch.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            assert is_safe_fetch_url("https://example.com/feed.xml")


class TestRSSParsing:
    def test_parses_rss_and_extracts_funding_signal(self):
        entries = RSSSignalConnector(source_id="s", feed_url="https://example.com/f")._parse_feed(
            SAMPLE_RSS.encode()
        )
        assert len(entries) == 2
        candidate = extract_signal_candidate(
            title=entries[0]["title"],
            description=entries[0]["description"],
            link=entries[0]["link"],
        )
        assert candidate is not None
        assert candidate.signal_type == "funding_round"
        assert candidate.company_domain == "acme.com"

    def test_malformed_xml_raises(self):
        with pytest.raises(Exception):
            RSSSignalConnector(source_id="s", feed_url="https://example.com/f")._parse_feed(
                b"<rss><unclosed>"
            )

    @patch("engine.signals.connectors.rss.is_safe_fetch_url", return_value=True)
    @patch("engine.signals.connectors.rss.safe_fetch")
    def test_fetch_returns_no_fake_events_on_http_error(self, mock_fetch, _safe):
        mock_fetch.return_value = SafeFetchResult(
            url="https://example.com/feed.xml", status_code=404, content=b"", content_type="",
        )
        connector = RSSSignalConnector(source_id="src", feed_url="https://example.com/feed.xml")
        events, cursor = connector.fetch_events(tenant_id="t-1", cursor=ConnectorCursor())
        assert events == []
        assert cursor.error_state is not None

    @patch("engine.signals.connectors.rss.is_safe_fetch_url", return_value=True)
    @patch("engine.signals.connectors.rss.safe_fetch")
    def test_duplicate_items_deduplicated_via_cursor(self, mock_fetch, _safe):
        mock_fetch.return_value = SafeFetchResult(
            url="https://example.com/feed.xml",
            status_code=200,
            content=SAMPLE_RSS.encode(),
            content_type="application/rss+xml",
        )
        connector = RSSSignalConnector(source_id="src", feed_url="https://example.com/feed.xml")
        events1, c1 = connector.fetch_events(tenant_id="t-1", cursor=ConnectorCursor())
        assert len(events1) == 1
        events2, _ = connector.fetch_events(tenant_id="t-1", cursor=c1)
        assert len(events2) == 0


class TestCrossTenantConnectorSecurity:
    def test_cannot_overwrite_another_tenants_source(self, storage):
        repo = _repo(storage)
        repo.save_source(
            source_id="src-shared",
            tenant_id="tenant-a",
            connector_kind="rss",
            name="A Feed",
            config={"feed_url": "https://example.com/a.xml"},
        )
        with pytest.raises(PermissionError):
            repo.save_source(
                source_id="src-shared",
                tenant_id="tenant-b",
                connector_kind="rss",
                name="Hijack",
                config={"feed_url": "https://evil.com/feed.xml"},
            )

    def test_connector_state_is_tenant_scoped(self, storage):
        repo = _repo(storage)
        repo.save_source(
            source_id="src-a", tenant_id="tenant-a", connector_kind="manual", name="A",
        )
        repo.save_connector_state(
            "src-a", "tenant-a", ConnectorCursor(last_cursor="abc", error_state="ok"),
        )
        state_b = repo.get_connector_state("src-a", tenant_id="tenant-b")
        assert state_b.last_cursor is None


class TestSignalsAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUTOREACH_SIGNALS_ENABLED", "1")
        app = create_app(db_url=f"sqlite:///{tmp_path / 'api.db'}")
        return TestClient(app, raise_server_exceptions=True)

    def _auth(self, client):
        r = client.post("/api/auth/signup", json={
            "email": "signals@co.com", "password": "Password1!", "company_name": "Sig Co",
        })
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_catalog_from_registry(self, client):
        h = self._auth(client)
        r = client.get("/api/signals/catalog", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == "1.0.0"
        assert body["count"] == 18

    def test_create_rss_source_blocks_ssrf_url(self, client):
        h = self._auth(client)
        r = client.post("/api/signals/sources", json={
            "connector_kind": "rss",
            "name": "Bad",
            "feed_url": "http://127.0.0.1/feed.xml",
        }, headers=h)
        assert r.status_code == 400

    def test_cross_tenant_source_access_denied(self, client):
        owner = self._auth(client)
        r = client.post("/api/signals/sources", json={
            "connector_kind": "manual", "name": "Manual",
        }, headers=owner)
        source_id = r.json()["source_id"]
        intruder_r = client.post("/api/auth/signup", json={
            "email": "intruder@co.com", "password": "Password1!", "company_name": "X",
        })
        intruder_h = {"Authorization": f"Bearer {intruder_r.json()['access_token']}"}
        r2 = client.get(f"/api/signals/sources/{source_id}/health", headers=intruder_h)
        assert r2.status_code == 404


class TestRuntimePrioritization:
    def test_higher_priority_prospect_sorted_first(self):
        low = Prospect(
            id="p-low", engagement_id="e1", email="a@l.com",
            research={"priority_score": 20, "signal_stack": {"score": 20}},
        )
        high = Prospect(
            id="p-high", engagement_id="e1", email="b@h.com",
            research={"priority_score": 90, "signal_stack": {"score": 90}},
        )
        ordered = sort_prospects_by_priority([low, high])
        assert ordered[0].id == "p-high"


class TestLiveRSSFeed:
    @pytest.mark.integration
    def test_live_w3c_blog_atom_feed(self):
        feed_url = "https://www.w3.org/blog/news/feed/atom/"
        if not is_safe_fetch_url(feed_url):
            pytest.skip("SSRF guard blocked feed URL")
        connector = RSSSignalConnector(source_id="live", feed_url=feed_url)
        events, cursor = connector.fetch_events(
            tenant_id="dev-tenant", cursor=ConnectorCursor(), limit=10,
        )
        assert cursor.error_state is None
        assert isinstance(events, list)
