"""Tests for database.py (renamed from init_database.py)."""

import sqlite3
from pathlib import Path

import pytest

from database import create_schema, import_plurks, import_responses


class TestCreateSchema:
    """Tests for create_schema function."""

    def test_creates_plurks_table(self, tmp_path: Path):
        """Schema creates plurks table with correct columns."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        cursor = conn.execute("PRAGMA table_info(plurks)")
        columns = {row[1] for row in cursor.fetchall()}

        assert "id" in columns
        assert "base_id" in columns
        assert "content_raw" in columns
        assert "posted" in columns
        assert "response_count" in columns
        assert "qualifier" in columns
        conn.close()

    def test_creates_responses_table(self, tmp_path: Path):
        """Schema creates responses table with correct columns."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        cursor = conn.execute("PRAGMA table_info(responses)")
        columns = {row[1] for row in cursor.fetchall()}

        assert "id" in columns
        assert "base_id" in columns
        assert "content_raw" in columns
        assert "posted" in columns
        assert "user_id" in columns
        assert "user_nick" in columns
        assert "user_display" in columns
        conn.close()

    def test_creates_fts_tables(self, tmp_path: Path):
        """Schema creates FTS5 virtual tables."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        # Check FTS tables exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'"
        )
        tables = {row[0] for row in cursor.fetchall()}

        assert "plurks_fts" in tables
        assert "responses_fts" in tables
        conn.close()


class TestImportPluks:
    """Tests for import_plurks function."""

    def test_import_plurks_basic(self, tmp_path: Path):
        """Import plurks from file list."""
        # Create test backup structure
        plurks_dir = tmp_path / "backup" / "data" / "plurks"
        plurks_dir.mkdir(parents=True)

        # Create test plurk file
        content = '''BackupData.plurks["2008_12"]=[{"id": 1, "base_id": "abc", "content_raw": "test", "posted": "Wed, 31 Dec 2008", "response_count": 5, "qualifier": "says"}];'''
        plurk_file = plurks_dir / "2008_12.js"
        plurk_file.write_text(content)

        # Create database and import
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)
        new_count, skipped_count = import_plurks(conn, [plurk_file])
        conn.commit()

        assert new_count == 1
        assert skipped_count == 0

        # Verify data
        cursor = conn.execute("SELECT id, base_id, content_raw FROM plurks")
        row = cursor.fetchone()
        assert row[0] == 1
        assert row[1] == "abc"
        assert row[2] == "test"
        conn.close()

    def test_import_plurks_fts_populated(self, tmp_path: Path):
        """FTS index is populated when importing plurks."""
        plurks_dir = tmp_path / "backup" / "data" / "plurks"
        plurks_dir.mkdir(parents=True)

        content = '''BackupData.plurks["2008_12"]=[{"id": 1, "base_id": "a", "content_raw": "hello world"}];'''
        plurk_file = plurks_dir / "2008_12.js"
        plurk_file.write_text(content)

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)
        import_plurks(conn, [plurk_file])
        conn.commit()

        # Search using FTS
        cursor = conn.execute(
            "SELECT rowid FROM plurks_fts WHERE plurks_fts MATCH 'hello'"
        )
        results = cursor.fetchall()
        assert len(results) == 1
        assert results[0][0] == 1
        conn.close()


class TestImportResponses:
    """Tests for import_responses function."""

    def test_import_responses_basic(self, tmp_path: Path):
        """Import responses from file list."""
        responses_dir = tmp_path / "backup" / "data" / "responses"
        responses_dir.mkdir(parents=True)

        content = '''BackupData.responses["abc"]=[{"id": 100, "content_raw": "reply", "posted": "Thu, 11 Jun 2009", "user": {"id": 123, "nick_name": "user1", "display_name": "User One"}}];'''
        response_file = responses_dir / "abc.js"
        response_file.write_text(content)

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)
        new_count, skipped_count = import_responses(conn, [response_file])
        conn.commit()

        assert new_count == 1
        assert skipped_count == 0

        cursor = conn.execute(
            "SELECT id, base_id, content_raw, user_nick FROM responses"
        )
        row = cursor.fetchone()
        assert row[0] == 100
        assert row[1] == "abc"
        assert row[2] == "reply"
        assert row[3] == "user1"
        conn.close()

    def test_import_responses_fts_populated(self, tmp_path: Path):
        """FTS index is populated when importing responses."""
        responses_dir = tmp_path / "backup" / "data" / "responses"
        responses_dir.mkdir(parents=True)

        content = '''BackupData.responses["x"]=[{"id": 1, "content_raw": "unique keyword here", "user": {"id": 1, "nick_name": "u"}}];'''
        response_file = responses_dir / "x.js"
        response_file.write_text(content)

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)
        import_responses(conn, [response_file])
        conn.commit()

        cursor = conn.execute(
            "SELECT rowid FROM responses_fts WHERE responses_fts MATCH 'keyword'"
        )
        results = cursor.fetchall()
        assert len(results) == 1
        conn.close()
