"""Admin interface - web-based backup upload and database initialization.

Provides a secondary HTTP server (default port 8001) for:
- Uploading Plurk backup zip files
- Initializing the database from uploaded backups
- Monitoring task progress

Used by Docker users who don't have CLI access.
"""

import io
import json
import http.server
import shutil
import sqlite3
import threading
import zipfile
from pathlib import Path

from database import resolve_icu_extension
from init_cmd import build_database, create_config
from links_cmd import (
    OGFetcher,
    create_link_metadata_table,
    is_own_plurk_url,
    is_image_url,
    merge_url_sources,
    process_plurk_file,
    process_response_file,
    update_og_metadata,
    upsert_link,
)
from patch_cmd import patch_index_html
from utils import (
    filter_plurk_files,
    filter_response_files,
    get_base_ids_from_plurks,
    validate_backup_dir,
)


TOOL_ROOT = Path(__file__).parent.parent
VIEWER_DIR = TOOL_ROOT / "viewer"


class TaskTracker:
    """Thread-safe tracker for a single background task (upload or init)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state: dict = {
            "type": None,
            "status": "idle",
            "progress": None,
            "log": [],
            "error": None,
        }

    def start(self, task_type: str) -> bool:
        """Start a new task. Returns False if one is already running."""
        with self._lock:
            if self._state["status"] == "running":
                return False
            self._state = {
                "type": task_type,
                "status": "running",
                "progress": None,
                "log": [],
                "error": None,
            }
            return True

    def update(self, progress: str | None = None, log_line: str | None = None) -> None:
        """Update task progress and/or append a log line."""
        with self._lock:
            if progress is not None:
                self._state["progress"] = progress
            if log_line is not None:
                self._state["log"].append(log_line)

    def finish(self, success: bool, message: str) -> None:
        """Mark task as finished."""
        with self._lock:
            self._state["status"] = "done" if success else "error"
            self._state["log"].append(message)
            if not success:
                self._state["error"] = message

    def get_status(self) -> dict:
        """Get a copy of the current task state."""
        with self._lock:
            return dict(self._state)


def extract_zip(zip_data: bytes, dest_dir: Path, tracker: TaskTracker) -> bool:
    """Extract a Plurk backup zip to dest_dir.

    Handles wrapper directories (e.g., username-backup/data/...).
    Validates structure after extraction.

    Args:
        zip_data: Raw zip file bytes
        dest_dir: Directory to extract into (e.g., data/backup/)
        tracker: TaskTracker for progress updates

    Returns:
        True if extraction succeeded and structure is valid
    """
    tracker.update(log_line="Validating zip file...")

    if not zipfile.is_zipfile(io.BytesIO(zip_data)):
        tracker.finish(False, "Invalid zip file")
        return False

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        # Security: check for path traversal
        for name in zf.namelist():
            if name.startswith("/") or ".." in name:
                tracker.finish(False, f"Unsafe path in zip: {name}")
                return False

        # Detect wrapper directory
        # Plurk exports as username-backup/data/...
        top_dirs = set()
        for name in zf.namelist():
            parts = name.split("/")
            if len(parts) > 1:
                top_dirs.add(parts[0])

        wrapper = ""
        if len(top_dirs) == 1:
            candidate = next(iter(top_dirs))
            # Check if this single top dir contains data/
            has_data_subdir = any(
                name.startswith(f"{candidate}/data/") for name in zf.namelist()
            )
            if has_data_subdir:
                wrapper = candidate + "/"
                tracker.update(log_line=f"Detected wrapper directory: {candidate}/")

        # Clear destination
        if dest_dir.exists():
            tracker.update(log_line="Clearing existing backup...")
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Extract files
        total = len(zf.namelist())
        tracker.update(log_line=f"Extracting {total} files...")

        for i, member in enumerate(zf.namelist()):
            # Strip wrapper directory
            if wrapper and member.startswith(wrapper):
                rel_path = member[len(wrapper):]
            else:
                rel_path = member

            if not rel_path:
                continue

            # Security: re-check after stripping wrapper
            if rel_path.startswith("/") or ".." in rel_path:
                continue

            target = dest_dir / rel_path

            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())

            if (i + 1) % 500 == 0:
                tracker.update(progress=f"{i + 1}/{total}")

    tracker.update(progress=f"{total}/{total}")

    # Validate structure
    tracker.update(log_line="Validating backup structure...")
    if not validate_backup_dir(dest_dir):
        tracker.finish(False, "Invalid backup structure. Expected data/plurks/, data/responses/, data/indexes.js")
        return False

    tracker.update(log_line="Backup extracted successfully")
    return True


def run_init(data_dir: Path, tracker: TaskTracker, on_complete=None) -> bool:
    """Run database initialization in a background thread.

    Args:
        data_dir: Data directory (contains backup/, will contain plurks.db, config.json)
        tracker: TaskTracker for progress updates
        on_complete: Optional callback(data_dir) called on success

    Returns:
        True if initialization succeeded
    """
    backup_path = data_dir / "backup"

    if not validate_backup_dir(backup_path):
        tracker.finish(False, "No valid backup found. Upload a backup zip first.")
        return False

    try:
        # Resolve ICU extension
        icu_path = resolve_icu_extension()
        tokenizer_name = "icu zh" if icu_path else "unicode61"
        tracker.update(log_line=f"Tokenizer: {tokenizer_name}")
        if icu_path:
            tracker.update(log_line=f"ICU extension: {icu_path}")

        # Create config
        tracker.update(log_line="Creating config.json...")
        create_config(backup_path, icu_path, config_dir=data_dir)

        # Build database
        tracker.update(log_line="Building database...")
        db_path = data_dir / "plurks.db"

        # Delete existing DB to force full rebuild
        if db_path.exists():
            db_path.unlink()
            tracker.update(log_line="Removed existing database")

        plurk_count, response_count = build_database(backup_path, db_path, icu_path)
        tracker.update(log_line=f"Database: {plurk_count:,} plurks, {response_count:,} responses")

        # Patch index.html
        tracker.update(log_line="Patching index.html...")
        patched = patch_index_html(backup_path)
        if patched:
            tracker.update(log_line="index.html patched with Enhanced Viewer link")
        else:
            tracker.update(log_line="index.html already patched or not found")

        tracker.finish(True, f"Initialization complete! {plurk_count:,} plurks, {response_count:,} responses")

        if on_complete:
            on_complete(data_dir)

        return True

    except Exception as e:
        tracker.finish(False, f"Initialization failed: {e}")
        return False


def run_links_extract(data_dir: Path, start_month: str, end_month: str,
                      tracker: TaskTracker) -> bool:
    """Extract URLs from backup files for a month range.

    Args:
        data_dir: Data directory (contains backup/, plurks.db, config.json)
        start_month: Start month as YYYYMM
        end_month: End month as YYYYMM
        tracker: TaskTracker for progress updates

    Returns:
        True if extraction succeeded
    """
    backup_path = data_dir / "backup"
    db_path = data_dir / "plurks.db"

    if not validate_backup_dir(backup_path):
        tracker.finish(False, "No valid backup found.")
        return False

    if not db_path.exists():
        tracker.finish(False, "Database not found. Build database first.")
        return False

    try:
        plurks_dir = backup_path / "data" / "plurks"
        responses_dir = backup_path / "data" / "responses"

        # Convert YYYYMM to YYYY-MM
        scan_start = f"{start_month[:4]}-{start_month[4:]}"
        scan_end = f"{end_month[:4]}-{end_month[4:]}"

        tracker.update(log_line=f"Scanning {scan_start} to {scan_end}...")

        plurk_files = filter_plurk_files(plurks_dir, scan_start, scan_end)
        if not plurk_files:
            tracker.finish(False, "No plurk files found for specified period.")
            return False

        tracker.update(log_line=f"Processing {len(plurk_files)} plurk file(s)...")

        # Collect all URLs from plurks
        all_url_sources: dict[str, dict] = {}
        for i, f in enumerate(plurk_files, 1):
            url_sources = process_plurk_file(f)
            merge_url_sources(all_url_sources, url_sources)
            if url_sources:
                tracker.update(log_line=f"  {f.name}: {len(url_sources)} URLs")
            if i % 10 == 0:
                tracker.update(progress=f"Plurks: {i}/{len(plurk_files)}")

        # Get response files matching these plurks
        base_ids = get_base_ids_from_plurks(plurk_files)
        response_files = filter_response_files(responses_dir, base_ids)
        tracker.update(log_line=f"Processing {len(response_files)} response file(s)...")

        for i, f in enumerate(response_files, 1):
            url_sources = process_response_file(f)
            merge_url_sources(all_url_sources, url_sources)
            if i % 50 == 0:
                tracker.update(progress=f"Responses: {i}/{len(response_files)}")

        image_count = sum(1 for url in all_url_sources if is_image_url(url))
        link_count = len(all_url_sources) - image_count
        tracker.update(log_line=f"Found {len(all_url_sources)} unique URLs ({link_count} links, {image_count} images)")

        # Save to database
        conn = sqlite3.connect(str(db_path))
        create_link_metadata_table(conn)

        new_count = 0
        own_plurk_count = 0
        merged_count = 0
        for url, sources in all_url_sources.items():
            if is_own_plurk_url(url, conn):
                own_plurk_count += 1
                continue
            if upsert_link(conn, url, sources):
                new_count += 1
            else:
                merged_count += 1

        conn.commit()
        conn.close()

        own_msg = f", {own_plurk_count} own-plurk skipped" if own_plurk_count else ""
        tracker.finish(True, f"Extract complete: {new_count} new, {merged_count} merged{own_msg}")
        return True

    except Exception as e:
        tracker.finish(False, f"Extract failed: {e}")
        return False


def run_links_fetch(data_dir: Path, limit: int, tracker: TaskTracker) -> bool:
    """Fetch OG metadata for pending links.

    Args:
        data_dir: Data directory (contains plurks.db)
        limit: Max URLs to fetch (0 = all pending)
        tracker: TaskTracker for progress updates

    Returns:
        True if fetch succeeded
    """
    db_path = data_dir / "plurks.db"

    if not db_path.exists():
        tracker.finish(False, "Database not found. Build database first.")
        return False

    try:
        conn = sqlite3.connect(str(db_path))

        # Check if link_metadata table exists
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata'"
        ).fetchone()
        if not table_check:
            conn.close()
            tracker.finish(False, "No links extracted yet. Run Extract Links first.")
            return False

        # Get pending URLs
        limit_clause = f"LIMIT {limit}" if limit else ""
        rows = conn.execute(
            f"SELECT url FROM link_metadata WHERE status = 'pending' {limit_clause}"
        ).fetchall()
        pending_urls = [row[0] for row in rows]

        if not pending_urls:
            conn.close()
            tracker.finish(True, "No pending URLs to fetch.")
            return True

        tracker.update(log_line=f"Fetching OG metadata for {len(pending_urls)} URLs...")

        # Filter out own-plurk URLs (safety net)
        own_plurk_urls = [url for url in pending_urls if is_own_plurk_url(url, conn)]
        if own_plurk_urls:
            for url in own_plurk_urls:
                conn.execute("DELETE FROM link_metadata WHERE url = ?", (url,))
            conn.commit()
            pending_urls = [url for url in pending_urls if url not in set(own_plurk_urls)]
            tracker.update(log_line=f"Skipped {len(own_plurk_urls)} own-plurk URL(s)")

        if not pending_urls:
            conn.close()
            tracker.finish(True, "No pending URLs to fetch.")
            return True

        stats = {"success": 0, "no_og": 0, "image": 0, "timeout": 0, "failed": 0}

        try:
            with OGFetcher() as fetcher:
                for i, url in enumerate(pending_urls, 1):
                    tracker.update(
                        progress=f"{i}/{len(pending_urls)}",
                        log_line=f"[{i}/{len(pending_urls)}] {url[:80]}..."
                    )

                    result = fetcher.fetch(url)
                    update_og_metadata(conn, result)
                    conn.commit()

                    stats[result.status] = stats.get(result.status, 0) + 1
                    tracker.update(log_line=f"  → {result.status}")
        except ImportError:
            conn.close()
            tracker.finish(False, "Playwright not installed. Run: uv add playwright && playwright install chromium")
            return False

        conn.close()

        summary = (f"Fetch complete: {stats['success']} success, {stats['no_og']} no_og, "
                   f"{stats['image']} image, {stats['timeout']} timeout, {stats['failed']} failed")
        tracker.finish(True, summary)
        return True

    except Exception as e:
        tracker.finish(False, f"Fetch failed: {e}")
        return False


class AdminHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for admin interface."""

    data_dir: Path
    viewer_dir: Path
    tracker: TaskTracker
    on_init_complete: object  # callable or None

    def __init__(self, *args, data_dir: Path, viewer_dir: Path,
                 tracker: TaskTracker, on_init_complete=None, **kwargs):
        self.data_dir = data_dir
        self.viewer_dir = viewer_dir
        self.tracker = tracker
        self.on_init_complete = on_init_complete
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "":
            self.send_response(302)
            self.send_header("Location", "/admin.html")
            self.end_headers()
            return

        if self.path == "/admin.html":
            self._serve_file(self.viewer_dir / "admin.html", "text/html")
            return

        if self.path == "/api/admin/info":
            self._handle_info()
            return

        if self.path == "/api/admin/status":
            self._send_json(self.tracker.get_status())
            return

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/api/admin/upload":
            self._handle_upload()
            return

        if self.path == "/api/admin/init":
            self._handle_init()
            return

        if self.path == "/api/admin/links/extract":
            self._handle_links_extract()
            return

        if self.path == "/api/admin/links/fetch":
            self._handle_links_fetch()
            return

        self._send_json({"error": "Not found"}, 404)

    def _handle_info(self):
        """Return system state."""
        backup_path = self.data_dir / "backup"
        db_path = self.data_dir / "plurks.db"

        info: dict = {
            "backup_exists": validate_backup_dir(backup_path),
            "db_exists": db_path.exists(),
            "icu_available": resolve_icu_extension() is not None,
        }

        # Get record counts if DB exists
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                info["plurk_count"] = conn.execute("SELECT COUNT(*) FROM plurks").fetchone()[0]
                info["response_count"] = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]

                # Link metadata counts
                table_check = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata'"
                ).fetchone()
                if table_check:
                    info["link_total"] = conn.execute(
                        "SELECT COUNT(*) FROM link_metadata"
                    ).fetchone()[0]
                    info["link_pending"] = conn.execute(
                        "SELECT COUNT(*) FROM link_metadata WHERE status = 'pending'"
                    ).fetchone()[0]

                conn.close()
            except Exception:
                info["plurk_count"] = 0
                info["response_count"] = 0

        self._send_json(info)

    def _handle_upload(self):
        """Accept zip body and extract in background."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_json({"error": "Empty body"}, 400)
            return

        if not self.tracker.start("upload"):
            self._send_json({"error": "A task is already running"}, 409)
            return

        # Read zip data
        self.tracker.update(log_line=f"Receiving {content_length / 1024 / 1024:.1f} MB...")
        zip_data = self.rfile.read(content_length)

        # Extract in background thread
        def do_extract():
            extract_zip(zip_data, self.data_dir / "backup", self.tracker)
            if self.tracker.get_status()["status"] == "running":
                self.tracker.finish(True, "Upload complete")

        thread = threading.Thread(target=do_extract, daemon=True)
        thread.start()

        self._send_json({"status": "started"})

    def _handle_init(self):
        """Trigger database build in background."""
        if not self.tracker.start("init"):
            self._send_json({"error": "A task is already running"}, 409)
            return

        def do_init():
            run_init(self.data_dir, self.tracker, on_complete=self.on_init_complete)

        thread = threading.Thread(target=do_init, daemon=True)
        thread.start()

        self._send_json({"status": "started"})

    def _handle_links_extract(self):
        """Trigger link extraction in background."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            params = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        start_month = params.get("start_month", "")
        end_month = params.get("end_month", "")

        # Validate month format (YYYYMM)
        for m in (start_month, end_month):
            if len(m) != 6 or not m.isdigit():
                self._send_json({"error": f"Invalid month format: {m}. Use YYYYMM."}, 400)
                return
            month_num = int(m[4:])
            if not 1 <= month_num <= 12:
                self._send_json({"error": f"Invalid month: {m}"}, 400)
                return

        if not self.tracker.start("extract"):
            self._send_json({"error": "A task is already running"}, 409)
            return

        def do_extract():
            run_links_extract(self.data_dir, start_month, end_month, self.tracker)

        thread = threading.Thread(target=do_extract, daemon=True)
        thread.start()

        self._send_json({"status": "started"})

    def _handle_links_fetch(self):
        """Trigger link metadata fetch in background."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            params = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        limit = int(params.get("limit", 0))

        if not self.tracker.start("fetch"):
            self._send_json({"error": "A task is already running"}, 409)
            return

        def do_fetch():
            run_links_fetch(self.data_dir, limit, self.tracker)

        thread = threading.Thread(target=do_fetch, daemon=True)
        thread.start()

        self._send_json({"status": "started"})

    def _serve_file(self, path: Path, content_type: str):
        """Serve a static file."""
        if not path.exists():
            self._send_json({"error": "Not found"}, 404)
            return

        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass


def make_admin_handler(data_dir: Path, viewer_dir: Path,
                       tracker: TaskTracker, on_init_complete=None):
    """Create a bound AdminHandler class."""

    class BoundAdminHandler(AdminHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(
                *args,
                data_dir=data_dir,
                viewer_dir=viewer_dir,
                tracker=tracker,
                on_init_complete=on_init_complete,
                **kwargs,
            )

    return BoundAdminHandler
