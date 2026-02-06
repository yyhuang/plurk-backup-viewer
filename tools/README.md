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
# 1. Initialize database from backup
uv run plurk-tools init ../username-backup

# 2. Start development server
uv run plurk-tools serve

# 3. Open in browser
open http://localhost:8000/
```

## Commands

### plurk-tools init

Initialize database from a Plurk backup. Creates `plurks.db` and `config.json` in the `viewer/` directory.

```bash
uv run plurk-tools init <backup_path>

# Example
uv run plurk-tools init ../username-backup
```

**What it does:**
1. Creates `config.json` pointing to backup directory
2. Builds `plurks.db` database from backup data

**Re-running for incremental import:**
```bash
# After adding new backup data, re-run init
uv run plurk-tools init ../username-backup
# Adds new records, skips existing (INSERT OR IGNORE)
```

### plurk-tools serve

Development HTTP server with dual-directory routing and cache disabled.

```bash
uv run plurk-tools serve [--port PORT]

# Example
uv run plurk-tools serve
uv run plurk-tools serve --port 3000
```

**Routing:**
| Request Path | Served From |
|--------------|-------------|
| `/data/*` | backup directory |
| `/index.html` | backup directory (original viewer) |
| `/static/backup.*`, `/static/jquery*`, `/static/icons.png` | backup directory |
| `/landing.html`, `/search.html`, `/plurks.db` | viewer directory |
| `/static/sql-wasm.*` | viewer directory |

### plurk-tools patch

Add a link to the enhanced viewer in the backup's original `index.html`.

```bash
uv run plurk-tools patch
```

**What it does:**
- Adds an "Enhanced Viewer" button to the original Plurk backup's `index.html`
- Safe to run multiple times (detects if already patched)
- Re-run after extracting a new backup (extraction overwrites `index.html`)

### plurk-tools links

Manage link metadata: extract URLs and fetch Open Graph metadata.

```bash
# Extract URLs from a specific month
uv run plurk-tools links extract --month 201810

# Fetch OG metadata for pending URLs
uv run plurk-tools links fetch --limit 50

# Check database status
uv run plurk-tools links status
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
| `extract` | `--month` | `--fetch-previews` |
| `fetch` | | `--limit`, `--timeout`, `--retries` |
| `status` | | |

**Fetch options:**
- `--limit N` - Max URLs to fetch (default: 50, 0=all)
- `--timeout MS` - Page load timeout (default: 10000)
- `--retries N` - Retry count (default: 3)

## Directory Structure

After running `plurk-tools init`:

```
plurk-backup-viewer/           # This repo
├── viewer/                 # HTML templates + user data
│   ├── landing.html        # Landing page
│   ├── search.html         # Search interface
│   ├── static/sql-wasm.*   # Browser SQLite
│   ├── plurks.db           # Generated database (gitignored)
│   └── config.json         # Points to backup (gitignored)
└── tools/                  # CLI tools

username-backup/               # Your Plurk export (untouched)
├── index.html              # Original backup viewer
├── static/backup.*, jquery, icons
└── data/
    ├── info.js, user.js, indexes.js
    ├── plurks/             # Monthly plurk files
    └── responses/          # Response files
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
