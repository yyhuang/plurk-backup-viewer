"""Link metadata commands: extract URLs from backup and fetch OG metadata.

Usage via unified CLI:
    plurk-tools links extract --month 201810
    plurk-tools links fetch --limit 100
    plurk-tools links status
"""

import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from utils import (
    filter_plurk_files,
    filter_response_files,
    get_base_ids_from_plurks,
    parse_plurk_file,
    parse_response_file,
    validate_backup_dir,
)


# Paths relative to this file
TOOL_ROOT = Path(__file__).parent.parent
VIEWER_DIR = TOOL_ROOT / "viewer"


def load_config() -> dict:
    """Load config.json from viewer directory."""
    config_path = VIEWER_DIR / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text())


def resolve_paths() -> tuple[Path, Path]:
    """Resolve backup_path and database path from viewer config.

    Returns:
        Tuple of (backup_path, database_path)
    """
    config = load_config()
    backup_path = Path(config["backup_path"])
    database = VIEWER_DIR / "plurks.db"
    return backup_path, database

# URL regex pattern - matches http:// and https:// URLs
# Stops at whitespace, Chinese characters, or common delimiters
URL_PATTERN = re.compile(
    r'https?://[^\s\u4e00-\u9fff\u3000-\u303f<>"\'\]\)）」』】]*[^\s\u4e00-\u9fff\u3000-\u303f<>"\'\]\)）」』】\.,;:!?]'
)


# ============== OG Fetcher (embedded from og-fetcher) ==============


@dataclass
class OGResult:
    """Result of fetching OG metadata from a URL."""

    url: str
    status: str  # 'success' | 'failed' | 'timeout' | 'no_og'
    title: str | None = None
    description: str | None = None
    site_name: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class OGFetcher:
    """Fetch Open Graph metadata from URLs using a headless browser."""

    def __init__(self, timeout: int = 10000, retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "OGFetcher":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def fetch(self, url: str) -> OGResult:
        if not self._context:
            raise RuntimeError("OGFetcher must be used as context manager.")

        last_error: str | None = None

        for _attempt in range(self.retries):
            try:
                return self._fetch_once(url)
            except Exception as e:
                last_error = str(e)
                if "timeout" in last_error.lower():
                    return OGResult(url=url, status="timeout", error=last_error)
                continue

        return OGResult(url=url, status="failed", error=last_error)

    def _fetch_once(self, url: str) -> OGResult:
        assert self._context is not None
        page = self._context.new_page()
        try:
            response = page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")

            # Check if response is an image by Content-Type
            if response:
                content_type = response.headers.get("content-type")
                if is_image_content_type(content_type):
                    return OGResult(url=url, status="image")

            page_data = page.evaluate(
                """() => {
                const tags = document.querySelectorAll('meta[property^="og:"]');
                const og = {};
                tags.forEach(tag => {
                    const property = tag.getAttribute('property');
                    const content = tag.getAttribute('content');
                    if (property && content) {
                        const key = property.replace('og:', '');
                        og[key] = content;
                    }
                });
                return { og: og, title: document.title || '' };
            }"""
            )

            og_data = page_data.get("og", {}) if page_data else {}
            page_title = (page_data.get("title") or "").strip() if page_data else ""

            if not og_data and not page_title:
                return OGResult(url=url, status="no_og")

            # Use <title> as fallback when og:title is missing
            title = og_data.get("title") or page_title or None

            return OGResult(
                url=url,
                status="success",
                title=title,
                description=og_data.get("description"),
                site_name=og_data.get("site_name"),
            )
        finally:
            page.close()


# ============== URL Extraction ==============


def extract_urls(content: str) -> list[str]:
    """Extract all URLs from content string."""
    if not content:
        return []
    return URL_PATTERN.findall(content)


# Image file extensions to detect
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}


