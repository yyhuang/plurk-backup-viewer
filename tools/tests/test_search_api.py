"""Tests for search_api.py - server-side search via SearchDB."""

import sqlite3
from pathlib import Path

import pytest

from database import create_schema
from links_cmd import create_link_metadata_table, upsert_link, update_og_metadata, OGResult
from search_api import SearchDB


@pytest.fixture
def db_with_data(tmp_path: Path):
    """Create a database with test data and return the path."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    # Insert plurks
    conn.execute(
        "INSERT INTO plurks (id, base_id, content_raw, posted, response_count, qualifier) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "abc", "hello world plurk", "Wed, 31 Oct 2018 16:00:47 GMT", 2, "says"),
    )
    conn.execute(
        "INSERT INTO plurks (id, base_id, content_raw, posted, response_count, qualifier) VALUES (?, ?, ?, ?, ?, ?)",
        (2, "def", "another test plurk", "Thu, 01 Nov 2018 10:00:00 GMT", 0, "thinks"),
    )
    conn.execute(
        "INSERT INTO plurks (id, base_id, content_raw, posted, response_count, qualifier) VALUES (?, ?, ?, ?, ?, ?)",
        (3, "ghi", "unique keyword here", "Fri, 02 Nov 2018 12:00:00 GMT", 1, None),
    )

    # Insert responses
    conn.execute(
        "INSERT INTO responses (id, base_id, content_raw, posted, user_id, user_nick, user_display) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (100, "abc", "response hello", "Wed, 31 Oct 2018 17:00:00 GMT", 999, "responder", "Responder User"),
    )
    conn.execute(
        "INSERT INTO responses (id, base_id, content_raw, posted, user_id, user_nick, user_display) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (101, "abc", "another reply", "Wed, 31 Oct 2018 18:00:00 GMT", 999, "responder", "Responder User"),
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def db_with_links(db_with_data: Path):
    """Add link_metadata table with test data."""
    conn = sqlite3.connect(db_with_data)
    create_link_metadata_table(conn)

    upsert_link(conn, "https://example.com/page", {"plurk_ids": [1], "response_ids": []})
    update_og_metadata(conn, OGResult(
        url="https://example.com/page",
        status="success",
        title="Example Page",
        description="A test page description",
        site_name="Example",
    ))

    upsert_link(conn, "https://test.org/article", {"plurk_ids": [2], "response_ids": [100]})
    update_og_metadata(conn, OGResult(
        url="https://test.org/article",
        status="success",
        title="Test Article",
        description="An article about testing",
        site_name="TestOrg",
    ))

    upsert_link(conn, "https://pending.com", {"plurk_ids": [3], "response_ids": []})
    # Leave this one as pending (no OG fetch)

    conn.commit()
    conn.close()
    return db_with_data


class TestSearchDBStats:
    """Tests for get_stats()."""

    def test_stats_counts(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        stats = db.get_stats()

        assert stats["plurk_count"] == 3
        assert stats["response_count"] == 2
        assert stats["link_count"] == 0
        assert stats["link_with_og"] == 0
        db.close()

    def test_stats_with_links(self, db_with_links: Path):
        db = SearchDB(db_with_links)
        stats = db.get_stats()

        assert stats["plurk_count"] == 3
        assert stats["response_count"] == 2
        assert stats["link_count"] == 3
        assert stats["link_with_og"] == 2
        db.close()


class TestSearchDBFtsSearch:
    """Tests for FTS search."""

    def test_fts_search_plurks(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("hello", "plurks", "fts", 0)

        assert result["total"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["type"] == "plurk"
        assert result["results"][0]["content_raw"] == "hello world plurk"
        db.close()

    def test_fts_search_responses(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("hello", "responses", "fts", 0)

        assert result["total"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["type"] == "response"
        assert result["results"][0]["content_raw"] == "response hello"
        db.close()

    def test_fts_search_all(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("hello", "all", "fts", 0)

        assert result["total"] == 2
        assert len(result["results"]) == 2
        types = {r["type"] for r in result["results"]}
        assert types == {"plurk", "response"}
        db.close()

    def test_fts_search_no_results(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("nonexistent", "all", "fts", 0)

        assert result["total"] == 0
        assert len(result["results"]) == 0
        db.close()

    def test_fts_search_unique_keyword(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("unique", "plurks", "fts", 0)

        assert result["total"] == 1
        assert result["results"][0]["base_id"] == "ghi"
        db.close()


class TestSearchDBLikeSearch:
    """Tests for LIKE search."""

    def test_like_search_plurks(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("hello", "plurks", "like", 0)

        assert result["total"] == 1
        assert result["results"][0]["content_raw"] == "hello world plurk"
        db.close()

    def test_like_search_responses(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("reply", "responses", "like", 0)

        assert result["total"] == 1
        assert result["results"][0]["content_raw"] == "another reply"
        db.close()

    def test_like_search_all(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("hello", "all", "like", 0)

        assert result["total"] == 2
        db.close()

    def test_like_search_special_characters(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        # Should not crash with special LIKE characters
        result = db.search("test%", "all", "like", 0)
        assert isinstance(result["total"], int)
        db.close()


class TestSearchDBLinkSearch:
    """Tests for link search."""

    def test_fts_link_search(self, db_with_links: Path):
        db = SearchDB(db_with_links)
        result = db.search("Example", "links", "fts", 0)

        assert result["total"] >= 1
        assert result["results"][0]["type"] == "link"
        assert result["results"][0]["og_title"] == "Example Page"
        db.close()

    def test_like_link_search_by_url(self, db_with_links: Path):
        db = SearchDB(db_with_links)
        result = db.search("example.com", "links", "like", 0)

        assert result["total"] == 1
        assert result["results"][0]["url"] == "https://example.com/page"
        db.close()

    def test_like_link_search_by_description(self, db_with_links: Path):
        db = SearchDB(db_with_links)
        result = db.search("testing", "links", "like", 0)

        assert result["total"] == 1
        assert result["results"][0]["url"] == "https://test.org/article"
        db.close()

    def test_link_search_no_table(self, db_with_data: Path):
        """Search links when table doesn't exist returns error."""
        db = SearchDB(db_with_data)
        result = db.search("test", "links", "fts", 0)

        assert result["total"] == 0
        assert "error" in result
        db.close()

    def test_link_sources_parsed(self, db_with_links: Path):
        db = SearchDB(db_with_links)
        result = db.search("test.org", "links", "like", 0)

        assert result["total"] == 1
        sources = result["results"][0]["sources"]
        assert sources["plurk_ids"] == [2]
        assert sources["response_ids"] == [100]
        db.close()


