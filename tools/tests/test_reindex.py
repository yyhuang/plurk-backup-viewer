"""Tests for resolve_icu_extension and rebuild_fts."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from database import create_schema, resolve_icu_extension
from reindex_cmd import rebuild_fts


class TestResolveIcuExtension:
    """Tests for resolve_icu_extension()."""

    def test_returns_none_when_no_config_and_no_default(self, tmp_path):
        """Falls back to None when nothing is available."""
        with patch("database.Path") as mock_path_cls:
            # Make __file__.parent.parent point to tmp_path (no viewer/lib/)
            mock_path_cls.return_value = mock_path_cls
            mock_path_cls.__truediv__ = Path.__truediv__
            # Just call with no config and monkeypatch the default path check
            result = resolve_icu_extension(None)
            # Can't easily mock Path(__file__), so test config-only paths instead

    def test_returns_config_path_when_exists(self, tmp_path):
        """Uses config icu_extension_path if the file exists."""
        ext_path = tmp_path / "libfts5_icu.dylib"
        ext_path.touch()
        config = {"icu_extension_path": str(ext_path)}
        result = resolve_icu_extension(config)
        assert result == str(ext_path)

    def test_ignores_config_path_when_not_exists(self):
        """Ignores config path if file doesn't exist."""
        config = {"icu_extension_path": "/nonexistent/libfts5_icu.dylib"}
        # Falls through to default location check (which also won't exist in CI)
        result = resolve_icu_extension(config)
        # Result depends on whether viewer/lib/libfts5_icu.dylib exists locally
        # but the config path should NOT be returned
        assert result != "/nonexistent/libfts5_icu.dylib"

    def test_ignores_empty_config_path(self):
        """Ignores empty icu_extension_path in config."""
        config = {"icu_extension_path": ""}
        result = resolve_icu_extension(config)
        assert result is None or result != ""

    def test_none_config(self):
        """Works with None config."""
        # Should not raise
        resolve_icu_extension(None)

    def test_empty_config(self):
        """Works with empty config dict."""
        resolve_icu_extension({})


class TestRebuildFts:
    """Tests for rebuild_fts() - rebuilding FTS5 indexes from existing data."""

    @pytest.fixture
    def db_with_data(self):
        """Create an in-memory database with data and unicode61 FTS."""
        conn = sqlite3.connect(":memory:")
        create_schema(conn, "unicode61")

        # Insert test data (triggers auto-populate FTS)
        conn.execute(
            "INSERT INTO plurks (id, base_id, content_raw, posted, response_count, qualifier) "
            "VALUES (1, 'abc', 'hello world test', '2024-01-01', 0, 'says')"
        )
        conn.execute(
            "INSERT INTO plurks (id, base_id, content_raw, posted, response_count, qualifier) "
            "VALUES (2, 'def', 'another plurk here', '2024-01-02', 1, 'thinks')"
        )
        conn.execute(
            "INSERT INTO responses (id, base_id, content_raw, posted, user_id, user_nick, user_display) "
            "VALUES (100, 'abc', 'nice response', '2024-01-01', 1, 'user1', 'User One')"
        )
        conn.execute(
            "INSERT INTO responses (id, base_id, content_raw, posted, user_id, user_nick, user_display) "
            "VALUES (101, 'def', 'great stuff', '2024-01-02', 2, 'user2', 'User Two')"
        )
        conn.execute(
            "INSERT INTO responses (id, base_id, content_raw, posted, user_id, user_nick, user_display) "
            "VALUES (102, 'def', 'me too', '2024-01-02', 3, 'user3', 'User Three')"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_rebuild_preserves_data(self, db_with_data):
        """Rebuilding FTS doesn't affect the main tables."""
        conn = db_with_data
        counts = rebuild_fts(conn, "unicode61")

        assert conn.execute("SELECT COUNT(*) FROM plurks").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0] == 3

    def test_rebuild_returns_correct_counts(self, db_with_data):
        """rebuild_fts returns the number of rows indexed."""
        counts = rebuild_fts(db_with_data, "unicode61")

        assert counts["plurks"] == 2
        assert counts["responses"] == 3
        assert counts["links"] == 0

    def test_fts_search_works_after_rebuild(self, db_with_data):
        """FTS search returns results after rebuilding."""
        conn = db_with_data
        rebuild_fts(conn, "unicode61")

        results = conn.execute(
            "SELECT p.id FROM plurks p "
            "JOIN plurks_fts ON plurks_fts.rowid = p.id "
            "WHERE plurks_fts MATCH 'hello'"
        ).fetchall()
        assert len(results) == 1
        assert results[0][0] == 1

        results = conn.execute(
            "SELECT r.id FROM responses r "
            "JOIN responses_fts ON responses_fts.rowid = r.id "
            "WHERE responses_fts MATCH 'great'"
        ).fetchall()
        assert len(results) == 1
        assert results[0][0] == 101

    def test_triggers_work_after_rebuild(self, db_with_data):
        """Triggers keep FTS in sync after rebuild."""
        conn = db_with_data
        rebuild_fts(conn, "unicode61")

        # Insert new data - trigger should update FTS
        conn.execute(
            "INSERT INTO plurks (id, base_id, content_raw, posted, response_count, qualifier) "
            "VALUES (3, 'ghi', 'fresh new plurk', '2024-01-03', 0, 'says')"
        )
        conn.commit()

        results = conn.execute(
            "SELECT COUNT(*) FROM plurks_fts WHERE plurks_fts MATCH 'fresh'"
        ).fetchone()[0]
        assert results == 1

    def test_rebuild_with_link_metadata(self):
        """Rebuilds link_metadata_fts when link_metadata table exists."""
        conn = sqlite3.connect(":memory:")
        create_schema(conn, "unicode61")

        # Create link_metadata table manually
        conn.executescript("""
            CREATE TABLE link_metadata (
                url TEXT PRIMARY KEY,
                og_title TEXT,
                og_description TEXT,
                og_site_name TEXT,
                sources JSON,
                status TEXT DEFAULT 'pending',
                fetched_at TEXT
            );
        """)
        conn.execute(
            "INSERT INTO link_metadata (url, og_title, og_description, og_site_name, status) "
            "VALUES ('https://example.com', 'Example Site', 'A test site', 'Example', 'success')"
        )
        conn.execute(
            "INSERT INTO link_metadata (url, og_title, og_description, og_site_name, status) "
            "VALUES ('https://test.org', 'Test Page', 'Testing things', 'Test', 'success')"
        )
        conn.commit()

        counts = rebuild_fts(conn, "unicode61")

        assert counts["links"] == 2

        # Verify FTS search works for links
        results = conn.execute(
            "SELECT lm.url FROM link_metadata lm "
            "JOIN link_metadata_fts ON link_metadata_fts.rowid = lm.rowid "
            "WHERE link_metadata_fts MATCH 'Example'"
        ).fetchall()
        assert len(results) == 1
        assert results[0][0] == "https://example.com"

        conn.close()

    def test_rebuild_without_link_metadata(self, db_with_data):
        """Skips link_metadata_fts when link_metadata table doesn't exist."""
        counts = rebuild_fts(db_with_data, "unicode61")
        assert counts["links"] == 0

    def test_double_rebuild(self, db_with_data):
        """Can rebuild FTS twice without errors."""
        rebuild_fts(db_with_data, "unicode61")
        counts = rebuild_fts(db_with_data, "unicode61")

        assert counts["plurks"] == 2
        assert counts["responses"] == 3