def is_image_url(url: str) -> bool:
    """Check if URL points to an image based on file extension.

    Detects common image extensions: .jpg, .jpeg, .png, .gif, .webp, .bmp, .svg
    Handles URLs with query parameters (e.g., photo.jpg?size=large).
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path.lower()

    # Check if path ends with an image extension
    for ext in IMAGE_EXTENSIONS:
        if path.endswith(ext):
            return True

    return False


def is_image_content_type(content_type: str | None) -> bool:
    """Check if Content-Type header indicates an image.

    Args:
        content_type: HTTP Content-Type header value (e.g., "image/jpeg; charset=utf-8")

    Returns:
        True if content type starts with "image/", False otherwise.
    """
    if not content_type:
        return False
    return content_type.lower().startswith("image/")


def process_plurk_file(path: Path) -> dict[str, dict]:
    """Extract URLs and their source plurk IDs from a plurk file."""
    _, plurks = parse_plurk_file(path)
    url_sources: dict[str, dict] = {}

    for p in plurks:
        content = p.get("content_raw", "")
        plurk_id = p["id"]

        for url in extract_urls(content):
            if url not in url_sources:
                url_sources[url] = {"plurk_ids": [], "response_ids": []}
            if plurk_id not in url_sources[url]["plurk_ids"]:
                url_sources[url]["plurk_ids"].append(plurk_id)

    return url_sources


def process_response_file(path: Path) -> dict[str, dict]:
    """Extract URLs and their source response IDs from a response file."""
    _, responses = parse_response_file(path)
    url_sources: dict[str, dict] = {}

    for r in responses:
        content = r.get("content_raw", "")
        response_id = r["id"]

        for url in extract_urls(content):
            if url not in url_sources:
                url_sources[url] = {"plurk_ids": [], "response_ids": []}
            if response_id not in url_sources[url]["response_ids"]:
                url_sources[url]["response_ids"].append(response_id)

    return url_sources


def merge_url_sources(base: dict[str, dict], new: dict[str, dict]) -> dict[str, dict]:
    """Merge two URL source dictionaries."""
    for url, sources in new.items():
        if url not in base:
            base[url] = {"plurk_ids": [], "response_ids": []}

        for pid in sources.get("plurk_ids", []):
            if pid not in base[url]["plurk_ids"]:
                base[url]["plurk_ids"].append(pid)

        for rid in sources.get("response_ids", []):
            if rid not in base[url]["response_ids"]:
                base[url]["response_ids"].append(rid)

    return base


# ============== Database Operations ==============


def create_link_metadata_table(conn: sqlite3.Connection) -> None:
    """Create the link_metadata table with FTS5 if it doesn't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS link_metadata (
            url TEXT PRIMARY KEY,
            og_title TEXT,
            og_description TEXT,
            og_site_name TEXT,
            sources JSON,
            status TEXT DEFAULT 'pending',
            fetched_at TEXT
        );

        -- FTS5 for searching OG metadata
        CREATE VIRTUAL TABLE IF NOT EXISTS link_metadata_fts USING fts5(
            og_title,
            og_description,
            og_site_name,
            content='link_metadata',
            content_rowid='rowid',
            tokenize='unicode61'
        );

        -- Triggers to keep FTS in sync
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


def upsert_link(conn: sqlite3.Connection, url: str, new_sources: dict) -> bool:
    """Insert or merge a link into the database.

    Returns True if new URL inserted, False if existing URL merged.
    """
    existing = conn.execute(
        "SELECT sources FROM link_metadata WHERE url = ?", (url,)
    ).fetchone()

    if existing is None:
        # Set status based on URL: 'image' for image URLs, 'pending' otherwise
        status = "image" if is_image_url(url) else "pending"
        conn.execute(
            "INSERT INTO link_metadata (url, sources, status) VALUES (?, ?, ?)",
            (url, json.dumps(new_sources), status),
        )
        return True
    else:
        old_sources = json.loads(existing[0])
        merged_plurk_ids = list(
            set(old_sources.get("plurk_ids", []) + new_sources.get("plurk_ids", []))
        )
        merged_response_ids = list(
            set(old_sources.get("response_ids", []) + new_sources.get("response_ids", []))
        )
        merged = {
            "plurk_ids": sorted(merged_plurk_ids),
            "response_ids": sorted(merged_response_ids),
        }
        conn.execute(
            "UPDATE link_metadata SET sources = ? WHERE url = ?",
            (json.dumps(merged), url),
        )
        return False


