"""Tests for incremental import feature."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from database import create_schema


# These functions will be implemented in utils.py
from utils import (
    calculate_scan_range,
    filter_plurk_files,
    get_base_ids_from_plurks,
    filter_response_files,
)


class TestCalculateScanRange:
    """Tests for calculate_scan_range function."""

    def test_empty_db_returns_none(self, tmp_path: Path):
        """Empty DB should return (None, None) to process all files."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        result = calculate_scan_range(conn, date(2026, 2, 2))

        assert result == (None, None)
        conn.close()

    def test_long_gap_scans_from_latest(self, tmp_path: Path):
        """Gap > 6 months: scan from latest in DB."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        # Insert a plurk from 2025-06-15 (8 months ago from 2026-02-02)
        conn.execute(
            "INSERT INTO plurks (id, posted) VALUES (?, ?)",
            (1, "2025-06-15T10:30:00"),
        )
        conn.commit()

        result = calculate_scan_range(conn, date(2026, 2, 2))

        assert result == ("2025-06", "2026-02")
        conn.close()

    def test_short_gap_scans_six_months_back(self, tmp_path: Path):
        """Gap <= 6 months: scan 6 months back."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        # Insert a plurk from 2025-12-31 (2 months ago from 2026-02-02)
        conn.execute(
            "INSERT INTO plurks (id, posted) VALUES (?, ?)",
            (1, "2025-12-31T23:59:59"),
        )
        conn.commit()

        result = calculate_scan_range(conn, date(2026, 2, 2))

        assert result == ("2025-08", "2026-02")
        conn.close()

    def test_exactly_six_months_gap(self, tmp_path: Path):
        """Gap == 6 months: should scan 6 months back (short gap behavior)."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        # Insert a plurk from 2025-08-02 (exactly 6 months ago from 2026-02-02)
        conn.execute(
            "INSERT INTO plurks (id, posted) VALUES (?, ?)",
            (1, "2025-08-02T10:00:00"),
        )
        conn.commit()

        result = calculate_scan_range(conn, date(2026, 2, 2))

        assert result == ("2025-08", "2026-02")
        conn.close()


class TestFilterPlurkFiles:
    """Tests for filter_plurk_files function."""

    def test_filter_none_returns_all(self, tmp_path: Path):
        """scan_start=None returns all files."""
        plurks_dir = tmp_path / "plurks"
        plurks_dir.mkdir()
        (plurks_dir / "2024_01.js").write_text("")
        (plurks_dir / "2025_06.js").write_text("")
        (plurks_dir / "2025_12.js").write_text("")

        files = filter_plurk_files(plurks_dir, None, None)

        assert len(files) == 3
        assert [f.stem for f in files] == ["2024_01", "2025_06", "2025_12"]

    def test_filter_by_range(self, tmp_path: Path):
        """Only files in scan range are returned."""
        plurks_dir = tmp_path / "plurks"
        plurks_dir.mkdir()
        (plurks_dir / "2025_01.js").write_text("")
        (plurks_dir / "2025_05.js").write_text("")  # before range
        (plurks_dir / "2025_06.js").write_text("")  # in range
        (plurks_dir / "2025_07.js").write_text("")  # in range
        (plurks_dir / "2025_08.js").write_text("")  # in range
        (plurks_dir / "2025_09.js").write_text("")  # after range

        files = filter_plurk_files(plurks_dir, "2025-06", "2025-08")

        assert [f.stem for f in files] == ["2025_06", "2025_07", "2025_08"]

    def test_filter_empty_directory(self, tmp_path: Path):
        """Empty directory returns empty list."""
        plurks_dir = tmp_path / "plurks"
        plurks_dir.mkdir()

        files = filter_plurk_files(plurks_dir, "2025-06", "2025-08")

        assert files == []

    def test_filter_no_matching_files(self, tmp_path: Path):
        """No files in range returns empty list."""
        plurks_dir = tmp_path / "plurks"
        plurks_dir.mkdir()
        (plurks_dir / "2020_01.js").write_text("")
        (plurks_dir / "2020_02.js").write_text("")

        files = filter_plurk_files(plurks_dir, "2025-06", "2025-08")

        assert files == []


class TestGetBaseIdsFromPlurks:
    """Tests for get_base_ids_from_plurks function."""

    def test_collect_base_ids(self, tmp_path: Path):
        """Collect base_ids from plurk files."""
        plurks_dir = tmp_path / "plurks"
        plurks_dir.mkdir()

        content1 = '''BackupData.plurks["2025_06"]=[{"id": 1, "base_id": "abc123"}, {"id": 2, "base_id": "def456"}];'''
        content2 = '''BackupData.plurks["2025_07"]=[{"id": 3, "base_id": "ghi789"}];'''

        (plurks_dir / "2025_06.js").write_text(content1)
        (plurks_dir / "2025_07.js").write_text(content2)

        files = [plurks_dir / "2025_06.js", plurks_dir / "2025_07.js"]
        base_ids = get_base_ids_from_plurks(files)

        assert base_ids == {"abc123", "def456", "ghi789"}

    def test_empty_files_list(self):
        """Empty files list returns empty set."""
        base_ids = get_base_ids_from_plurks([])

        assert base_ids == set()

    def test_plurk_without_base_id(self, tmp_path: Path):
        """Plurks without base_id are skipped."""
        plurks_dir = tmp_path / "plurks"
        plurks_dir.mkdir()

        content = '''BackupData.plurks["2025_06"]=[{"id": 1, "base_id": "abc"}, {"id": 2}];'''
        (plurks_dir / "2025_06.js").write_text(content)

        files = [plurks_dir / "2025_06.js"]
        base_ids = get_base_ids_from_plurks(files)

        assert base_ids == {"abc"}


class TestFilterResponseFiles:
    """Tests for filter_response_files function."""

    def test_filter_by_base_ids(self, tmp_path: Path):
        """Only response files matching base_ids are returned."""
        responses_dir = tmp_path / "responses"
        responses_dir.mkdir()
        (responses_dir / "abc123.js").write_text("")
        (responses_dir / "def456.js").write_text("")
        (responses_dir / "xyz999.js").write_text("")  # not in base_ids

        files = filter_response_files(responses_dir, {"abc123", "def456"})

        assert len(files) == 2
        assert set(f.stem for f in files) == {"abc123", "def456"}

    def test_empty_base_ids(self, tmp_path: Path):
        """Empty base_ids returns empty list."""
        responses_dir = tmp_path / "responses"
        responses_dir.mkdir()
        (responses_dir / "abc123.js").write_text("")

        files = filter_response_files(responses_dir, set())

        assert files == []

    def test_no_matching_files(self, tmp_path: Path):
        """No matching files returns empty list."""
        responses_dir = tmp_path / "responses"
        responses_dir.mkdir()
        (responses_dir / "xyz.js").write_text("")

        files = filter_response_files(responses_dir, {"abc", "def"})

        assert files == []


class TestInsertOrIgnore:
    """Tests for INSERT OR IGNORE behavior."""

    def test_insert_new_plurk(self, tmp_path: Path):
        """New plurk is inserted, returns rowcount=1."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        cursor = conn.execute(
            "INSERT OR IGNORE INTO plurks (id, content_raw, posted) VALUES (?, ?, ?)",
            (1, "test content", "2025-06-15T10:00:00"),
        )

        assert cursor.rowcount == 1

        # Verify inserted
        row = conn.execute("SELECT content_raw FROM plurks WHERE id = 1").fetchone()
        assert row[0] == "test content"
        conn.close()

    def test_ignore_existing_plurk(self, tmp_path: Path):
        """Existing plurk is skipped, returns rowcount=0."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        # Insert first
        conn.execute(
            "INSERT INTO plurks (id, content_raw, posted) VALUES (?, ?, ?)",
            (1, "original content", "2025-06-15T10:00:00"),
        )
        conn.commit()

        # Try to insert again with different content
        cursor = conn.execute(
            "INSERT OR IGNORE INTO plurks (id, content_raw, posted) VALUES (?, ?, ?)",
            (1, "new content", "2025-06-15T10:00:00"),
        )

        assert cursor.rowcount == 0

        # Verify original content preserved
        row = conn.execute("SELECT content_raw FROM plurks WHERE id = 1").fetchone()
        assert row[0] == "original content"
        conn.close()

    def test_insert_new_response(self, tmp_path: Path):
        """New response is inserted."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        cursor = conn.execute(
            "INSERT OR IGNORE INTO responses (id, base_id, content_raw, posted) VALUES (?, ?, ?, ?)",
            (100, "abc", "reply", "2025-06-15T11:00:00"),
        )

        assert cursor.rowcount == 1
        conn.close()

    def test_ignore_existing_response(self, tmp_path: Path):
        """Existing response is skipped."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        conn.execute(
            "INSERT INTO responses (id, base_id, content_raw, posted) VALUES (?, ?, ?, ?)",
            (100, "abc", "original reply", "2025-06-15T11:00:00"),
        )
        conn.commit()

        cursor = conn.execute(
            "INSERT OR IGNORE INTO responses (id, base_id, content_raw, posted) VALUES (?, ?, ?, ?)",
            (100, "abc", "new reply", "2025-06-15T11:00:00"),
        )

        assert cursor.rowcount == 0

        row = conn.execute("SELECT content_raw FROM responses WHERE id = 100").fetchone()
        assert row[0] == "original reply"
        conn.close()

    def test_mixed_new_and_existing(self, tmp_path: Path):
        """Mix of new and existing records."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        # Insert some existing records
        conn.execute("INSERT INTO plurks (id, content_raw, posted) VALUES (1, 'a', '2025-01-01')")
        conn.execute("INSERT INTO plurks (id, content_raw, posted) VALUES (2, 'b', '2025-01-02')")
        conn.commit()

        # Try to insert mix of new and existing
        new_count = 0
        skipped_count = 0

        for plurk_id, content in [(1, "a"), (2, "b"), (3, "c"), (4, "d"), (5, "e")]:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO plurks (id, content_raw, posted) VALUES (?, ?, ?)",
                (plurk_id, content, f"2025-01-0{plurk_id}"),
            )
            if cursor.rowcount == 1:
                new_count += 1
            else:
                skipped_count += 1

        assert new_count == 3  # ids 3, 4, 5
        assert skipped_count == 2  # ids 1, 2
        conn.close()
