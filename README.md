# Plurk Backup Viewer

English | [繁體中文](README.zh-TW.md)

Enhanced viewer for Plurk backup data with full-text search capabilities.

## Features

- **Landing page** with profile card and navigation
- **Full-text search** across all plurks and responses (FTS5 + LIKE fallback)
- **Link search** with Open Graph metadata (search by URL, title, description)
- **Modal popups** to view plurk details and responses
- **Incremental import** - add new backup exports without rebuilding
- **Web admin interface** - upload backup, initialize database, and manage link metadata from browser

## Quick Start

### Option A: Docker (recommended)

No Python setup required. Includes web admin for uploading backups.

```bash
# 1. Clone and start
git clone https://github.com/user/plurk-backup-viewer
cd plurk-backup-viewer
docker compose up

# 2. Open admin interface
open http://localhost:8001

# 3. Upload your backup .zip and click "Build Database"
# 4. (Optional) Extract and fetch link metadata from the admin page
# 5. Search is live at http://localhost:8000
```

### Option B: Local Setup

Prerequisites: Python 3.11+, [uv](https://github.com/astral-sh/uv)

```bash
# 1. Extract your Plurk backup
cd ~/my-plurk
unzip your-backup.zip
# This creates a directory like: username-backup/

# 2. Clone this repo
git clone https://github.com/user/plurk-backup-viewer
cd plurk-backup-viewer/tools
uv sync

# 3. Initialize database
uv run plurk-tools init ../username-backup

# 4. Start the server
uv run plurk-tools serve
# Open http://localhost:8000

# 5. (Optional) Add link to enhanced viewer in original index.html
uv run plurk-tools patch
```

## Directory Structure After Setup

```
~/my-plurk/
├── username-backup/           # Your Plurk export (untouched)
│   ├── index.html          # Original Plurk viewer
│   ├── static/
│   └── data/
│
└── plurk-backup-viewer/       # This repo
    ├── viewer/             # HTML templates (static assets)
    │   ├── landing.html    # Enhanced landing page
    │   ├── search.html     # Search interface
    │   └── admin.html      # Admin interface
    ├── data/               # User data (auto-created)
    │   ├── plurks.db       # Search database
    │   └── config.json     # Points to backup
    └── tools/              # CLI tools
```

## Commands

All commands are run from the `tools/` directory.

### Initialize Database

```bash
uv run plurk-tools init <backup_path>
```

Creates:
- `data/plurks.db` - SQLite database with all plurks and responses
- `data/config.json` - Points to your backup directory

### Start Server

```bash
uv run plurk-tools serve [--port 8000]
```

Starts a local server that serves both the enhanced viewer and your backup data. Admin interface is available at `http://localhost:8001` by default. Use `--admin-port 0` to disable.

### Patch Original Viewer (Optional)

```bash
uv run plurk-tools patch
```

Adds an "Enhanced Viewer" link to the original Plurk backup's `index.html`. Run this after each new backup extraction.

### Link Metadata (Optional)

Extract URLs from your plurks and fetch Open Graph metadata for link search:

```bash
# Extract links from a specific month
uv run plurk-tools links extract --month 201810

# Fetch OG metadata for pending links
uv run plurk-tools links fetch --limit 100

# Check status
uv run plurk-tools links status
```

## Docker Setup

The Docker setup runs a single container with the search server (port 8000) and admin interface (port 8001).

```bash
# Build and start
docker compose up

# With Cloudflare Tunnel (optional)
TUNNEL_TOKEN=your-token docker compose up
```

**Volumes:**
- `viewer/` is mounted read-only (static HTML templates)
- `data/` is mounted read-write (database, config, uploaded backups)

**Ports:**
- `8000` - Search interface (can be tunneled)
- `8001` - Admin interface (local only)

## Updating Your Backup

When you export a new backup from Plurk:

1. Extract the new backup (can overwrite the old one)
2. Run `plurk-tools init` again - it will incrementally add new plurks
3. Run `plurk-tools patch` again - the new extraction overwrites `index.html`

```bash
# Re-run init to import new data
uv run plurk-tools init ../username-backup

# Re-run patch (new extraction overwrites index.html)
uv run plurk-tools patch
```

For Docker: use the admin interface to re-upload and re-initialize.

## CJK Search (Optional)

The default FTS5 tokenizer (`unicode61`) works for basic CJK search, but for better Chinese/Japanese/Korean word segmentation, you can install the [fts5-icu-tokenizer](https://github.com/cwt/fts5-icu-tokenizer) extension.

1. Build `libfts5_icu.dylib` (macOS) or `libfts5_icu.so` (Linux) from the repo
2. Place it in `viewer/lib/`
3. Rebuild the FTS5 indexes:

```bash
uv run plurk-tools reindex
```

The extension is auto-detected from `viewer/lib/` by both `init` and `reindex`.

| Tokenizer | CJK Behavior |
|-----------|-------------|
| `unicode61` (default) | Character-level tokenization, works for most searches |
| `icu` (with extension) | Proper word segmentation for Chinese, Japanese, Korean |

The Docker image includes the ICU extension pre-built.

## How It Works

- **Database**: SQLite with FTS5 full-text search index, stored in `data/`
- **Dual-directory routing**: Server combines viewer files with your backup data
- **Minimal modifications**: Only `patch` command modifies `index.html`, other backup files are untouched
- **Admin interface**: Web-based setup (upload zip, build database, extract/fetch link metadata)

## License

MIT