def update_og_metadata(conn: sqlite3.Connection, result: OGResult) -> None:
    """Update a URL's OG metadata in the database."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE link_metadata
           SET og_title = ?, og_description = ?, og_site_name = ?,
               status = ?, fetched_at = ?
           WHERE url = ?""",
        (result.title, result.description, result.site_name, result.status, now, result.url),
    )


# ============== Commands ==============


def cmd_extract(args) -> int:
    """Extract URLs from backup files."""
    # Validate --month format
    if len(args.month) != 6 or not args.month.isdigit():
        print("Error: --month must be YYYYMM format (e.g., 201810)", file=sys.stderr)
        return 1
    month_num = int(args.month[4:])
    if not 1 <= month_num <= 12:
        print("Error: month must be 01-12", file=sys.stderr)
        return 1

    if not validate_backup_dir(args.backup_path):
        print(f"Error: Invalid backup directory: {args.backup_path}", file=sys.stderr)
        return 1

    database = args.db if args.db else args.backup_path / "data" / "plurks.db"
    plurks_dir = args.backup_path / "data" / "plurks"
    responses_dir = args.backup_path / "data" / "responses"

    # Single month: YYYYMM -> YYYY-MM
    scan_start = scan_end = f"{args.month[:4]}-{args.month[4:]}"

    plurk_files = filter_plurk_files(plurks_dir, scan_start, scan_end)
    if not plurk_files:
        print("No plurk files found for specified period", file=sys.stderr)
        return 1

    print(f"Processing {len(plurk_files)} plurk file(s)...")

    # Collect all URLs from plurks
    all_url_sources: dict[str, dict] = {}
    for file in plurk_files:
        url_sources = process_plurk_file(file)
        merge_url_sources(all_url_sources, url_sources)
        if url_sources:
            print(f"  {file.name}: {len(url_sources)} URLs")

    # Get response files matching these plurks
    base_ids = get_base_ids_from_plurks(plurk_files)
    response_files = filter_response_files(responses_dir, base_ids)
    print(f"Processing {len(response_files)} response file(s)...")

    for file in response_files:
        url_sources = process_response_file(file)
        merge_url_sources(all_url_sources, url_sources)

    # Count images vs regular links
    image_count = sum(1 for url in all_url_sources if is_image_url(url))
    link_count = len(all_url_sources) - image_count
    print(f"\nFound {len(all_url_sources)} unique URLs ({link_count} links, {image_count} images)")

    # Save to database
    conn = sqlite3.connect(database)
    create_link_metadata_table(conn)

    new_count = 0
    new_images = 0
    merged_count = 0
    for url, sources in all_url_sources.items():
        if upsert_link(conn, url, sources):
            new_count += 1
            if is_image_url(url):
                new_images += 1
        else:
            merged_count += 1

    conn.commit()
    conn.close()

    new_links = new_count - new_images
    print(f"Database updated: {new_count} new ({new_links} links, {new_images} images), {merged_count} merged")

    # Optionally fetch OG metadata
    if args.fetch_previews:
        print("\n--- Fetching OG metadata ---")
        args.limit = getattr(args, "limit", 0) or 0  # 0 = all newly extracted
        return cmd_fetch_previews_internal(args, list(all_url_sources.keys()))

    return 0


def cmd_fetch_previews(args) -> int:
    """Fetch OG metadata for pending URLs."""
    return cmd_fetch_previews_internal(args, None, args.timeout, args.retries)


