"""
Patch command - modify backup's index.html to add link to enhanced viewer.

Usage:
    plurk-tools patch <viewer_path>

This patches the original Plurk backup's index.html to add a link to the
enhanced landing page. Run this after extracting a new backup zip.
"""

import json
import re
import sys
from pathlib import Path


def patch_index_html(backup_path: Path) -> bool:
    """
    Add a link to landing.html in the backup's index.html.

    Returns True if patched, False if already patched or failed.
    """
    index_file = backup_path / "index.html"

    if not index_file.exists():
        print(f"Error: {index_file} not found", file=sys.stderr)
        return False

    content = index_file.read_text(encoding="utf-8")

    # Check if already patched
    if "enhanced-viewer-link" in content:
        print("index.html already patched, skipping")
        return False

    # The link to inject - styled to match Plurk's top bar
    link_html = '''<a id="enhanced-viewer-link" href="/landing.html" style="color: #fff; text-decoration: none; padding: 8px 16px; background: #cf682f; border-radius: 4px; margin-left: 16px; font-size: 14px;">Enhanced Viewer</a>'''

    # Try to inject after the backup-info div
    # Pattern: <div id="backup-info"></div>
    pattern = r'(<div id="backup-info"></div>)'
    replacement = r'\1' + link_html

    new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        # Fallback: inject after top-bar opening
        pattern = r'(<div id="top-bar"[^>]*>)'
        replacement = r'\1' + link_html
        new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        print("Error: Could not find injection point in index.html", file=sys.stderr)
        return False

    index_file.write_text(new_content, encoding="utf-8")
    print(f"Patched {index_file}")
    return True


def cmd_patch(args) -> int:
    """Run the patch command."""
    viewer_path = Path(args.viewer_path).resolve()

    # Load config to find backup path
    config_file = viewer_path / "config.json"
    if not config_file.exists():
        print(f"Error: {config_file} not found", file=sys.stderr)
        print("Run 'plurk-tools init' first to create the viewer", file=sys.stderr)
        return 1

    config = json.loads(config_file.read_text())
    backup_path = Path(config["backup_path"])

    if not backup_path.exists():
        print(f"Error: Backup path not found: {backup_path}", file=sys.stderr)
        return 1

    print(f"Patching backup at: {backup_path}")

    if patch_index_html(backup_path):
        print("\nDone! The original viewer now has a link to the enhanced viewer.")
        print("Start the server with: plurk-tools serve", viewer_path)

    return 0


def setup_parser(subparsers):
    """Set up the argument parser for the patch command."""
    parser = subparsers.add_parser(
        "patch",
        help="Add link to enhanced viewer in backup's index.html",
        description=__doc__,
    )
    parser.add_argument(
        "viewer_path",
        help="Path to viewer directory (e.g., username-viewer)",
    )
    parser.set_defaults(func=cmd_patch)