class TestSearchDBPagination:
    """Tests for pagination."""

    def test_pagination_info(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("plurk", "plurks", "like", 0)

        assert result["page"] == 0
        assert result["pages"] >= 1
        db.close()

    def test_page_out_of_range(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.search("plurk", "plurks", "like", 999)

        assert result["results"] == []
        assert result["page"] == 999
        db.close()


class TestSearchDBPlurkLookup:
    """Tests for get_plurk()."""

    def test_get_existing_plurk(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.get_plurk(1)

        assert result is not None
        assert result["base_id"] == "abc"
        assert "posted" in result
        db.close()

    def test_get_nonexistent_plurk(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.get_plurk(9999)

        assert result is None
        db.close()


class TestSearchDBResponseLookup:
    """Tests for get_response_plurk()."""

    def test_get_response_plurk(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.get_response_plurk(100)

        assert result is not None
        assert result["base_id"] == "abc"
        assert "posted" in result
        db.close()

    def test_get_nonexistent_response(self, db_with_data: Path):
        db = SearchDB(db_with_data)
        result = db.get_response_plurk(9999)

        assert result is None
        db.close()


class TestSearchDBQueryBuilding:
    """Tests for query building static methods."""

    def test_build_fts_query_simple(self):
        assert SearchDB._build_fts_query("hello world") == '"hello"* "world"*'

    def test_build_fts_query_single_term(self):
        assert SearchDB._build_fts_query("hello") == '"hello"*'

    def test_build_fts_query_special_chars(self):
        # Double quotes should be escaped
        assert SearchDB._build_fts_query('he"llo') == '"he""llo"*'

    def test_build_like_pattern(self):
        assert SearchDB._build_like_pattern("hello") == "%hello%"

    def test_build_like_pattern_escapes_percent(self):
        assert SearchDB._build_like_pattern("100%") == "%100\\%%"

    def test_build_like_pattern_escapes_underscore(self):
        assert SearchDB._build_like_pattern("a_b") == "%a\\_b%"
