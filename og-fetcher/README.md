# OG Fetcher

Fetch Open Graph metadata from URLs using a headless browser.

This project is developed with AI assistance.

## Features

- Extracts `og:title`, `og:description`, `og:site_name` from any URL
- Handles JavaScript-rendered pages (Threads, Facebook, Instagram, etc.)
- Configurable timeout and retry settings
- Both CLI and library interfaces
- Structured error handling with status codes

## Installation

```bash
cd og-fetcher
uv sync
uv run playwright install chromium
```

## CLI Usage

```bash
# Basic usage
uv run python og_fetcher.py "https://example.com"

# JSON output (for scripting)
uv run python og_fetcher.py "https://example.com" --json

# Custom timeout and retries
uv run python og_fetcher.py "https://example.com" --timeout 15000 --retries 2

# Help
uv run python og_fetcher.py -h
```

### Output Formats

**Human-readable (default):**
```
Status: success
Title: Example Domain
Description: This domain is for use in illustrative examples.
Site: Example
```

**JSON (`--json`):**
```json
{
  "url": "https://example.com",
  "status": "success",
  "title": "Example Domain",
  "description": "This domain is for use in illustrative examples.",
  "site_name": "Example"
}
```

### Status Codes

| Status | Meaning | Exit Code |
|--------|---------|-----------|
| `success` | OG tags found and extracted | 0 |
| `no_og` | Page loaded but no OG tags present | 1 |
| `timeout` | Page load timed out | 1 |
| `failed` | Other error (network, invalid URL, etc.) | 1 |

## Library Usage

### Single URL (convenience method)

```python
from og_fetcher import OGFetcher

result = OGFetcher.fetch_one("https://example.com")
print(result.status)  # 'success'
print(result.title)   # 'Example Domain'
```

### Multiple URLs (browser reuse)

```python
from og_fetcher import OGFetcher

urls = [
    "https://threads.com/@zuck",
    "https://facebook.com/post/123",
    "https://youtube.com/watch?v=dQw4w9WgXcQ",
]

with OGFetcher(timeout=15000, retries=2) as fetcher:
    for url in urls:
        result = fetcher.fetch(url)
        print(f"{result.status}: {result.title}")
```

### OGResult Fields

```python
@dataclass
class OGResult:
    url: str           # Original URL
    status: str        # 'success' | 'no_og' | 'timeout' | 'failed'
    title: str | None
    description: str | None
    site_name: str | None
    error: str | None  # Error message if status != 'success'
```

## Development

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=og_fetcher
```

## License

MIT
