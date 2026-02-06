# Plurk Backup Viewer

English | [繁體中文](README.zh-TW.md)

Enhanced viewer for Plurk backup data with full-text search capabilities.

## Features

- **Landing page** with profile card and navigation
- **Full-text search** across all plurks and responses (FTS5 + LIKE fallback)
- **Link search** with Open Graph metadata (search by URL, title, description)
- **Modal popups** to view plurk details and responses
- **Incremental import** - add new backup exports without rebuilding

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Python package manager)

## Quick Start

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
└── plurk-backup-viewer/       # This repo (keep for serving)
    ├── viewer/             # HTML + database
    │   ├── landing.html    # Enhanced landing page
    │   ├── search.html     # Search interface
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
- `viewer/plurks.db` - SQLite database with all plurks and responses
- `viewer/config.json` - Points to your backup directory

### Start Server

```bash
uv run plurk-tools serve [--port 8000]
```

Starts a local server that serves both the enhanced viewer and your backup data.

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

## How It Works

- **Database**: SQLite with FTS5 full-text search index
- **Dual-directory routing**: Server combines viewer files with your backup data
- **Minimal modifications**: Only `patch` command modifies `index.html`, other backup files are untouched

## License

MIT
