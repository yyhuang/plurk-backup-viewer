#!/usr/bin/env python3
"""Development server with dual-directory routing and search API.

Routes requests to appropriate directory:
- /api/* → search API (JSON responses)
- /data/* → backup directory
- /static/backup.*, /static/jquery*, /static/icons.png → backup directory
- /*.html, /plurks.db → viewer directory
- /index.html → backup directory (original viewer)

Usage:
    plurk-tools serve [--port 8000] [--admin-port 8001]
"""

import http.server
import json
import re
import socketserver
import sys
import threading
import urllib.parse
from pathlib import Path

from database import resolve_icu_extension
from search_api import SearchDB


# Paths relative to this file
TOOL_ROOT = Path(__file__).parent.parent
VIEWER_DIR = TOOL_ROOT / "viewer"
DATA_DIR = TOOL_ROOT / "data"


class ServerState:
    """Thread-safe shared state between main server and admin."""

    def __init__(self):
        self._lock = threading.Lock()
        self.search_db: SearchDB | None = None
        self.backup_path: Path | None = None

    def update(self, search_db: SearchDB, backup_path: Path) -> None:
        with self._lock:
            old_db = self.search_db
            self.search_db = search_db
            self.backup_path = backup_path
        if old_db:
            old_db.close()

    def get(self) -> tuple[SearchDB | None, Path | None]:
        with self._lock:
            return self.search_db, self.backup_path


def load_config() -> dict:
    """Load config.json from data directory."""
    config_path = DATA_DIR / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text())


class DualDirectoryHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that routes requests to viewer or backup directory."""

    server_state: ServerState
    admin_port: int | None

    def __init__(self, *args, server_state: ServerState, admin_port: int | None = None, **kwargs):
        self.server_state = server_state
        self.admin_port = admin_port
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET request with routing."""
        # Redirect root to landing.html
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", "/landing.html")
            self.end_headers()
            return

        # API routes
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return

        super().do_GET()

    def _handle_api(self, parsed: urllib.parse.ParseResult) -> None:
        """Route API requests to SearchDB."""
        search_db, _ = self.server_state.get()

        if search_db is None:
            msg = {"error": "Not initialized. Upload backup and run init first."}
            if self.admin_port:
                msg["setup_url"] = f"http://localhost:{self.admin_port}"
            self._send_json(msg, 503)
            return

        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/stats":
                result = search_db.get_stats()

            elif path == "/api/search":
                query = params.get("q", [""])[0]
                if not query:
                    self._send_json({"error": "Missing query parameter 'q'"}, 400)
                    return
                search_type = params.get("type", ["all"])[0]
                mode = params.get("mode", ["fts"])[0]
                page = int(params.get("page", ["0"])[0])
                result = search_db.search(query, search_type, mode, page)

            elif (m := re.match(r"^/api/plurk/(\d+)$", path)):
                plurk_id = int(m.group(1))
                result = search_db.get_plurk(plurk_id)
                if result is None:
                    self._send_json({"error": "Plurk not found"}, 404)
                    return

            elif (m := re.match(r"^/api/response/(\d+)/plurk$", path)):
                response_id = int(m.group(1))
                result = search_db.get_response_plurk(response_id)
                if result is None:
                    self._send_json({"error": "Response not found"}, 404)
                    return

            else:
                self._send_json({"error": "Not found"}, 404)
                return

            self._send_json(result)

        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path: str) -> str:
        """Translate URL path to filesystem path with dual-directory routing."""
        # Parse and normalize the path
        path = urllib.parse.unquote(path)
        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]

        # Remove leading slash for path matching
        clean_path = path.lstrip("/")

        # Route to backup directory (if available)
        _, backup_path = self.server_state.get()

        if backup_path:
            if clean_path.startswith("data/"):
                return str(backup_path / clean_path)

            if clean_path == "index.html":
                # Original backup viewer
                return str(backup_path / clean_path)

            if clean_path.startswith("static/"):
                # Check which static file
                filename = clean_path[7:]  # Remove "static/"
                if filename.startswith("backup.") or filename.startswith("jquery") or filename == "icons.png":
                    return str(backup_path / clean_path)
                # Other viewer static files
                return str(VIEWER_DIR / clean_path)

        # Default: viewer directory (landing.html, search.html)
        return str(VIEWER_DIR / clean_path)

    def end_headers(self):
        """Add no-cache headers."""
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def make_handler(server_state: ServerState, admin_port: int | None = None):
    """Create a handler class with the state bound."""

    class BoundHandler(DualDirectoryHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, server_state=server_state, admin_port=admin_port, **kwargs)

    return BoundHandler


