"""Init command - initialize database from Plurk backup.

This command:
1. Creates config.json pointing to the backup directory
2. Builds the SQLite database from backup data

Database and config are stored in the viewer/ directory.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from database import (
    connect_with_icu,
    create_schema,
    import_plurks,
    import_responses,
    resolve_icu_extension,
)
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
DATA_DIR = TOOL_ROOT / "data"


def create_config(
    backup_path: Path,
    icu_extension_path: str | None = None,
    config_dir: Path | None = None,
) -> None:
    """Create config.json in the data directory.

    Args:
        backup_path: Path to backup directory
        icu_extension_path: Optional path to ICU tokenizer extension
        config_dir: Directory to write config.json (defaults to DATA_DIR)
    """
    config_dir = config_dir or DATA_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    config: dict = {
        "backup_path": str(backup_path.resolve()),
    }
    if icu_extension_path:
        config["icu_extension_path"] = icu_extension_path
    config_path = config_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2))


@dataclass
class BuildResult:
    """Result of build_database()."""

    plurk_count: int
    response_count: int
    plurk_files: list[Path] = field(default_factory=list)
    response_files: list[Path] = field(default_factory=list)


def build_database(
    backup_path: Path, db_path: Path, icu_extension_path: str | None = None
) -> BuildResult:
    """Build SQLite database from backup.

    Args:
        backup_path: Path to backup directory
        db_path: Path for output database
        icu_extension_path: Optional path to ICU tokenizer extension

    Returns:
        BuildResult with counts and file lists
    """
    from datetime import date

    plurks_dir = backup_path / "data" / "plurks"
    responses_dir = backup_path / "data" / "responses"

    # Check if database exists (incremental update)
    is_incremental = db_path.exists()

    # Open connection and load ICU extension (if available)
    conn, icu_loaded = connect_with_icu(db_path, icu_extension_path)
    tokenizer = "icu zh" if icu_loaded else "unicode61"

    if is_incremental:
        print(f"Updating existing database: {db_path}")
        scan_start, scan_end = calculate_scan_range(conn, date.today())
        if scan_start:
            print(f"Scanning files from {scan_start} to {scan_end}")
        else:
            print("Database is empty, importing all files")
    else:
        print(f"Creating new database: {db_path}")
        create_schema(conn, tokenizer)
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

    return BuildResult(
        plurk_count=plurk_count,
        response_count=response_count,
        plurk_files=plurk_files,
        response_files=response_files,
    )


def cmd_init(backup_path: Path, icu_extension: str | None = None) -> int:
    """Initialize database from Plurk backup.

    Args:
        backup_path: Path to backup directory
        icu_extension: Optional path to ICU tokenizer extension

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

    # Resolve ICU extension path
    icu_path = icu_extension
    if icu_path:
        icu_path = str(Path(icu_path).resolve())
        if not Path(icu_path).exists():
            print(f"Error: ICU extension not found: {icu_path}", file=sys.stderr)
            return 1
        print(f"ICU extension: {icu_path}")
    else:
        # Check default location
        icu_path = resolve_icu_extension()
        if icu_path:
            print(f"ICU extension (auto-detected): {icu_path}")
        else:
            print("Warning: No ICU extension found. Using unicode61 tokenizer.")
            print("  For better CJK search, place libfts5_icu.dylib in viewer/lib/")

    print(f"Backup: {backup_path}")
    print(f"Data:   {DATA_DIR}")
    print()

    # Step 1: Create config.json
    print("Creating config.json...")
    create_config(backup_path, icu_path)

    # Step 2: Build database
    print("Building database...")
    db_path = DATA_DIR / "plurks.db"
    result = build_database(backup_path, db_path, icu_path)

    print()
    print(f"Database: {result.plurk_count:,} plurks, {result.response_count:,} responses")
    print(f"Tokenizer: {'icu zh' if icu_path else 'unicode61'}")

    # Step 3: Extract links
    try:
        from links_cmd import extract_links_from_files

        tokenizer = "icu zh" if icu_path else "unicode61"
        print()
        print("Extracting links...")
        link_result = extract_links_from_files(
            plurk_files=result.plurk_files,
            response_files=result.response_files,
            db_path=db_path,
            tokenizer=tokenizer,
            icu_extension_path=icu_path,
            progress_callback=lambda msg: print(f"  {msg}"),
        )
        print(
            f"Links: {link_result['new_count']} new, "
            f"{link_result['merged_count']} merged, "
            f"{link_result['own_plurk_count']} own-plurk skipped"
        )
    except Exception as e:
        print(f"Warning: Link extraction failed: {e}", file=sys.stderr)

    print()
    print("Done! To start the server:")
    print(f"  cd {TOOL_ROOT / 'tools'}")
    print("  uv run plurk-tools serve")

    return 0
