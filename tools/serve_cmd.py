#!/usr/bin/env python3
"""Development server with dual-directory routing.

Routes requests to appropriate directory:
- /data/* → backup directory
- /static/backup.*, /static/jquery*, /static/icons.png → backup directory
- /static/sql-wasm.* → viewer directory
- /*.html, /plurks.db → viewer directory
- /index.html → backup directory (original viewer)

Usage:
    plurk-tools serve <viewer_path> [--port 8000]

Examples:
    plurk-tools serve ../username-viewer
    plurk-tools serve ../username-viewer --port 3000
"""

import argparse
import http.server
import json
import socketserver
import sys
import urllib.parse
from pathlib import Path


def load_config(viewer_path: Path) -> dict:
    """Load config.json from viewer directory."""
    config_path = viewer_path / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text())


class DualDirectoryHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that routes requests to viewer or backup directory."""

    viewer_path: Path
    backup_path: Path

    def __init__(self, *args, viewer_path: Path, backup_path: Path, **kwargs):
        self.viewer_path = viewer_path
        self.backup_path = backup_path
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET request with routing."""
        # Redirect root to landing.html
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", "/landing.html")
            self.end_headers()
            return
        super().do_GET()

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
            # sql-wasm.* and other viewer static files
            return str(self.viewer_path / clean_path)

        # Default: viewer directory (landing.html, search.html, plurks.db)
        return str(self.viewer_path / clean_path)

    def end_headers(self):
        """Add no-cache headers."""
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def make_handler(viewer_path: Path, backup_path: Path):
    """Create a handler class with the paths bound."""

    class BoundHandler(DualDirectoryHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, viewer_path=viewer_path, backup_path=backup_path, **kwargs)

    return BoundHandler


def cmd_serve(viewer_path: Path, port: int = 8000) -> int:
    """Start development server.

    Args:
        viewer_path: Path to viewer directory
        port: Port number (default: 8000)

    Returns:
        Exit code (0 for success)
    """
    viewer_path = viewer_path.resolve()

    # Load config to get backup path
    try:
        config = load_config(viewer_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Run 'plurk-tools init' first to create the viewer.", file=sys.stderr)
        return 1

    backup_path = Path(config["backup_path"])
    if not backup_path.exists():
        print(f"Error: Backup directory not found: {backup_path}", file=sys.stderr)
        return 1

    # Create handler and start server
    handler = make_handler(viewer_path, backup_path)

    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving at http://localhost:{port} (no-cache mode)")
        print(f"  Viewer: {viewer_path}")
        print(f"  Backup: {backup_path}")
        print()
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")

    return 0


def main():
    """Standalone entry point for serve command."""
    parser = argparse.ArgumentParser(description="Development server with dual-directory routing")
    parser.add_argument("viewer_path", type=Path, help="Path to viewer directory")
    parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    args = parser.parse_args()

    return cmd_serve(args.viewer_path, args.port)


if __name__ == "__main__":
    sys.exit(main())
