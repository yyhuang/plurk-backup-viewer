# OG Fetcher

This project is developed with AI assistance.

## Overview

A standalone Python tool to fetch Open Graph metadata from URLs using a headless browser. Handles JavaScript-rendered pages (Threads, Facebook, etc.).

## Project Status

**Phase: Implemented**

### Completed
- `OGFetcher` class with context manager for browser reuse
- `OGResult` dataclass with structured status codes
- CLI with `--help`, `--json`, `--timeout`, `--retries`
- Unit tests (4 passing)
- README.md documentation

### Decided
- Class-based design (`OGFetcher`) for browser reuse
- Playwright for browser automation (handles JS-rendered pages)
- Structured result with status codes for error handling
- CLI with `--help` support
- Configurable timeout and retries with sensible defaults

### Open Questions

| # | Question | Options | Decision |
|---|----------|---------|----------|
| 1 | User-Agent | Default / Custom (some sites block headless browsers) | TBD |
| 2 | Rate limiting | None / Fixed delay / Per-domain delay | TBD |
| 3 | Headless mode | Always headless / Option for headed (debugging) | TBD |
| 4 | Facebook Graph API | Playwright only / Hybrid (API for Meta URLs, Playwright for others) | **Playwright only** for now - no credentials needed, works universally |

## Directory Structure

```
og-fetcher/
├── CLAUDE.md           # This file
├── README.md           # User documentation
├── pyproject.toml      # Dependencies
├── og_fetcher.py       # OGFetcher class + CLI
└── tests/
    └── test_og_fetcher.py
```

## Development Commands

```bash
# Setup
cd og-fetcher
uv sync
uv run playwright install chromium

# Run CLI
uv run python og_fetcher.py "https://example.com"
uv run python og_fetcher.py "https://example.com" --json
uv run python og_fetcher.py -h

# Run tests
uv run pytest
```

## Design

### OGResult (dataclass)

```python
@dataclass
class OGResult:
    url: str
    status: str        # 'success' | 'failed' | 'timeout' | 'no_og'
    title: str | None
    description: str | None
    site_name: str | None
    error: str | None  # Error message if status != 'success'
```

### Status Codes

| Status | Meaning |
|--------|---------|
| `success` | OG tags found and extracted |
| `no_og` | Page loaded but no OG tags present |
| `timeout` | Page load timed out |
| `failed` | Other error (network, invalid URL, etc.) |

### OGFetcher Class

```python
class OGFetcher:
    def __init__(self, timeout: int = 10000, retries: int = 3):
        ...

    def __enter__(self) -> 'OGFetcher':
        # Launch browser

    def __exit__(self, ...):
        # Close browser

    def fetch(self, url: str) -> OGResult:
        # Fetch OG metadata from URL
```

### Usage Patterns

```python
# Library use - browser reused across calls
with OGFetcher(timeout=15000, retries=2) as fetcher:
    result1 = fetcher.fetch("https://threads.com/...")
    result2 = fetcher.fetch("https://facebook.com/...")

# CLI use - one-shot
# uv run python og_fetcher.py "https://example.com" --json
```

### CLI Interface

```
usage: og_fetcher.py [-h] [--timeout MS] [--retries N] [--json] URL

Fetch Open Graph metadata from a URL using headless browser.

positional arguments:
  URL              URL to fetch OG metadata from

options:
  -h, --help       show this help message and exit
  --timeout MS     Page load timeout in milliseconds (default: 10000)
  --retries N      Number of retries on failure (default: 3)
  --json           Output as JSON (default: human-readable)
```

## Technical Notes

### Facebook Graph API Alternative

Facebook provides an API endpoint to fetch OG metadata without browser automation:

```
POST https://graph.facebook.com/v18.0/
  ?id={URL}
  &scrape=true
  &access_token={APP_ID}|{APP_SECRET}
```

**Response includes:** `og:title`, `og:description`, `og:image`, `og:type`, etc.

| Approach | Pros | Cons |
|----------|------|------|
| **Graph API** | Fast, reliable, no browser needed | Requires FB App credentials, rate limited, FB caches results |
| **Playwright** | No credentials needed, works on any site | Slower, heavier, needs browser |

**Decision:** Use Playwright for now (general-purpose, no credentials needed). Could add optional `--facebook-token` flag later for hybrid approach if needed.

### Why Playwright (not HTTP requests)?

- JavaScript-rendered pages (Threads, Facebook) don't return OG tags via simple HTTP fetch
- OG tags are injected by client-side JavaScript
- Headless browser executes JS and sees final DOM

### OG Tags Extracted

| Tag | Field | Notes |
|-----|-------|-------|
| `og:title` | `title` | Most useful for search |
| `og:description` | `description` | Most useful for search |
| `og:site_name` | `site_name` | Source platform |
| `og:image` | (skipped) | Not useful for text search |

### Browser Extraction Code

```javascript
Array.from(document.querySelectorAll('meta[property^="og:"]'))
  .map(m => ({
    property: m.getAttribute('property'),
    content: m.getAttribute('content')
  }))
```

## Dependencies

```toml
[project]
name = "og-fetcher"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "playwright",
]

[project.optional-dependencies]
dev = [
    "pytest",
]
```

## Original Context

This tool was created for the Plurk Backup Viewer project to enable searching by link content (OG metadata). The plurk backup only stores raw URLs, but users want to search by link titles/descriptions.

See `/Users/yyhuang/claude/plurk/CLAUDE.md` for the parent project context.
