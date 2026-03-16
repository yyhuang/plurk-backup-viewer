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
DATA_DIR = TOOL_ROOT / "data"


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
    if "plurk-logo-link" in content:
        print("index.html already patched, skipping")
        return False

    # Wrap plurk-logo contents in a link to /landing.html
    # Original: <div id="plurk-logo"><span ...></span><span ...></span></div>
    # Patched:  <div id="plurk-logo"><a id="plurk-logo-link" href="/landing.html" ...>...</a></div>
    pattern = r'(<div id="plurk-logo">)(.*?)(</div>)'
    # re.S so .*? matches newlines in multiline HTML
    link_open = '<a id="plurk-logo-link" href="/landing.html" style="text-decoration: none;">'
    link_close = '</a>'
    replacement = rf'\1{link_open}\2{link_close}\3'

    new_content, count = re.subn(pattern, replacement, content, flags=re.S)

    if count == 0:
        print("Error: Could not find plurk-logo div in index.html", file=sys.stderr)
        return False

    index_file.write_text(new_content, encoding="utf-8")
    print(f"Patched {index_file}")
    return True


def cmd_patch() -> int:
    """Run the patch command."""
    # Load config to find backup path
    config_file = DATA_DIR / "config.json"
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
