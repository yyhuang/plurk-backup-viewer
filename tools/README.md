# Plurk Backup Tools

This project is developed with AI assistance.

Command-line tools for managing Plurk backup data with SQLite full-text search.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Setup

```bash
cd tools
uv sync
```

## Quick Start

```bash
# 1. Initialize viewer from backup (creates username-viewer/ directory)
uv run plurk-tools init ../username-backup

# 2. Start development server
uv run plurk-tools serve ../username-viewer

# 3. Open in browser
open http://localhost:8000/
```

## Commands

### plurk-tools init

Initialize a viewer from a Plurk backup. Creates a viewer directory with HTML templates and builds the SQLite database.

```bash
uv run plurk-tools init <backup_path> [--viewer <viewer_path>]

# Example (creates ../username-viewer/)
uv run plurk-tools init ../username-backup

# Custom viewer path
uv run plurk-tools init ../username-backup --viewer /path/to/viewer
```

**What it does:**
1. Creates viewer directory with HTML templates (landing.html, search.html)
2. Copies sql-wasm.* files for browser SQLite
3. Creates config.json pointing to backup directory
4. Builds plurks.db database from backup data

**Re-running for incremental import:**
```bash
# After adding new backup data, re-run init
uv run plurk-tools init ../username-backup
# Adds new records, skips existing (INSERT OR IGNORE)
```

### plurk-tools serve

Development HTTP server with dual-directory routing and cache disabled.

```bash
uv run plurk-tools serve <viewer_path> [--port PORT]

# Example
uv run plurk-tools serve ../username-viewer
uv run plurk-tools serve ../username-viewer --port 3000
```

**Routing:**
| Request Path | Served From |
|--------------|-------------|
| `/data/*` | backup directory |
| `/index.html` | backup directory (original viewer) |
| `/static/backup.*`, `/static/jquery*`, `/static/icons.png` | backup directory |
| `/landing.html`, `/search.html`, `/plurks.db` | viewer directory |
| `/static/sql-wasm.*` | viewer directory |

### plurk-tools links

Manage link metadata: extract URLs and fetch Open Graph metadata.

```bash
# Extract URLs from a specific month
uv run plurk-tools links extract ../username-viewer --month 201810

# Fetch OG metadata for pending URLs
uv run plurk-tools links fetch ../username-viewer --limit 50

# Check database status
uv run plurk-tools links status ../username-viewer
```

**Subcommands:**

| Command | Description |
|---------|-------------|
| `extract` | Extract URLs from backup files for a specific month |
| `fetch` | Fetch OG metadata for pending URLs using headless browser |
| `status` | Show counts by status (pending, success, failed, etc.) |

**Options:**

| Subcommand | Required Args | Optional Args |
|------------|---------------|---------------|
| `extract` | `viewer_path`, `--month` | `--fetch-previews` |
| `fetch` | `viewer_path` | `--limit`, `--timeout`, `--retries` |
| `status` | `viewer_path` | |

**Fetch options:**
- `--limit N` - Max URLs to fetch (default: 50, 0=all)
- `--timeout MS` - Page load timeout (default: 10000)
- `--retries N` - Retry count (default: 3)

## Directory Structure

After running `plurk-tools init`:

```
~/my-plurk/
├── username-backup/           # Original Plurk export (untouched)
│   ├── index.html          # Original backup viewer
│   ├── static/backup.*, jquery, icons
│   └── data/
│       ├── info.js, user.js, indexes.js
│       ├── plurks/         # Monthly plurk files
│       └── responses/      # Response files
│
└── username-viewer/           # Created by plurk-tools init
    ├── landing.html        # Landing page
    ├── search.html         # Search interface
    ├── static/sql-wasm.*   # Browser SQLite
    ├── plurks.db           # Generated database
    └── config.json         # Points to backup directory
```

## Running Tests

```bash
uv run pytest
```

## Web Interface

After initialization, open `http://localhost:8000/` to access:

- **Landing page** - Navigation to browse/search
- **Timeline browser** - Browse plurks by month (original index.html)
- **Search** - Full-text search with FTS5/LIKE modes
- **Link search** - Search by link title/description (OG metadata)

## Database Schema

### plurks table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key (plurk ID) |
| base_id | TEXT | Base36 encoded ID (used in URLs like plurk.com/p/{base_id}) |
| content_raw | TEXT | Plain text content (HTML stripped) |
| posted | TEXT | Timestamp |
| response_count | INTEGER | Number of responses |
| qualifier | TEXT | Verb qualifier (says, thinks, loves, etc.) |

### responses table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key (response ID) |
| base_id | TEXT | Parent plurk's base_id |
| content_raw | TEXT | Plain text content |
| posted | TEXT | Timestamp |
| user_id | INTEGER | Responder's user ID |
| user_nick | TEXT | Responder's nickname |
| user_display | TEXT | Responder's display name |

### link_metadata table

| Column | Type | Description |
|--------|------|-------------|
| url | TEXT | Primary key (the URL) |
| og_title | TEXT | Open Graph title |
| og_description | TEXT | Open Graph description |
| og_site_name | TEXT | Open Graph site name |
| sources | JSON | `{"plurk_ids": [...], "response_ids": [...]}` |
| status | TEXT | `pending`, `image`, `success`, `failed`, `no_og`, or `timeout` |
| fetched_at | TEXT | Timestamp when OG was fetched |

### FTS5 virtual tables

- `plurks_fts` - Full-text index on `plurks.content_raw`
- `responses_fts` - Full-text index on `responses.content_raw`
- `link_metadata_fts` - Full-text index on `og_title`, `og_description`, `og_site_name`

All use `unicode61` tokenizer for Chinese character support.
