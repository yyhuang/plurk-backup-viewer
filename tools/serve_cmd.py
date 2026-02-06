#!/usr/bin/env python3
"""Development server with dual-directory routing and search API.

Routes requests to appropriate directory:
- /api/* → search API (JSON responses)
- /data/* → backup directory
- /static/backup.*, /static/jquery*, /static/icons.png → backup directory
- /*.html, /plurks.db → viewer directory
- /index.html → backup directory (original viewer)

Usage:
    plurk-tools serve [--port 8000]
"""

import http.server
import json
import re
import socketserver
import sys
import urllib.parse
from pathlib import Path

from database import resolve_icu_extension
from search_api import SearchDB


# Paths relative to this file
TOOL_ROOT = Path(__file__).parent.parent
VIEWER_DIR = TOOL_ROOT / "viewer"


def load_config() -> dict:
    """Load config.json from viewer directory."""
    config_path = VIEWER_DIR / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text())


class DualDirectoryHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that routes requests to viewer or backup directory."""

    backup_path: Path
    search_db: SearchDB

    def __init__(self, *args, backup_path: Path, search_db: SearchDB, **kwargs):
        self.backup_path = backup_path
        self.search_db = search_db
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
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/stats":
                result = self.search_db.get_stats()

            elif path == "/api/search":
                query = params.get("q", [""])[0]
                if not query:
                    self._send_json({"error": "Missing query parameter 'q'"}, 400)
                    return
                search_type = params.get("type", ["all"])[0]
                mode = params.get("mode", ["fts"])[0]
                page = int(params.get("page", ["0"])[0])
                result = self.search_db.search(query, search_type, mode, page)

            elif (m := re.match(r"^/api/plurk/(\d+)$", path)):
                plurk_id = int(m.group(1))
                result = self.search_db.get_plurk(plurk_id)
                if result is None:
                    self._send_json({"error": "Plurk not found"}, 404)
                    return

            elif (m := re.match(r"^/api/response/(\d+)/plurk$", path)):
                response_id = int(m.group(1))
                result = self.search_db.get_response_plurk(response_id)
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

        # Route to backup directory
        if clean_path.startswith("data/"):
            return str(self.backup_path / clean_path)

        if clean_path == "index.html":
            # Original backup viewer
            return str(self.backup_path / clean_path)

        if clean_path.startswith("static/"):
            # Check which static file
            filename = clean_path[7:]  # Remove "static/"
            if filename.startswith("backup.") or filename.startswith("jquery") or filename == "icons.png":
                return str(self.backup_path / clean_path)
            # Other viewer static files
            return str(VIEWER_DIR / clean_path)

        # Default: viewer directory (landing.html, search.html, plurks.db)
        return str(VIEWER_DIR / clean_path)

    def end_headers(self):
        """Add no-cache headers."""
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def make_handler(backup_path: Path, search_db: SearchDB):
    """Create a handler class with the paths bound."""

    class BoundHandler(DualDirectoryHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, backup_path=backup_path, search_db=search_db, **kwargs)

    return BoundHandler


def cmd_serve(port: int = 8000) -> int:
    """Start development server.

    Args:
        port: Port number (default: 8000)

    Returns:
        Exit code (0 for success)
    """
    # Load config to get backup path
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

    # Resolve ICU extension
    db_path = VIEWER_DIR / "plurks.db"
    icu_path = resolve_icu_extension(config)

    if icu_path:
        print(f"  ICU extension: {icu_path}")
    else:
        print("  ICU extension: not found (using unicode61 tokenizer)")

    # Create SearchDB instance
    search_db = SearchDB(db_path, icu_extension_path=icu_path)

    # Create handler and start server
    handler = make_handler(backup_path, search_db)

    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving at http://localhost:{port} (no-cache mode)")
        print(f"  Viewer: {VIEWER_DIR}")
        print(f"  Backup: {backup_path}")
        print()
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            search_db.close()

    return 0


def main():
    """Standalone entry point for serve command."""
    import argparse
    parser = argparse.ArgumentParser(description="Development server")
    parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    args = parser.parse_args()

    return cmd_serve(args.port)


if __name__ == "__main__":
    sys.exit(main())