def cmd_fetch_previews_internal(
    args, url_filter: list[str] | None, timeout: int = 10000, retries: int = 3
) -> int:
    """Internal: fetch OG metadata.

    Args:
        args: Parsed arguments
        url_filter: If provided, only fetch these URLs (must still be pending).
                    If None, fetch all pending URLs up to limit.
        timeout: Page load timeout in ms (default: 10000)
        retries: Number of retries (default: 3)
    """
    if not validate_backup_dir(args.backup_path):
        print(f"Error: Invalid backup directory: {args.backup_path}", file=sys.stderr)
        return 1

    database = args.db if args.db else args.backup_path / "data" / "plurks.db"

    if not database.exists():
        print(f"Error: Database not found: {database}", file=sys.stderr)
        print("Run 'extract' command first to create the database.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(database)

    # Get pending URLs
    if url_filter:
        # Filter to specific URLs that are pending
        placeholders = ",".join("?" * len(url_filter))
        query = f"SELECT url FROM link_metadata WHERE status = 'pending' AND url IN ({placeholders})"
        rows = conn.execute(query, url_filter).fetchall()
    else:
        # Get all pending URLs
        limit_clause = f"LIMIT {args.limit}" if args.limit else ""
        query = f"SELECT url FROM link_metadata WHERE status = 'pending' {limit_clause}"
        rows = conn.execute(query).fetchall()

    pending_urls = [row[0] for row in rows]

    if not pending_urls:
        print("No pending URLs to fetch.")
        conn.close()
        return 0

    print(f"Fetching OG metadata for {len(pending_urls)} URLs...")

    # Fetch OG metadata
    stats = {"success": 0, "no_og": 0, "image": 0, "timeout": 0, "failed": 0}

    with OGFetcher(timeout=timeout, retries=retries) as fetcher:
        for i, url in enumerate(pending_urls, 1):
            print(f"  [{i}/{len(pending_urls)}] {url[:80]}...", end=" ", flush=True)

            result = fetcher.fetch(url)
            update_og_metadata(conn, result)
            conn.commit()

            stats[result.status] += 1
            print(result.status)

    conn.close()

    print(f"\nCompleted: {stats['success']} success, {stats['no_og']} no_og, "
          f"{stats['image']} image, {stats['timeout']} timeout, {stats['failed']} failed")

    return 0


def cmd_status(args) -> int:
    """Show link_metadata database status."""
    if not validate_backup_dir(args.backup_path):
        print(f"Error: Invalid backup directory: {args.backup_path}", file=sys.stderr)
        return 1

    database = args.db if args.db else args.backup_path / "data" / "plurks.db"

    if not database.exists():
        print(f"Database not found: {database}")
        return 1

    conn = sqlite3.connect(database)

    # Check if table exists
    table_check = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata'"
    ).fetchone()

    if not table_check:
        print("link_metadata table does not exist. Run 'extract' first.")
        conn.close()
        return 0

    # Get counts by status
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM link_metadata GROUP BY status ORDER BY status"
    ).fetchall()

    total = sum(row[1] for row in rows)
    print(f"Total URLs: {total}")
    print("By status:")
    for status, count in rows:
        print(f"  {status}: {count}")

    conn.close()
    return 0


# ============== Unified CLI Entry Point ==============


def cmd_links(args) -> int:
    """Entry point for 'plurk-tools links' subcommands.

    Called from cli.py with parsed args.
    """
    try:
        backup_path, database = resolve_paths()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Run 'plurk-tools init <backup_path>' first.", file=sys.stderr)
        return 1

    if not validate_backup_dir(backup_path):
        print(f"Error: Invalid backup directory: {backup_path}", file=sys.stderr)
        return 1

    # Create a namespace with the resolved paths for internal commands
    from types import SimpleNamespace

    if args.links_command == "extract":
        resolved = SimpleNamespace(
            backup_path=backup_path,
            db=database,
            month=args.month,
            fetch_previews=args.fetch_previews,
        )
        return cmd_extract(resolved)

    elif args.links_command == "fetch":
        resolved = SimpleNamespace(
            backup_path=backup_path,
            db=database,
            limit=args.limit,
            timeout=args.timeout,
            retries=args.retries,
        )
        return cmd_fetch_previews(resolved)

    elif args.links_command == "status":
        resolved = SimpleNamespace(
            backup_path=backup_path,
            db=database,
        )
        return cmd_status(resolved)

    return 1


