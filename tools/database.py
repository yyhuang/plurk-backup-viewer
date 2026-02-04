"""Create or update SQLite database with FTS5 from Plurk backup."""

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

from utils import (
    calculate_scan_range,
    filter_plurk_files,
    filter_response_files,
    get_base_ids_from_plurks,
    parse_plurk_file,
    parse_response_file,
    validate_backup_dir,
)


def create_schema(conn: sqlite3.Connection) -> None:
    """Create database schema with FTS5 tables and triggers."""
    conn.executescript("""
        -- Main tables
        CREATE TABLE IF NOT EXISTS plurks (
            id INTEGER PRIMARY KEY,
            base_id TEXT,
            content_raw TEXT,
            posted TEXT,
            response_count INTEGER,
            qualifier TEXT
        );

        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY,
            base_id TEXT,
            content_raw TEXT,
            posted TEXT,
            user_id INTEGER,
            user_nick TEXT,
            user_display TEXT
        );

        -- FTS5 virtual tables for full-text search
        CREATE VIRTUAL TABLE IF NOT EXISTS plurks_fts USING fts5(
            content_raw,
            content='plurks',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS responses_fts USING fts5(
            content_raw,
            content='responses',
            content_rowid='id',
            tokenize='unicode61'
        );

        -- Triggers to keep FTS in sync with main tables
        CREATE TRIGGER IF NOT EXISTS plurks_ai AFTER INSERT ON plurks BEGIN
            INSERT INTO plurks_fts(rowid, content_raw) VALUES (new.id, new.content_raw);
        END;

        CREATE TRIGGER IF NOT EXISTS plurks_ad AFTER DELETE ON plurks BEGIN
            INSERT INTO plurks_fts(plurks_fts, rowid, content_raw) VALUES ('delete', old.id, old.content_raw);
        END;

        CREATE TRIGGER IF NOT EXISTS plurks_au AFTER UPDATE ON plurks BEGIN
            INSERT INTO plurks_fts(plurks_fts, rowid, content_raw) VALUES ('delete', old.id, old.content_raw);
            INSERT INTO plurks_fts(rowid, content_raw) VALUES (new.id, new.content_raw);
        END;

        CREATE TRIGGER IF NOT EXISTS responses_ai AFTER INSERT ON responses BEGIN
            INSERT INTO responses_fts(rowid, content_raw) VALUES (new.id, new.content_raw);
        END;

        CREATE TRIGGER IF NOT EXISTS responses_ad AFTER DELETE ON responses BEGIN
            INSERT INTO responses_fts(responses_fts, rowid, content_raw) VALUES ('delete', old.id, old.content_raw);
        END;

        CREATE TRIGGER IF NOT EXISTS responses_au AFTER UPDATE ON responses BEGIN
            INSERT INTO responses_fts(responses_fts, rowid, content_raw) VALUES ('delete', old.id, old.content_raw);
            INSERT INTO responses_fts(rowid, content_raw) VALUES (new.id, new.content_raw);
        END;
    """)


def import_plurks(
    conn: sqlite3.Connection, plurk_files: list[Path]
) -> tuple[int, int]:
    """Import plurks from file list using INSERT OR IGNORE.

    Args:
        conn: SQLite connection
        plurk_files: List of plurk JS files to import

    Returns:
        Tuple of (new_count, skipped_count)
    """
    new_count = 0
    skipped_count = 0

    for file in plurk_files:
        _, plurks = parse_plurk_file(file)
        for p in plurks:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO plurks (id, base_id, content_raw, posted, response_count, qualifier)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    p["id"],
                    p.get("base_id"),
                    p.get("content_raw"),
                    p.get("posted"),
                    p.get("response_count"),
                    p.get("qualifier"),
                ),
            )
            if cursor.rowcount == 1:
                new_count += 1
            else:
                skipped_count += 1

    return new_count, skipped_count


def import_responses(
    conn: sqlite3.Connection, response_files: list[Path]
) -> tuple[int, int]:
    """Import responses from file list using INSERT OR IGNORE.

    Args:
        conn: SQLite connection
        response_files: List of response JS files to import

    Returns:
        Tuple of (new_count, skipped_count)
    """
    new_count = 0
    skipped_count = 0

    for file in response_files:
        base_id, responses = parse_response_file(file)
        for r in responses:
            user = r.get("user", {})
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO responses (id, base_id, content_raw, posted, user_id, user_nick, user_display)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["id"],
                    base_id,
                    r.get("content_raw"),
                    r.get("posted"),
                    user.get("id"),
                    user.get("nick_name"),
                    user.get("display_name"),
                ),
            )
            if cursor.rowcount == 1:
                new_count += 1
            else:
                skipped_count += 1

    return new_count, skipped_count


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create or update SQLite database from Plurk backup."
    )
    parser.add_argument(
        "backup_path",
        type=Path,
        help="Path to backup directory (e.g., username-backup)",
    )
    parser.add_argument(
        "output_db",
        type=Path,
        help="Path for output database (e.g., plurks.db)",
    )
    args = parser.parse_args()

    # Validate backup directory
    if not validate_backup_dir(args.backup_path):
        print(f"Error: Invalid backup directory: {args.backup_path}", file=sys.stderr)
        print("Required: data/plurks/, data/responses/, data/indexes.js", file=sys.stderr)
        return 1

    plurks_dir = args.backup_path / "data" / "plurks"
    responses_dir = args.backup_path / "data" / "responses"

    # Check if this is a fresh import or incremental update
    is_incremental = args.output_db.exists()

    if is_incremental:
        print(f"Updating existing database: {args.output_db}")
        conn = sqlite3.connect(args.output_db)

        # Calculate scan range based on latest data
        scan_start, scan_end = calculate_scan_range(conn, date.today())
        if scan_start:
            print(f"Scanning files from {scan_start} to {scan_end}")
        else:
            print("Database is empty, importing all files")
    else:
        print(f"Creating new database: {args.output_db}")
        conn = sqlite3.connect(args.output_db)
        create_schema(conn)
        scan_start, scan_end = None, None

    # Filter plurk files based on scan range
    plurk_files = filter_plurk_files(plurks_dir, scan_start, scan_end)
    print(f"Processing {len(plurk_files)} plurk files...")

    # Import plurks
    plurk_new, plurk_skipped = import_plurks(conn, plurk_files)

    # Get base_ids for response filtering
    base_ids = get_base_ids_from_plurks(plurk_files)

    # Filter response files
    response_files = filter_response_files(responses_dir, base_ids)
    print(f"Processing {len(response_files)} response files...")

    # Import responses
    response_new, response_skipped = import_responses(conn, response_files)

    conn.commit()
    conn.close()

    # Print summary
    print()
    if is_incremental:
        print(f"Plurks: {plurk_new} new, {plurk_skipped} skipped")
        print(f"Responses: {response_new} new, {response_skipped} skipped")
        print(f"Done! Database updated at {args.output_db}")
    else:
        print(f"Imported {plurk_new} plurks, {response_new} responses")
        print(f"Done! Database created at {args.output_db}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
