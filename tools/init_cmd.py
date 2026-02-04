"""Init command - initialize viewer from Plurk backup.

This command:
1. Creates a viewer directory with HTML templates and static files
2. Creates config.json pointing to the backup directory
3. Builds the SQLite database from backup data
"""

import json
import shutil
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


# Path to viewer templates (relative to this file)
TOOL_ROOT = Path(__file__).parent.parent
VIEWER_TEMPLATE_DIR = TOOL_ROOT / "viewer"


def get_default_viewer_path(backup_path: Path) -> Path:
    """Calculate default viewer path from backup path.

    Examples:
        username-backup -> username-viewer (sibling)
        my-backup -> my-viewer (sibling)
        backup -> backup-viewer (sibling with suffix)
    """
    name = backup_path.name
    if name.endswith("-backup"):
        viewer_name = name[:-7] + "-viewer"  # Remove "-backup", add "-viewer"
    else:
        viewer_name = name + "-viewer"
    return backup_path.parent / viewer_name


def copy_viewer_templates(viewer_path: Path) -> None:
    """Copy viewer templates to viewer directory."""
    if not VIEWER_TEMPLATE_DIR.exists():
        raise FileNotFoundError(f"Viewer templates not found at {VIEWER_TEMPLATE_DIR}")

    # Create viewer directory
    viewer_path.mkdir(parents=True, exist_ok=True)

    # Copy HTML files
    for html_file in VIEWER_TEMPLATE_DIR.glob("*.html"):
        shutil.copy2(html_file, viewer_path / html_file.name)

    # Copy static directory
    static_src = VIEWER_TEMPLATE_DIR / "static"
    static_dst = viewer_path / "static"
    if static_src.exists():
        if static_dst.exists():
            shutil.rmtree(static_dst)
        shutil.copytree(static_src, static_dst)


def create_config(viewer_path: Path, backup_path: Path) -> None:
    """Create config.json in viewer directory."""
    config = {
        "backup_path": str(backup_path.resolve()),
    }
    config_path = viewer_path / "config.json"
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


def cmd_init(backup_path: Path, viewer_path: Path | None = None) -> int:
    """Initialize viewer from Plurk backup.

    Args:
        backup_path: Path to backup directory
        viewer_path: Optional path for viewer directory (default: auto-calculated)

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

    # Calculate viewer path if not provided
    if viewer_path is None:
        viewer_path = get_default_viewer_path(backup_path)
    else:
        viewer_path = viewer_path.resolve()

    print(f"Backup: {backup_path}")
    print(f"Viewer: {viewer_path}")
    print()

    # Step 1: Copy viewer templates
    print("Copying viewer templates...")
    try:
        copy_viewer_templates(viewer_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Step 2: Create config.json
    print("Creating config.json...")
    create_config(viewer_path, backup_path)

    # Step 3: Build database
    print("Building database...")
    db_path = viewer_path / "plurks.db"
    plurk_count, response_count = build_database(backup_path, db_path)

    print()
    print(f"Done! Viewer created at {viewer_path}")
    print(f"Database: {plurk_count:,} plurks, {response_count:,} responses")
    print()
    print("To start the server:")
    print(f"  cd {TOOL_ROOT / 'tools'}")
    print(f"  uv run plurk-tools serve {viewer_path}")

    return 0
