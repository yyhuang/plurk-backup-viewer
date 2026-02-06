"""Init command - initialize database from Plurk backup.

This command:
1. Creates config.json pointing to the backup directory
2. Builds the SQLite database from backup data

Database and config are stored in the viewer/ directory.
"""

import json
import sys
from pathlib import Path

from database import create_schema, import_plurks, import_responses
from utils import (
    calculate_scan_range,
    filter_plurk_files,
    filter_response_files,
    get_base_ids_from_plurks,
    validate_backup_dir,
)


# Paths relative to this file
TOOL_ROOT = Path(__file__).parent.parent
VIEWER_DIR = TOOL_ROOT / "viewer"


def create_config(backup_path: Path) -> None:
    """Create config.json in viewer directory."""
    config = {
        "backup_path": str(backup_path.resolve()),
    }
    config_path = VIEWER_DIR / "config.json"
    config_path.write_text(json.dumps(config, indent=2))


def build_database(backup_path: Path, db_path: Path) -> tuple[int, int]:
    """Build SQLite database from backup.

    Returns:
        Tuple of (plurk_count, response_count)
    """
    import sqlite3
    from datetime import date

    plurks_dir = backup_path / "data" / "plurks"
    responses_dir = backup_path / "data" / "responses"

    # Check if database exists (incremental update)
    is_incremental = db_path.exists()

    if is_incremental:
        print(f"Updating existing database: {db_path}")
        conn = sqlite3.connect(db_path)
        scan_start, scan_end = calculate_scan_range(conn, date.today())
        if scan_start:
            print(f"Scanning files from {scan_start} to {scan_end}")
        else:
            print("Database is empty, importing all files")
    else:
        print(f"Creating new database: {db_path}")
        conn = sqlite3.connect(db_path)
        create_schema(conn)
        scan_start, scan_end = None, None

    # Filter and import plurks
    plurk_files = filter_plurk_files(plurks_dir, scan_start, scan_end)
    print(f"Processing {len(plurk_files)} plurk files...")
    plurk_new, plurk_skipped = import_plurks(conn, plurk_files)

    # Filter and import responses
    base_ids = get_base_ids_from_plurks(plurk_files)
    response_files = filter_response_files(responses_dir, base_ids)
    print(f"Processing {len(response_files)} response files...")
    response_new, response_skipped = import_responses(conn, response_files)

    conn.commit()

    # Get total counts
    plurk_count = conn.execute("SELECT COUNT(*) FROM plurks").fetchone()[0]
    response_count = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]

    conn.close()

    if is_incremental:
        print(f"Plurks: {plurk_new} new, {plurk_skipped} skipped")
        print(f"Responses: {response_new} new, {response_skipped} skipped")
    else:
        print(f"Imported {plurk_new} plurks, {response_new} responses")

    return plurk_count, response_count


def cmd_init(backup_path: Path) -> int:
    """Initialize database from Plurk backup.

    Args:
        backup_path: Path to backup directory

    Returns:
        Exit code (0 for success)
    """
    # Resolve paths
    backup_path = backup_path.resolve()

    # Validate backup directory
    if not validate_backup_dir(backup_path):
        print(f"Error: Invalid backup directory: {backup_path}", file=sys.stderr)
        print("Required: data/plurks/, data/responses/, data/indexes.js", file=sys.stderr)
        return 1

    print(f"Backup: {backup_path}")
    print(f"Viewer: {VIEWER_DIR}")
    print()

    # Step 1: Create config.json
    print("Creating config.json...")
    create_config(backup_path)

    # Step 2: Build database
    print("Building database...")
    db_path = VIEWER_DIR / "plurks.db"
    plurk_count, response_count = build_database(backup_path, db_path)

    print()
    print(f"Done! Database: {plurk_count:,} plurks, {response_count:,} responses")
    print()
    print("To start the server:")
    print(f"  cd {TOOL_ROOT / 'tools'}")
    print("  uv run plurk-tools serve")

    return 0
