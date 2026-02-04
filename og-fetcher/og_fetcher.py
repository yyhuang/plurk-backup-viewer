#!/usr/bin/env python3
"""
OG Fetcher - Fetch Open Graph metadata from URLs using headless browser.

Handles JavaScript-rendered pages (Threads, Facebook, etc.).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page


@dataclass
class OGResult:
    """Result of fetching OG metadata from a URL."""

    url: str
    status: str  # 'success' | 'failed' | 'timeout' | 'no_og'
    title: str | None = None
    description: str | None = None
    site_name: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class OGFetcher:
    """
    Fetch Open Graph metadata from URLs using a headless browser.

    Usage:
        # Context manager (recommended for multiple URLs)
        with OGFetcher() as fetcher:
            result1 = fetcher.fetch("https://example.com")
            result2 = fetcher.fetch("https://another.com")

        # Single fetch (convenience method)
        result = OGFetcher.fetch_one("https://example.com")
    """

    def __init__(self, timeout: int = 10000, retries: int = 3):
        """
        Initialize OGFetcher.

        Args:
            timeout: Page load timeout in milliseconds (default: 10000)
            retries: Number of retries on failure (default: 3)
        """
        self.timeout = timeout
        self.retries = retries
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> OGFetcher:
        """Launch browser for reuse across multiple fetches."""
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        """Close browser and cleanup."""
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def fetch(self, url: str) -> OGResult:
        """
        Fetch OG metadata from a URL.

        Args:
            url: URL to fetch OG metadata from

        Returns:
            OGResult with status and extracted metadata
        """
        if not self._context:
            raise RuntimeError(
                "OGFetcher must be used as context manager. "
                "Use 'with OGFetcher() as fetcher:' or OGFetcher.fetch_one()"
            )

        last_error: str | None = None

        for _attempt in range(self.retries):
            try:
                return self._fetch_once(url)
            except Exception as e:
                last_error = str(e)
                if "timeout" in last_error.lower():
                    # Don't retry on timeout - likely a slow/unresponsive site
                    return OGResult(url=url, status="timeout", error=last_error)
                # Retry on other errors
                continue

        return OGResult(url=url, status="failed", error=last_error)

    def _fetch_once(self, url: str) -> OGResult:
        """Single fetch attempt."""
        assert self._context is not None
        page: Page = self._context.new_page()
        try:
            page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")

            # Extract OG tags
            og_data = page.evaluate(
                """() => {
                const tags = document.querySelectorAll('meta[property^="og:"]');
                const result = {};
                tags.forEach(tag => {
                    const property = tag.getAttribute('property');
                    const content = tag.getAttribute('content');
                    if (property && content) {
                        const key = property.replace('og:', '');
                        result[key] = content;
                    }
                });
                return result;
            }"""
            )

            if not og_data:
                return OGResult(url=url, status="no_og")

            return OGResult(
                url=url,
                status="success",
                title=og_data.get("title"),
                description=og_data.get("description"),
                site_name=og_data.get("site_name"),
            )
        finally:
            page.close()

    @classmethod
    def fetch_one(
        cls, url: str, timeout: int = 10000, retries: int = 3
    ) -> OGResult:
        """
        Convenience method to fetch a single URL.

        Creates a new browser instance, fetches the URL, and closes.
        For multiple URLs, use the context manager instead.

        Args:
            url: URL to fetch OG metadata from
            timeout: Page load timeout in milliseconds
            retries: Number of retries on failure

        Returns:
            OGResult with status and extracted metadata
        """
        with cls(timeout=timeout, retries=retries) as fetcher:
            return fetcher.fetch(url)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch Open Graph metadata from a URL using headless browser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "https://example.com"
  %(prog)s "https://threads.com/@zuck" --json
  %(prog)s "https://facebook.com/post/123" --timeout 15000 --retries 2

Status codes:
  success  - OG tags found and extracted
  no_og    - Page loaded but no OG tags present
  timeout  - Page load timed out
  failed   - Other error (network, invalid URL, etc.)
""",
    )
    parser.add_argument("url", metavar="URL", help="URL to fetch OG metadata from")
    parser.add_argument(
        "--timeout",
        type=int,
        default=10000,
        metavar="MS",
        help="Page load timeout in milliseconds (default: 10000)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        metavar="N",
        help="Number of retries on failure (default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (default: human-readable)",
    )

    args = parser.parse_args()

    result = OGFetcher.fetch_one(
        url=args.url,
        timeout=args.timeout,
        retries=args.retries,
    )

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"Status: {result.status}")
        if result.title:
            print(f"Title: {result.title}")
        if result.description:
            print(f"Description: {result.description}")
        if result.site_name:
            print(f"Site: {result.site_name}")
        if result.error:
            print(f"Error: {result.error}")

    # Exit with non-zero status on failure
    sys.exit(0 if result.status == "success" else 1)


if __name__ == "__main__":
    main()
