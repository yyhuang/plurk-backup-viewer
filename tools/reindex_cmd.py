"""Reindex command - rebuild FTS5 tables without reimporting data.

Useful when switching tokenizers (e.g., unicode61 → icu zh).
Drops and recreates all FTS5 virtual tables and triggers,
then repopulates them from existing data.
"""

import json
import sqlite3
import sys
from pathlib import Path

from database import create_schema, load_icu_extension, resolve_icu_extension

TOOL_ROOT = Path(__file__).parent.parent
VIEWER_DIR = TOOL_ROOT / "viewer"


def rebuild_fts(conn: sqlite3.Connection, tokenizer: str) -> dict:
    """Drop and recreate all FTS5 tables with the given tokenizer.

    Args:
        conn: SQLite connection (ICU extension must already be loaded if needed)
        tokenizer: FTS5 tokenizer name (e.g., 'unicode61' or 'icu zh')

    Returns:
        Dict with row counts repopulated per table
    """
    # Drop existing triggers and FTS tables
    conn.executescript("""
        -- Drop triggers for plurks
        DROP TRIGGER IF EXISTS plurks_ai;
        DROP TRIGGER IF EXISTS plurks_ad;
        DROP TRIGGER IF EXISTS plurks_au;

        -- Drop triggers for responses
        DROP TRIGGER IF EXISTS responses_ai;
        DROP TRIGGER IF EXISTS responses_ad;
        DROP TRIGGER IF EXISTS responses_au;

        -- Drop triggers for link_metadata
        DROP TRIGGER IF EXISTS link_metadata_ai;
        DROP TRIGGER IF EXISTS link_metadata_ad;
        DROP TRIGGER IF EXISTS link_metadata_au;

        -- Drop FTS tables
        DROP TABLE IF EXISTS plurks_fts;
        DROP TABLE IF EXISTS responses_fts;
        DROP TABLE IF EXISTS link_metadata_fts;
    """)

    # Recreate plurks/responses FTS tables and triggers
    create_schema(conn, tokenizer)

    # Recreate link_metadata FTS if link_metadata table exists
    has_links = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata'"
    ).fetchone()

    if has_links:
        conn.executescript(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS link_metadata_fts USING fts5(
                og_title,
                og_description,
                og_site_name,
                content='link_metadata',
                content_rowid='rowid',
                tokenize='{tokenizer}'
            );

            CREATE TRIGGER IF NOT EXISTS link_metadata_ai AFTER INSERT ON link_metadata BEGIN
                INSERT INTO link_metadata_fts(rowid, og_title, og_description, og_site_name)
                VALUES (new.rowid, new.og_title, new.og_description, new.og_site_name);
            END;

            CREATE TRIGGER IF NOT EXISTS link_metadata_ad AFTER DELETE ON link_metadata BEGIN
                INSERT INTO link_metadata_fts(link_metadata_fts, rowid, og_title, og_description, og_site_name)
                VALUES ('delete', old.rowid, old.og_title, old.og_description, old.og_site_name);
            END;

            CREATE TRIGGER IF NOT EXISTS link_metadata_au AFTER UPDATE ON link_metadata BEGIN
                INSERT INTO link_metadata_fts(link_metadata_fts, rowid, og_title, og_description, og_site_name)
                VALUES ('delete', old.rowid, old.og_title, old.og_description, old.og_site_name);
                INSERT INTO link_metadata_fts(rowid, og_title, og_description, og_site_name)
                VALUES (new.rowid, new.og_title, new.og_description, new.og_site_name);
            END;
        """)

    # Repopulate FTS tables from existing data
    plurk_count = conn.execute(
        "INSERT INTO plurks_fts(rowid, content_raw) SELECT id, content_raw FROM plurks"
    ).rowcount

    response_count = conn.execute(
        "INSERT INTO responses_fts(rowid, content_raw) SELECT id, content_raw FROM responses"
    ).rowcount

    link_count = 0
    if has_links:
        link_count = conn.execute(
            "INSERT INTO link_metadata_fts(rowid, og_title, og_description, og_site_name) "
            "SELECT rowid, og_title, og_description, og_site_name FROM link_metadata"
        ).rowcount

    conn.commit()

    return {
        "plurks": plurk_count,
        "responses": response_count,
        "links": link_count,
    }


def cmd_reindex() -> int:
    """Rebuild FTS5 indexes with the configured tokenizer.

    Returns:
        Exit code (0 for success)
    """
    db_path = VIEWER_DIR / "plurks.db"
    config_path = VIEWER_DIR / "config.json"

    if not db_path.exists():
        print("Error: Database not found. Run 'plurk-tools init' first.", file=sys.stderr)
        return 1

    # Load config
    config = None
    if config_path.exists():
        config = json.loads(config_path.read_text())

    # Resolve ICU extension
    icu_path = resolve_icu_extension(config)
    tokenizer = "unicode61"
    if icu_path:
        tokenizer = "icu zh"
        print(f"ICU extension: {icu_path}")
    else:
        print("No ICU extension found. Using unicode61 tokenizer.")

    print(f"Tokenizer: {tokenizer}")
    print(f"Database: {db_path}")
    print()

    # Open database and load extension
    conn = sqlite3.connect(db_path)
    if icu_path:
        load_icu_extension(conn, icu_path)

    print("Rebuilding FTS5 indexes...")
    counts = rebuild_fts(conn, tokenizer)
    conn.close()

    print(f"  Plurks: {counts['plurks']:,} rows indexed")
    print(f"  Responses: {counts['responses']:,} rows indexed")
    if counts["links"]:
        print(f"  Links: {counts['links']:,} rows indexed")
    print()
    print("Done!")

    return 0
