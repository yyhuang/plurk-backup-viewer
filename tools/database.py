"""Create or update SQLite database with FTS5 from Plurk backup."""

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
                conn.close()
                raise RuntimeError(
                    f"Failed to load ICU extension from {path}: {e}\n"
                    "Fix: install the correct ICU extension, or remove it to use unicode61 fallback."
                ) from e
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

        print(f"  Done migrating {table}")
