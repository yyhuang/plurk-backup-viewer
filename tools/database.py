"""Create or update SQLite database with FTS5 from Plurk backup."""

import argparse
import sqlite3
import sys
from datetime import date
from email.utils import parsedate_to_datetime
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


def load_icu_extension(conn: sqlite3.Connection, extension_path: str) -> None:
    """Load fts5-icu-tokenizer SQLite extension.

    Args:
        conn: SQLite connection
        extension_path: Path to the .dylib/.so extension file
    """
    # Strip file suffix — SQLite's load_extension() auto-appends the
    # platform suffix (.so on Linux, .dylib on macOS), causing double
    # extension errors like "libfts5_icu.so.so" if we pass the full path.
    path = Path(extension_path)
    entry_point = str(path.with_suffix(""))
    conn.enable_load_extension(True)
    conn.load_extension(entry_point)
    conn.enable_load_extension(False)


def resolve_icu_extension(config: dict | None = None) -> str | None:
    """Resolve ICU extension path from config or default location.

    Resolution order:
    1. config["icu_extension_path"] if present
    2. viewer/lib/libfts5_icu.{dylib,so} (default location)
    3. /usr/local/lib/libfts5_icu.so (system, e.g. Docker)
    4. None (fall back to unicode61)

    Args:
        config: Parsed config.json dict, or None

    Returns:
        Path string to ICU extension, or None if not found
    """
    tool_root = Path(__file__).parent.parent
    viewer_dir = tool_root / "viewer"

    # Check config
    if config and config.get("icu_extension_path"):
        path = config["icu_extension_path"]
        if Path(path).exists():
            return path

    # Check default location: only platform-compatible extension
    # (avoids picking up macOS .dylib mounted into Linux container)
    if sys.platform == "darwin":
        names = ("libfts5_icu.dylib",)
    else:
        names = ("libfts5_icu.so",)
    for name in names:
        path = viewer_dir / "lib" / name
        if path.exists():
            return str(path)

    # Check system lib (e.g. Docker image with baked-in libs)
    system_path = Path("/usr/local/lib/libfts5_icu.so")
    if system_path.exists():
        return str(system_path)

    return None


def connect_with_icu(
    db_path: str | Path,
    icu_extension_path: str | None = None,
    config: dict | None = None,
    row_factory=None,
) -> tuple[sqlite3.Connection, bool]:
    """Open a SQLite connection and optionally load the ICU extension.

    ICU resolution order:
    1. Use icu_extension_path if provided
    2. Otherwise call resolve_icu_extension(config) to auto-detect

    Args:
        db_path: Path to the SQLite database
        icu_extension_path: Explicit ICU extension path (takes priority)
        config: Config dict passed to resolve_icu_extension() if no explicit path
        row_factory: Optional row_factory to set on the connection

    Returns:
        (conn, icu_loaded) — icu_loaded is False if not found or load failed.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        if row_factory:
            conn.row_factory = row_factory

        path = icu_extension_path or resolve_icu_extension(config)
        icu_loaded = False
        if path:
            try:
                load_icu_extension(conn, path)
                icu_loaded = True
            except Exception as e:
                print(f"Warning: Failed to load ICU extension: {e}")
    except Exception:
        conn.close()
        raise
    return conn, icu_loaded


def to_epoch(posted_str: str | None) -> int | None:
    """Convert RFC 2822 date string to Unix epoch seconds.

    Args:
        posted_str: Date string like "Wed, 31 Oct 2018 16:00:47 GMT"

    Returns:
        Unix epoch as int, or None if parsing fails
    """
    if not posted_str:
        return None
    try:
        dt = parsedate_to_datetime(posted_str)
        return int(dt.timestamp())
    except Exception:
        return None


def create_schema(conn: sqlite3.Connection, tokenizer: str = "unicode61") -> None:
    """Create database schema with FTS5 tables and triggers.

    Args:
        conn: SQLite connection
        tokenizer: FTS5 tokenizer name (e.g., 'unicode61' or 'icu zh')
    """
    conn.executescript(f"""
        -- Main tables
        CREATE TABLE IF NOT EXISTS plurks (
            id INTEGER PRIMARY KEY,
            base_id TEXT,
            content_raw TEXT,
            posted TEXT,
            posted_ts INTEGER,
            response_count INTEGER,
            qualifier TEXT
        );

        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY,
            base_id TEXT,
            content_raw TEXT,
            posted TEXT,
            posted_ts INTEGER,
            user_id INTEGER,
            user_nick TEXT,
            user_display TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_plurks_posted_ts ON plurks(posted_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_responses_posted_ts ON responses(posted_ts DESC);

        -- FTS5 virtual tables for full-text search
        CREATE VIRTUAL TABLE IF NOT EXISTS plurks_fts USING fts5(
            content_raw,
            content='plurks',
            content_rowid='id',
            tokenize='{tokenizer}'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS responses_fts USING fts5(
            content_raw,
            content='responses',
            content_rowid='id',
            tokenize='{tokenizer}'
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
                INSERT OR IGNORE INTO plurks (id, base_id, content_raw, posted, posted_ts, response_count, qualifier)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["id"],
                    p.get("base_id"),
                    p.get("content_raw"),
                    p.get("posted"),
                    to_epoch(p.get("posted")),
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
                INSERT OR IGNORE INTO responses (id, base_id, content_raw, posted, posted_ts, user_id, user_nick, user_display)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["id"],
                    base_id,
                    r.get("content_raw"),
                    r.get("posted"),
                    to_epoch(r.get("posted")),
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


def ensure_posted_ts_column(conn: sqlite3.Connection) -> None:
    """Add posted_ts column to plurks and responses if missing, and backfill.

    This is a migration for existing databases that lack the column.
    Safe to call multiple times (idempotent).

    Args:
        conn: SQLite connection
    """
    for table in ("plurks", "responses"):
        # Check if column exists
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "posted_ts" in cols:
            continue

        print(f"  Adding posted_ts column to {table}...")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN posted_ts INTEGER")

        # Backfill in batches
        batch_size = 5000
        total = 0
        while True:
            rows = conn.execute(
                f"SELECT id, posted FROM {table} WHERE posted_ts IS NULL LIMIT ?",
                (batch_size,),
            ).fetchall()
            if not rows:
                break
            for row_id, posted_str in rows:
                epoch = to_epoch(posted_str)
                conn.execute(
                    f"UPDATE {table} SET posted_ts = ? WHERE id = ?",
                    (epoch, row_id),
                )
            conn.commit()
            total += len(rows)
            print(f"    Backfilled {total} rows in {table}...")

        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_posted_ts ON {table}(posted_ts DESC)"
        )
        conn.commit()
        print(f"  Done migrating {table}")


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
        ensure_posted_ts_column(conn)

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