def _init_server_state(state: ServerState) -> None:
    """Try to load config and initialize SearchDB into server state."""
    try:
        config = load_config()
    except FileNotFoundError:
        return

    backup_path = Path(config["backup_path"])
    if not backup_path.exists():
        return

    db_path = DATA_DIR / "plurks.db"
    if not db_path.exists():
        return

    icu_path = resolve_icu_extension(config)
    search_db = SearchDB(db_path, icu_extension_path=icu_path)

    if icu_path:
        print(f"  ICU extension: {icu_path}")
    else:
        print("  ICU extension: not found (using unicode61 tokenizer)")

    state.update(search_db, backup_path)
    print(f"  Backup: {backup_path}")


def cmd_serve(port: int = 8000, admin_port: int | None = None) -> int:
    """Start development server.

    Args:
        port: Port number (default: 8000)
        admin_port: Admin interface port (default: None = disabled)

    Returns:
        Exit code (0 for success)
    """
    # 0 means disabled
    if admin_port == 0:
        admin_port = None

    state = ServerState()

    # Try to load existing config/DB
    if admin_port:
        # Graceful startup: don't fail if not initialized yet
        _init_server_state(state)
        if state.search_db is None:
            print("  Not initialized yet — use admin interface to set up")
    else:
        # Without admin, require config
        try:
            config = load_config()
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("Run 'plurk-tools init <backup_path>' first.", file=sys.stderr)
            return 1

        backup_path = Path(config["backup_path"])
        if not backup_path.exists():
            print(f"Error: Backup directory not found: {backup_path}", file=sys.stderr)
            return 1

        db_path = DATA_DIR / "plurks.db"
        icu_path = resolve_icu_extension(config)

        if icu_path:
            print(f"  ICU extension: {icu_path}")
        else:
            print("  ICU extension: not found (using unicode61 tokenizer)")

        search_db = SearchDB(db_path, icu_extension_path=icu_path)
        state.update(search_db, backup_path)
        print(f"  Backup: {backup_path}")

    # Start admin server if requested
    admin_server = None
    if admin_port:
        from admin_cmd import TaskTracker, make_admin_handler

        data_dir = DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)
        tracker = TaskTracker()

        def on_init_complete(_data_dir: Path):
            """Callback: reload SearchDB after admin init."""
            print("\n  Reloading search database...")
            _init_server_state(state)
            if state.search_db is not None:
                print("  Search is now live!")
            else:
                print("  Warning: Failed to load search database after init")

        admin_handler = make_admin_handler(data_dir, VIEWER_DIR, tracker, on_init_complete)
        admin_server = socketserver.TCPServer(("", admin_port), admin_handler)
        admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
        admin_thread.start()
        print(f"  Admin: http://localhost:{admin_port}")

    # Create handler and start server
    handler = make_handler(state, admin_port=admin_port)

    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving at http://localhost:{port} (no-cache mode)")
        print(f"  Viewer: {VIEWER_DIR}")
        print()
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            search_db_final, _ = state.get()
            if search_db_final:
                search_db_final.close()
            if admin_server:
                admin_server.shutdown()

    return 0


def main():
    """Standalone entry point for serve command."""
    import argparse
    parser = argparse.ArgumentParser(description="Development server")
    parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    parser.add_argument("--admin-port", type=int, default=8001, help="Admin interface port (default: 8001, 0 to disable)")
    args = parser.parse_args()

    return cmd_serve(args.port, admin_port=args.admin_port)


if __name__ == "__main__":
    sys.exit(main())
