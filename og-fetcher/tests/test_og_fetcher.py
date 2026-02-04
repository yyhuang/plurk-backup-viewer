"""Tests for og_fetcher module."""

import pytest
from og_fetcher import OGFetcher, OGResult


class TestOGResult:
    """Tests for OGResult dataclass."""

    def test_to_dict_excludes_none(self):
        """to_dict should exclude None values."""
        result = OGResult(
            url="https://example.com",
            status="success",
            title="Example",
            description=None,
            site_name=None,
            error=None,
        )
        d = result.to_dict()
        assert d == {
            "url": "https://example.com",
            "status": "success",
            "title": "Example",
        }

    def test_to_dict_includes_all_values(self):
        """to_dict should include all non-None values."""
        result = OGResult(
            url="https://example.com",
            status="success",
            title="Example",
            description="A description",
            site_name="Example Site",
            error=None,
        )
        d = result.to_dict()
        assert d == {
            "url": "https://example.com",
            "status": "success",
            "title": "Example",
            "description": "A description",
            "site_name": "Example Site",
        }

    def test_to_dict_includes_error(self):
        """to_dict should include error when present."""
        result = OGResult(
            url="https://example.com",
            status="failed",
            error="Connection refused",
        )
        d = result.to_dict()
        assert d == {
            "url": "https://example.com",
            "status": "failed",
            "error": "Connection refused",
        }


class TestOGFetcherContextManager:
    """Tests for OGFetcher context manager behavior."""

    def test_fetch_without_context_raises(self):
        """fetch() should raise if not used as context manager."""
        fetcher = OGFetcher()
        with pytest.raises(RuntimeError, match="must be used as context manager"):
            fetcher.fetch("https://example.com")


class TestOGFetcherIntegration:
    """Integration tests that actually fetch URLs.

    These tests require network access and may be slow.
    Mark with pytest.mark.integration to skip in fast test runs.
    """

    @pytest.mark.integration
    def test_fetch_example_com(self):
        """Fetch example.com - a stable test target."""
        result = OGFetcher.fetch_one("https://example.com")
        # example.com may or may not have OG tags
        assert result.url == "https://example.com"
        assert result.status in ("success", "no_og")

    @pytest.mark.integration
    def test_fetch_invalid_url(self):
        """Fetch invalid URL should return failed status."""
        result = OGFetcher.fetch_one("https://this-domain-does-not-exist-12345.com")
        assert result.status == "failed"
        assert result.error is not None

    @pytest.mark.integration
    def test_fetch_multiple_urls_reuses_browser(self):
        """Multiple fetches should work with browser reuse."""
        urls = ["https://example.com", "https://example.org"]
        results = []

        with OGFetcher() as fetcher:
            for url in urls:
                results.append(fetcher.fetch(url))

        assert len(results) == 2
        for result in results:
            assert result.status in ("success", "no_og", "failed")
