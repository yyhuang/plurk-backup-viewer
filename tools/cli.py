#!/usr/bin/env python3
"""Plurk Backup Tools - Unified CLI.

Usage:
    plurk-tools init <backup_path>
    plurk-tools serve [--port 8000]
    plurk-tools patch
    plurk-tools links extract --month YYYYMM
    plurk-tools links fetch [--limit 50]
    plurk-tools links status
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    """Main entry point for plurk-tools CLI."""
    parser = argparse.ArgumentParser(
        description="Plurk Backup Tools - manage and search Plurk backups",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize from backup (creates database in viewer/)
  plurk-tools init ../username-backup

  # Serve viewer (starts development server)
  plurk-tools serve

  # Extract links from October 2018
  plurk-tools links extract --month 201810

  # Fetch OG metadata for pending links
  plurk-tools links fetch --limit 100

  # Check link database status
  plurk-tools links status
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ========== init command ==========
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize database from Plurk backup",
        description="Create database from backup data",
    )
    init_parser.add_argument(
        "backup_path",
        type=Path,
        help="Path to backup directory (e.g., ../username-backup)",
    )

    # ========== serve command ==========
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start development server",
        description="Serve viewer with no-cache headers for development",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number (default: 8000)",
    )

    # ========== patch command ==========
    subparsers.add_parser(
        "patch",
        help="Add link to enhanced viewer in backup's index.html",
        description="Patch the original Plurk backup's index.html to add a link to the enhanced landing page",
    )

    # ========== links command ==========
    links_parser = subparsers.add_parser(
        "links",
        help="Manage link metadata",
        description="Extract URLs and fetch OG metadata",
    )
    links_subparsers = links_parser.add_subparsers(dest="links_command", required=True)

    # links extract
    links_extract_parser = links_subparsers.add_parser(
        "extract",
        help="Extract URLs from backup files",
    )
    links_extract_parser.add_argument(
        "--month",
        type=str,
        required=True,
        help="Month to process (YYYYMM format)",
    )
    links_extract_parser.add_argument(
        "--fetch-previews",
        action="store_true",
        help="Also fetch OG metadata for extracted URLs",
    )

    # links fetch
    links_fetch_parser = links_subparsers.add_parser(
        "fetch",
        help="Fetch OG metadata for pending URLs",
    )
    links_fetch_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max URLs to fetch (default: 50, 0=all)",
    )
    links_fetch_parser.add_argument(
        "--timeout",
        type=int,
        default=10000,
        help="Page load timeout in ms (default: 10000)",
    )
    links_fetch_parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retries (default: 3)",
    )

    # links status
    links_subparsers.add_parser(
        "status",
        help="Show link database status",
    )

    args = parser.parse_args()

    # Route to appropriate command handler
    if args.command == "init":
        from init_cmd import cmd_init

        return cmd_init(args.backup_path)

    elif args.command == "serve":
        from serve_cmd import cmd_serve

        return cmd_serve(args.port)

    elif args.command == "patch":
        from patch_cmd import cmd_patch

        return cmd_patch()

    elif args.command == "links":
        from links_cmd import cmd_links

        return cmd_links(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
