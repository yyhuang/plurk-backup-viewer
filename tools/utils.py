"""Utilities for parsing Plurk backup JS files."""

import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta


def parse_plurk_file(path: Path) -> tuple[str, list[dict]]:
    """Parse a plurk JS file and extract the month key and plurk data.

    Args:
        path: Path to the plurk JS file (e.g., data/plurks/2008_12.js)

    Returns:
        Tuple of (month_key, list of plurk dictionaries)

    Example file format:
        BackupData.plurks["2008_12"]=[{...}, {...}];
    """
    content = path.read_text(encoding="utf-8")

    # Extract the key from BackupData.plurks["KEY"]
    key_match = re.match(r'BackupData\.plurks\["([^"]+)"\]', content)
    if not key_match:
        raise ValueError(f"Invalid plurk file format: {path}")

    month_key = key_match.group(1)

    # Extract the JSON array (after the "]=")
    eq_pos = content.index("]=")
    json_start = eq_pos + 2  # Skip "]=" to reach the "[" of the array
    json_end = content.rindex("]") + 1
    json_str = content[json_start:json_end]

    plurks = json.loads(json_str)
    return month_key, plurks


def parse_response_file(path: Path) -> tuple[str, list[dict]]:
    """Parse a response JS file and extract the base_id and response data.

    Args:
        path: Path to the response JS file (e.g., data/responses/100o22.js)

    Returns:
        Tuple of (base_id, list of response dictionaries)

    Example file format:
        BackupData.responses["100o22"]=[{...}, {...}];
    """
    content = path.read_text(encoding="utf-8")

    # Extract the key from BackupData.responses["KEY"]
    key_match = re.match(r'BackupData\.responses\["([^"]+)"\]', content)
    if not key_match:
        raise ValueError(f"Invalid response file format: {path}")

    base_id = key_match.group(1)

    # Extract the JSON array (after the "]=")
    eq_pos = content.index("]=")
    json_start = eq_pos + 2  # Skip "]=" to reach the "[" of the array
    json_end = content.rindex("]") + 1
    json_str = content[json_start:json_end]

    responses = json.loads(json_str)
    return base_id, responses


def validate_backup_dir(path: Path) -> bool:
    """Validate that a directory has the required backup structure.

    Args:
        path: Path to the backup directory

    Returns:
        True if valid, False otherwise

    Required structure:
        path/
        ├── data/
        │   ├── plurks/      (directory)
        │   ├── responses/   (directory)
        │   └── indexes.js   (file)
    """
    required = [
        path / "data" / "plurks",
        path / "data" / "responses",
        path / "data" / "indexes.js",
    ]

    for req in required:
        if not req.exists():
            return False

    return True


def calculate_scan_range(
    conn: sqlite3.Connection, current_date: date
) -> tuple[str | None, str | None]:
    """Calculate month range to scan based on latest data in DB.

    Args:
        conn: SQLite connection to the database
        current_date: Current date for calculating scan range

    Returns:
        (scan_start, scan_end) as "YYYY-MM" strings, or (None, None) for empty DB
    """
    result = conn.execute("SELECT MAX(posted) FROM plurks").fetchone()
    latest_in_db = result[0]

    if latest_in_db is None:
        # Empty DB: process all files
        return (None, None)

    # Parse the latest date from DB (handles various formats like "Wed, 31 Oct 2018 16:00:47 GMT")
    latest_date = parse_date(latest_in_db).date()

    # Calculate gap in months
    gap_months = (
        (current_date.year - latest_date.year) * 12
        + (current_date.month - latest_date.month)
    )

    if gap_months > 6:
        # Long gap: scan from latest in DB
        scan_start = latest_date.strftime("%Y-%m")
    else:
        # Short gap: scan 6 months back to catch new responses
        six_months_ago = current_date - relativedelta(months=6)
        scan_start = six_months_ago.strftime("%Y-%m")

    scan_end = current_date.strftime("%Y-%m")
    return (scan_start, scan_end)


def filter_plurk_files(
    plurks_dir: Path, scan_start: str | None, scan_end: str | None
) -> list[Path]:
    """Filter plurk files to only those in scan range.

    Args:
        plurks_dir: Directory containing plurk JS files
        scan_start: "YYYY-MM" or None for all files
        scan_end: "YYYY-MM" or None for all files

    Returns:
        Sorted list of Path objects for files in range
    """
    all_files = sorted(plurks_dir.glob("*.js"))

    if scan_start is None:
        return all_files

    files = []
    for file in all_files:
        # File format: YYYY_MM.js -> convert to YYYY-MM for comparison
        month_key = file.stem.replace("_", "-")
        if scan_start <= month_key <= scan_end:
            files.append(file)

    return sorted(files)


def get_base_ids_from_plurks(plurk_files: list[Path]) -> set[str]:
    """Collect base_ids from plurk files for response filtering.

    Args:
        plurk_files: List of plurk file paths to process

    Returns:
        Set of base_id strings
    """
    base_ids: set[str] = set()

    for file in plurk_files:
        _, plurks = parse_plurk_file(file)
        for p in plurks:
            if p.get("base_id"):
                base_ids.add(p["base_id"])

    return base_ids


def filter_response_files(responses_dir: Path, base_ids: set[str]) -> list[Path]:
    """Filter response files to only those matching base_ids.

    Args:
        responses_dir: Directory containing response JS files
        base_ids: Set of base_id strings to match

    Returns:
        Sorted list of Path objects for matching response files
    """
    if not base_ids:
        return []

    files = []
    for file in responses_dir.glob("*.js"):
        if file.stem in base_ids:
            files.append(file)

    return sorted(files)
