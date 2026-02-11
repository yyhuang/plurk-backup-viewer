"""Tests for posted_ts column — epoch conversion, migration, and sort order."""

import sqlite3
from pathlib import Path

import pytest

from database import create_schema, ensure_posted_ts_column, to_epoch
from search_api import SearchDB


class TestToEpoch:
    """Tests for to_epoch() helper."""

    def test_rfc2822_date(self):
        # Wed, 31 Oct 2018 16:00:47 GMT → 1541001647
        result = to_epoch("Wed, 31 Oct 2018 16:00:47 GMT")
        assert result == 1541001647

    def test_different_day_of_week(self):
        # Thu, 01 Nov 2018 10:00:00 GMT → 1541066400
        result = to_epoch("Thu, 01 Nov 2018 10:00:00 GMT")
        assert result == 1541066400

    def test_none_input(self):
        assert to_epoch(None) is None

    def test_empty_string(self):
        assert to_epoch("") is None

    def test_invalid_string(self):
        assert to_epoch("not a date") is None

    def test_ordering_correctness(self):
        """Dates that sort wrong as strings should sort correctly as epochs."""
        # "Fri" < "Thu" < "Wed" alphabetically, but chronologically:
        # Wed Oct 31 < Thu Nov 1 < Fri Nov 2
        wed = to_epoch("Wed, 31 Oct 2018 16:00:47 GMT")
        thu = to_epoch("Thu, 01 Nov 2018 10:00:00 GMT")
        fri = to_epoch("Fri, 02 Nov 2018 12:00:00 GMT")
        assert wed < thu < fri


class TestEnsurePostedTsColumn:
    """Tests for ensure_posted_ts_column() migration."""

    def _create_legacy_db(self, tmp_path: Path) -> Path:
        """Create a DB without posted_ts (simulates old schema)."""
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE plurks (
                id INTEGER PRIMARY KEY,
                base_id TEXT,
                content_raw TEXT,
                posted TEXT,
                response_count INTEGER,
                qualifier TEXT
            );
            CREATE TABLE responses (
                id INTEGER PRIMARY KEY,
                base_id TEXT,
                content_raw TEXT,
                posted TEXT,
                user_id INTEGER,
                user_nick TEXT,
                user_display TEXT
            );
        """)
        conn.execute(
            "INSERT INTO plurks VALUES (1, 'abc', 'test', 'Wed, 31 Oct 2018 16:00:47 GMT', 0, 'says')"
        )
        conn.execute(
            "INSERT INTO plurks VALUES (2, 'def', 'test2', 'Thu, 01 Nov 2018 10:00:00 GMT', 0, 'says')"
        )
        conn.execute(
            "INSERT INTO responses VALUES (100, 'abc', 'reply', 'Wed, 31 Oct 2018 17:00:00 GMT', 1, 'user', 'User')"
        )
        conn.commit()
        conn.close()
        return db_path

    def test_adds_column_and_backfills(self, tmp_path: Path):
        db_path = self._create_legacy_db(tmp_path)
        conn = sqlite3.connect(db_path)
        ensure_posted_ts_column(conn)

        # Check column exists
        cols = {row[1] for row in conn.execute("PRAGMA table_info(plurks)").fetchall()}
        assert "posted_ts" in cols

        # Check backfill
        null_count = conn.execute(
            "SELECT COUNT(*) FROM plurks WHERE posted_ts IS NULL"
        ).fetchone()[0]
        assert null_count == 0

        # Check values
        row = conn.execute(
            "SELECT posted_ts FROM plurks WHERE id = 1"
        ).fetchone()
        assert row[0] == 1541001647

        # Responses too
        null_count = conn.execute(
            "SELECT COUNT(*) FROM responses WHERE posted_ts IS NULL"
        ).fetchone()[0]
        assert null_count == 0

        conn.close()

    def test_idempotent(self, tmp_path: Path):
        """Calling ensure_posted_ts_column twice should be safe."""
        db_path = self._create_legacy_db(tmp_path)
        conn = sqlite3.connect(db_path)
        ensure_posted_ts_column(conn)
        ensure_posted_ts_column(conn)  # Should not raise

        count = conn.execute("SELECT COUNT(*) FROM plurks").fetchone()[0]
        assert count == 2
        conn.close()

    def test_creates_index(self, tmp_path: Path):
        db_path = self._create_legacy_db(tmp_path)
        conn = sqlite3.connect(db_path)
        ensure_posted_ts_column(conn)

        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(plurks)").fetchall()
        }
        assert "idx_plurks_posted_ts" in indexes

        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(responses)").fetchall()
        }
        assert "idx_responses_posted_ts" in indexes
        conn.close()


class TestSearchOrdering:
    """Tests that search results come back in chronological order."""

    @pytest.fixture
    def db_with_varied_dates(self, tmp_path: Path):
        """Create DB with dates that sort differently as strings vs epochs."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        create_schema(conn)

        # These dates sort WRONG alphabetically by day name:
        # "Fri..." < "Mon..." < "Thu..." < "Wed..." (alpha)
        # But chronologically: Mon < Wed < Thu < Fri
        dates = [
            ("Fri, 02 Nov 2018 12:00:00 GMT", 1541160000),  # newest
            ("Mon, 29 Oct 2018 08:00:00 GMT", 1540800000),  # oldest
            ("Thu, 01 Nov 2018 10:00:00 GMT", 1541066400),
            ("Wed, 31 Oct 2018 16:00:47 GMT", 1540915247),
        ]
        for i, (posted, ts) in enumerate(dates):
            conn.execute(
                "INSERT INTO plurks (id, base_id, content_raw, posted, posted_ts, response_count, qualifier) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (i + 1, f"b{i}", f"content {i}", posted, ts, 0, "says"),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_fts_search_chronological_order(self, db_with_varied_dates: Path):
        db = SearchDB(db_with_varied_dates)
        result = db.search("content", "plurks", "fts", 0)

        posted_dates = [r["posted"] for r in result["results"]]
        # Should be newest first (Fri, Thu, Wed, Mon)
        assert posted_dates[0].startswith("Fri")
        assert posted_dates[1].startswith("Thu")
        assert posted_dates[2].startswith("Wed")
        assert posted_dates[3].startswith("Mon")
        db.close()

    def test_like_search_chronological_order(self, db_with_varied_dates: Path):
        db = SearchDB(db_with_varied_dates)
        result = db.search("content", "plurks", "like", 0)

        posted_dates = [r["posted"] for r in result["results"]]
        assert posted_dates[0].startswith("Fri")
        assert posted_dates[-1].startswith("Mon")
        db.close()
