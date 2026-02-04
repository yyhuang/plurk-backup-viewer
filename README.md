# Plurk Backup Viewer

English | [繁體中文](README.zh-TW.md)

Enhanced viewer for Plurk backup data with full-text search capabilities.

## Features

- **Landing page** with profile card and navigation
- **Full-text search** across all plurks and responses (FTS5 + LIKE fallback)
- **Link search** with Open Graph metadata (search by link title/description)
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

# 3. Initialize viewer (creates sibling directory)
uv run plurk-tools init ../username-backup
# Output: Created viewer at ~/my-plurk/username-viewer/
#         Database: X plurks, Y responses

# 4. Start the server
uv run plurk-tools serve ../username-viewer
# Open http://localhost:8000
```

## Directory Structure After Setup

```
~/my-plurk/
├── username-backup/           # Your Plurk export (untouched)
│   ├── index.html          # Original Plurk viewer
│   ├── static/
│   └── data/
│
├── username-viewer/           # Created by plurk-tools init
│   ├── landing.html        # Enhanced landing page
│   ├── search.html         # Search interface
│   ├── static/sql-wasm.*   # SQLite for browser
│   ├── plurks.db           # Search database
│   └── config.json         # Points to backup directory
│
└── plurk-backup-viewer/    # This repo (can delete after setup)
```

## Commands

All commands are run from the `tools/` directory.

### Initialize Viewer

```bash
uv run plurk-tools init <backup_path> [--viewer <viewer_path>]
```

Creates a viewer directory with:
- HTML templates for enhanced viewing
- SQLite database with all plurks and responses
- Config file pointing to your backup

Default viewer path: `<backup_name>-viewer` (sibling to backup)

### Start Server

```bash
uv run plurk-tools serve <viewer_path> [--port 8000]
```

Starts a local server that serves both the enhanced viewer and your backup data.

### Link Metadata (Optional)

Extract URLs from your plurks and fetch Open Graph metadata for link search:

```bash
# Extract links from a specific month
uv run plurk-tools links extract <viewer_path> --month 201810

# Fetch OG metadata for pending links
uv run plurk-tools links fetch <viewer_path> --limit 100

# Check status
uv run plurk-tools links status <viewer_path>
```

## Updating Your Backup

When you export a new backup from Plurk:

1. Extract the new backup (can overwrite the old one)
2. Run `plurk-tools init` again - it will incrementally add new plurks

```bash
# Re-run init to import new data
uv run plurk-tools init ../username-backup
# Output: Added X new plurks, Y new responses
```

## How It Works

- **Database**: SQLite with FTS5 full-text search index
- **Dual-directory routing**: Server combines viewer files with your backup data
- **No modifications**: Your original backup files are never modified

## License

MIT
