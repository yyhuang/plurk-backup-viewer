"""
Patch command - modify backup's index.html to add link to enhanced viewer.

Usage:
    plurk-tools patch

This patches the original Plurk backup's index.html to add a link to the
enhanced landing page. Run this after extracting a new backup zip.
"""

import json
import re
import sys
from pathlib import Path


# Paths relative to this file
TOOL_ROOT = Path(__file__).parent.parent
VIEWER_DIR = TOOL_ROOT / "viewer"


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


def cmd_patch() -> int:
    """Run the patch command."""
    # Load config to find backup path
    config_file = VIEWER_DIR / "config.json"
    if not config_file.exists():
        print(f"Error: {config_file} not found", file=sys.stderr)
        print("Run 'plurk-tools init <backup_path>' first", file=sys.stderr)
        return 1

    config = json.loads(config_file.read_text())
    backup_path = Path(config["backup_path"])

    if not backup_path.exists():
        print(f"Error: Backup path not found: {backup_path}", file=sys.stderr)
        return 1

    print(f"Patching backup at: {backup_path}")

    if patch_index_html(backup_path):
        print("\nDone! The original viewer now has a link to the enhanced viewer.")
        print("Start the server with: plurk-tools serve")

    return 0
