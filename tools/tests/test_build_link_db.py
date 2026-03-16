"""Tests for links_cmd.py (renamed from build_link_db.py) - URL extraction and OG metadata fetching."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from links_cmd import (
    PLURK_URL_PATTERN,
    create_link_metadata_table,
    ensure_source_month_column,
    extract_links_from_files,
    extract_urls,
    is_image_content_type,
    is_image_url,
    is_own_plurk_url,
    process_plurk_file,
    process_response_file,
    update_og_metadata,
    upsert_link,
    OGResult,
)


class TestExtractUrls:
    """Tests for URL extraction from content."""

    def test_extract_single_url(self):
        """Extract a single URL from content."""
        content = "Check this out: https://example.com/page"
        urls = extract_urls(content)
        assert urls == ["https://example.com/page"]

    def test_extract_multiple_urls(self):
        """Extract multiple URLs from content."""
        content = "Links: https://a.com and http://b.com/path"
        urls = extract_urls(content)
        assert urls == ["https://a.com", "http://b.com/path"]

    def test_extract_no_urls(self):
        """Return empty list when no URLs present."""
        content = "Just some text without links"
        urls = extract_urls(content)
        assert urls == []

    def test_extract_url_with_query_params(self):
        """Extract URL with query parameters."""
        content = "https://youtube.com/watch?v=dQw4w9WgXcQ"
        urls = extract_urls(content)
        assert urls == ["https://youtube.com/watch?v=dQw4w9WgXcQ"]

    def test_extract_url_with_chinese_text(self):
        """Extract URL surrounded by Chinese text."""
        content = "看這個 https://example.com 很有趣"
        urls = extract_urls(content)
        assert urls == ["https://example.com"]

    def test_extract_plurk_url(self):
        """Extract Plurk URL format."""
        content = "https://www.plurk.com/p/mz33tg # 就是這樣!"
        urls = extract_urls(content)
        assert urls == ["https://www.plurk.com/p/mz33tg"]

    def test_extract_url_with_hash_fragment(self):
        """Extract URL with hash fragment."""
        content = "See https://example.com/page#section here"
        urls = extract_urls(content)
        assert urls == ["https://example.com/page#section"]


class TestIsImageUrl:
    """Tests for image URL detection."""

    def test_jpg_extension(self):
        """Detect .jpg as image."""
        assert is_image_url("https://example.com/photo.jpg") is True

    def test_jpeg_extension(self):
        """Detect .jpeg as image."""
        assert is_image_url("https://example.com/photo.jpeg") is True

    def test_png_extension(self):
        """Detect .png as image."""
        assert is_image_url("https://example.com/image.png") is True

    def test_gif_extension(self):
        """Detect .gif as image."""
        assert is_image_url("https://example.com/animation.gif") is True

    def test_webp_extension(self):
        """Detect .webp as image."""
        assert is_image_url("https://example.com/image.webp") is True

    def test_bmp_extension(self):
        """Detect .bmp as image."""
        assert is_image_url("https://example.com/image.bmp") is True

    def test_svg_extension(self):
        """Detect .svg as image."""
        assert is_image_url("https://example.com/icon.svg") is True

    def test_uppercase_extension(self):
        """Detect uppercase extensions."""
        assert is_image_url("https://example.com/PHOTO.JPG") is True
        assert is_image_url("https://example.com/image.PNG") is True

    def test_extension_with_query_params(self):
        """Detect image with query parameters."""
        assert is_image_url("https://example.com/photo.jpg?size=large") is True

    def test_html_page_not_image(self):
        """HTML page is not an image."""
        assert is_image_url("https://example.com/page.html") is False

    def test_no_extension_not_image(self):
        """URL without extension is not detected as image."""
        assert is_image_url("https://example.com/page") is False

    def test_video_not_image(self):
        """Video files are not images."""
        assert is_image_url("https://example.com/video.mp4") is False

    def test_pdf_not_image(self):
        """PDF is not an image."""
        assert is_image_url("https://example.com/doc.pdf") is False


class TestIsImageContentType:
    """Tests for Content-Type based image detection."""

    def test_image_jpeg(self):
        """Detect image/jpeg as image."""
        assert is_image_content_type("image/jpeg") is True

    def test_image_png(self):
        """Detect image/png as image."""
        assert is_image_content_type("image/png") is True

    def test_image_gif(self):
        """Detect image/gif as image."""
        assert is_image_content_type("image/gif") is True

    def test_image_webp(self):
        """Detect image/webp as image."""
        assert is_image_content_type("image/webp") is True

    def test_image_svg(self):
        """Detect image/svg+xml as image."""
        assert is_image_content_type("image/svg+xml") is True

    def test_content_type_with_charset(self):
        """Detect image with charset parameter."""
        assert is_image_content_type("image/png; charset=utf-8") is True

    def test_text_html_not_image(self):
        """text/html is not an image."""
        assert is_image_content_type("text/html") is False

    def test_application_json_not_image(self):
        """application/json is not an image."""
        assert is_image_content_type("application/json") is False

    def test_none_content_type(self):
        """None content type is not an image."""
        assert is_image_content_type(None) is False

    def test_empty_content_type(self):
        """Empty content type is not an image."""
        assert is_image_content_type("") is False


class TestProcessPlurkFile:
    """Tests for processing plurk files."""

    def test_process_plurk_file_with_urls(self, tmp_path: Path):
        """Extract URLs and plurk IDs from plurk file."""
        content = '''BackupData.plurks["2018_10"]=[{"id": 123, "base_id": "abc", "content_raw": "Check https://example.com"}, {"id": 456, "base_id": "def", "content_raw": "No links here"}];'''
        file = tmp_path / "2018_10.js"
        file.write_text(content)

        url_sources = process_plurk_file(file)

        assert "https://example.com" in url_sources
        assert url_sources["https://example.com"] == {"plurk_ids": [123], "response_ids": [], "month": "2018_10"}

    def test_process_plurk_file_multiple_urls_same_plurk(self, tmp_path: Path):
        """Handle multiple URLs in same plurk."""
        content = '''BackupData.plurks["2018_10"]=[{"id": 123, "base_id": "abc", "content_raw": "See https://a.com and https://b.com"}];'''
        file = tmp_path / "2018_10.js"
        file.write_text(content)

        url_sources = process_plurk_file(file)

        assert "https://a.com" in url_sources
        assert "https://b.com" in url_sources
        assert url_sources["https://a.com"]["plurk_ids"] == [123]

    def test_process_plurk_file_same_url_multiple_plurks(self, tmp_path: Path):
        """Same URL in multiple plurks collects all IDs."""
        content = '''BackupData.plurks["2018_10"]=[{"id": 123, "base_id": "abc", "content_raw": "https://shared.com"}, {"id": 456, "base_id": "def", "content_raw": "https://shared.com again"}];'''
        file = tmp_path / "2018_10.js"
        file.write_text(content)

        url_sources = process_plurk_file(file)

        assert url_sources["https://shared.com"]["plurk_ids"] == [123, 456]


class TestProcessResponseFile:
    """Tests for processing response files."""

    def test_process_response_file_with_urls(self, tmp_path: Path):
        """Extract URLs and response IDs from response file."""
        content = '''BackupData.responses["abc"]=[{"id": 789, "content_raw": "Reply with https://example.com", "user": {"id": 1, "nick_name": "test"}}];'''
        file = tmp_path / "abc.js"
        file.write_text(content)

        url_sources = process_response_file(file)

        assert "https://example.com" in url_sources
        assert url_sources["https://example.com"] == {"plurk_ids": [], "response_ids": [789], "month": None}


class TestUpsertLink:
    """Tests for upserting links to database."""

    @pytest.fixture
    def db(self):
        """Create in-memory database with schema."""
        conn = sqlite3.connect(":memory:")
        create_link_metadata_table(conn)
        yield conn
        conn.close()

    def test_insert_new_link(self, db: sqlite3.Connection):
        """Insert a new URL into database."""
        sources = {"plurk_ids": [123], "response_ids": []}
        upsert_link(db, "https://example.com", sources)

        row = db.execute("SELECT url, sources, status FROM link_metadata").fetchone()
        assert row[0] == "https://example.com"
        assert json.loads(row[1]) == sources
        assert row[2] == "pending"

    def test_merge_existing_link(self, db: sqlite3.Connection):
        """Merge sources when URL already exists."""
        # Insert initial
        upsert_link(db, "https://example.com", {"plurk_ids": [123], "response_ids": []})

        # Upsert with additional sources
        upsert_link(db, "https://example.com", {"plurk_ids": [456], "response_ids": [789]})

        row = db.execute("SELECT sources FROM link_metadata WHERE url = ?", ("https://example.com",)).fetchone()
        sources = json.loads(row[0])
        assert sorted(sources["plurk_ids"]) == [123, 456]
        assert sources["response_ids"] == [789]

    def test_no_duplicate_ids(self, db: sqlite3.Connection):
        """Don't add duplicate IDs when merging."""
        upsert_link(db, "https://example.com", {"plurk_ids": [123], "response_ids": []})
        upsert_link(db, "https://example.com", {"plurk_ids": [123], "response_ids": []})

        row = db.execute("SELECT sources FROM link_metadata WHERE url = ?", ("https://example.com",)).fetchone()
        sources = json.loads(row[0])
        assert sources["plurk_ids"] == [123]

    def test_insert_image_url_sets_image_status(self, db: sqlite3.Connection):
        """Image URLs should have status 'image'."""
        sources = {"plurk_ids": [123], "response_ids": []}
        upsert_link(db, "https://example.com/photo.jpg", sources)

        row = db.execute("SELECT status FROM link_metadata WHERE url = ?",
                        ("https://example.com/photo.jpg",)).fetchone()
        assert row[0] == "image"

    def test_insert_non_image_url_sets_pending_status(self, db: sqlite3.Connection):
        """Non-image URLs should have status 'pending'."""
        sources = {"plurk_ids": [123], "response_ids": []}
        upsert_link(db, "https://example.com/page", sources)

        row = db.execute("SELECT status FROM link_metadata WHERE url = ?",
                        ("https://example.com/page",)).fetchone()
        assert row[0] == "pending"


class TestCreateLinkMetadataTable:
    """Tests for table creation."""

    def test_create_table(self):
        """Create link_metadata table with correct schema."""
        conn = sqlite3.connect(":memory:")
        create_link_metadata_table(conn)

        # Check table exists
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata'"
        ).fetchone()
        assert result is not None

        # Check columns
        cols = conn.execute("PRAGMA table_info(link_metadata)").fetchall()
        col_names = [c[1] for c in cols]
        assert "url" in col_names
        assert "og_title" in col_names
        assert "og_description" in col_names
        assert "og_site_name" in col_names
        assert "sources" in col_names
        assert "status" in col_names
        assert "fetched_at" in col_names
        assert "source_month" in col_names

        # Check FTS5 table exists
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata_fts'"
        ).fetchone()
        assert result is not None
        conn.close()

    def test_create_table_idempotent(self):
        """Creating table twice doesn't error."""
        conn = sqlite3.connect(":memory:")
        create_link_metadata_table(conn)
        create_link_metadata_table(conn)  # Should not raise
        conn.close()


class TestSourceMonth:
    """Tests for source_month tracking."""

    @pytest.fixture
    def db(self):
        """Create in-memory database with schema."""
        conn = sqlite3.connect(":memory:")
        create_link_metadata_table(conn)
        yield conn
        conn.close()

    def test_upsert_stores_month(self, db: sqlite3.Connection):
        """Upsert stores source_month on insert."""
        sources = {"plurk_ids": [123], "response_ids": []}
        upsert_link(db, "https://example.com", sources, month="2024_01")

        row = db.execute("SELECT source_month FROM link_metadata WHERE url = ?",
                        ("https://example.com",)).fetchone()
        assert row[0] == "2024_01"

    def test_upsert_keeps_newer_month(self, db: sqlite3.Connection):
        """Merge keeps the newer month."""
        upsert_link(db, "https://example.com", {"plurk_ids": [1], "response_ids": []}, month="2020_01")
        upsert_link(db, "https://example.com", {"plurk_ids": [2], "response_ids": []}, month="2024_06")

        row = db.execute("SELECT source_month FROM link_metadata WHERE url = ?",
                        ("https://example.com",)).fetchone()
        assert row[0] == "2024_06"

    def test_upsert_does_not_downgrade_month(self, db: sqlite3.Connection):
        """Merge does not downgrade to an older month."""
        upsert_link(db, "https://example.com", {"plurk_ids": [1], "response_ids": []}, month="2024_06")
        upsert_link(db, "https://example.com", {"plurk_ids": [2], "response_ids": []}, month="2020_01")

        row = db.execute("SELECT source_month FROM link_metadata WHERE url = ?",
                        ("https://example.com",)).fetchone()
        assert row[0] == "2024_06"

    def test_upsert_null_month_does_not_overwrite(self, db: sqlite3.Connection):
        """Merge with None month does not overwrite existing month."""
        upsert_link(db, "https://example.com", {"plurk_ids": [1], "response_ids": []}, month="2024_01")
        upsert_link(db, "https://example.com", {"plurk_ids": [2], "response_ids": []}, month=None)

        row = db.execute("SELECT source_month FROM link_metadata WHERE url = ?",
                        ("https://example.com",)).fetchone()
        assert row[0] == "2024_01"

    def test_upsert_upgrades_from_null(self, db: sqlite3.Connection):
        """Merge upgrades from NULL to a real month."""
        upsert_link(db, "https://example.com", {"plurk_ids": [1], "response_ids": []}, month=None)
        upsert_link(db, "https://example.com", {"plurk_ids": [2], "response_ids": []}, month="2024_01")

        row = db.execute("SELECT source_month FROM link_metadata WHERE url = ?",
                        ("https://example.com",)).fetchone()
        assert row[0] == "2024_01"

    def test_ensure_source_month_column_adds_column(self):
        """ensure_source_month_column adds column to existing table without it."""
        conn = sqlite3.connect(":memory:")
        # Create old schema without source_month
        conn.execute("""
            CREATE TABLE link_metadata (
                url TEXT PRIMARY KEY,
                og_title TEXT,
                sources JSON,
                status TEXT DEFAULT 'pending'
            )
        """)
        ensure_source_month_column(conn)

        cols = conn.execute("PRAGMA table_info(link_metadata)").fetchall()
        col_names = [c[1] for c in cols]
        assert "source_month" in col_names
        conn.close()

    def test_ensure_source_month_column_idempotent(self):
        """ensure_source_month_column is safe to call on new schema."""
        conn = sqlite3.connect(":memory:")
        create_link_metadata_table(conn)
        # Should not raise even though column already exists
        ensure_source_month_column(conn)
        conn.close()

    def test_merge_url_sources_keeps_max_month(self):
        """merge_url_sources keeps the newest month."""
        from links_cmd import merge_url_sources

        base = {
            "https://a.com": {"plurk_ids": [1], "response_ids": [], "month": "2020_01"},
        }
        new = {
            "https://a.com": {"plurk_ids": [2], "response_ids": [], "month": "2024_06"},
        }
        result = merge_url_sources(base, new)
        assert result["https://a.com"]["month"] == "2024_06"

    def test_merge_url_sources_none_does_not_downgrade(self):
        """merge_url_sources with None month preserves existing."""
        from links_cmd import merge_url_sources

        base = {
            "https://a.com": {"plurk_ids": [1], "response_ids": [], "month": "2020_01"},
        }
        new = {
            "https://a.com": {"plurk_ids": [], "response_ids": [5], "month": None},
        }
        result = merge_url_sources(base, new)
        assert result["https://a.com"]["month"] == "2020_01"


class TestOGFetcherTitleFallback:
    """Tests for <title> fallback when OG metadata is missing."""

    def _make_fetcher_with_mock(self, evaluate_return, content_type="text/html"):
        """Create an OGFetcher with mocked Playwright internals."""
        from unittest.mock import MagicMock

        from links_cmd import OGFetcher

        fetcher = OGFetcher.__new__(OGFetcher)
        fetcher.timeout = 10000
        fetcher.retries = 3

        mock_response = MagicMock()
        mock_response.headers = {"content-type": content_type}

        mock_page = MagicMock()
        mock_page.goto.return_value = mock_response
        mock_page.evaluate.return_value = evaluate_return

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        fetcher._context = mock_context

        return fetcher

    def test_og_title_preferred_over_page_title(self):
        """OG title takes precedence over <title>."""
        fetcher = self._make_fetcher_with_mock(
            {"og": {"title": "OG Title", "description": "desc"}, "title": "Page Title"}
        )
        result = fetcher._fetch_once("https://example.com")
        assert result.status == "success"
        assert result.title == "OG Title"
        assert result.description == "desc"

    def test_page_title_fallback_when_no_og(self):
        """Use <title> when no OG tags exist."""
        fetcher = self._make_fetcher_with_mock(
            {"og": {}, "title": "My Page Title"}
        )
        result = fetcher._fetch_once("https://example.com")
        assert result.status == "success"
        assert result.title == "My Page Title"
        assert result.description is None

    def test_page_title_fallback_when_og_title_missing(self):
        """Use <title> when OG exists but og:title is missing."""
        fetcher = self._make_fetcher_with_mock(
            {"og": {"description": "Some description"}, "title": "Fallback Title"}
        )
        result = fetcher._fetch_once("https://example.com")
        assert result.status == "success"
        assert result.title == "Fallback Title"
        assert result.description == "Some description"

    def test_no_og_no_title(self):
        """Return no_og when neither OG nor <title> exists."""
        fetcher = self._make_fetcher_with_mock(
            {"og": {}, "title": ""}
        )
        result = fetcher._fetch_once("https://example.com")
        assert result.status == "no_og"

    def test_whitespace_only_title_ignored(self):
        """Whitespace-only <title> is treated as empty."""
        fetcher = self._make_fetcher_with_mock(
            {"og": {}, "title": "   "}
        )
        result = fetcher._fetch_once("https://example.com")
        assert result.status == "no_og"

    def test_image_content_type_still_returns_image(self):
        """Image content-type takes priority over title fallback."""
        fetcher = self._make_fetcher_with_mock(
            {"og": {}, "title": "Some Title"}, content_type="image/jpeg"
        )
        result = fetcher._fetch_once("https://example.com/photo")
        assert result.status == "image"


class TestPlurkUrlPattern:
    """Tests for Plurk URL pattern matching."""

    def test_standard_plurk_url(self):
        """Match standard plurk.com/p/ URL."""
        match = PLURK_URL_PATTERN.match("https://www.plurk.com/p/3hjsoumvig")
        assert match is not None
        assert match.group(1) == "3hjsoumvig"

    def test_mobile_plurk_url(self):
        """Match mobile plurk.com/m/p/ URL."""
        match = PLURK_URL_PATTERN.match("https://www.plurk.com/m/p/3hjsoumvig")
        assert match is not None
        assert match.group(1) == "3hjsoumvig"

    def test_without_www(self):
        """Match plurk.com without www prefix."""
        match = PLURK_URL_PATTERN.match("https://plurk.com/p/abc123")
        assert match is not None
        assert match.group(1) == "abc123"

    def test_http_scheme(self):
        """Match http:// (not just https://)."""
        match = PLURK_URL_PATTERN.match("http://www.plurk.com/p/abc123")
        assert match is not None

    def test_non_plurk_url(self):
        """Don't match non-Plurk URLs."""
        match = PLURK_URL_PATTERN.match("https://example.com/page")
        assert match is None

    def test_plurk_profile_url(self):
        """Don't match Plurk profile URLs (no /p/ segment)."""
        match = PLURK_URL_PATTERN.match("https://www.plurk.com/username")
        assert match is None


class TestIsOwnPlurkUrl:
    """Tests for own-plurk URL detection."""

    @pytest.fixture
    def db_with_plurks(self):
        """Create in-memory DB with plurks table and sample data."""
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE plurks (
                id INTEGER PRIMARY KEY,
                base_id TEXT,
                content_raw TEXT,
                posted TEXT,
                response_count INTEGER,
                qualifier TEXT
            )
        """)
        # Insert a plurk with known ID
        # "bsmqk" in base36 = 19811612 in decimal
        conn.execute(
            "INSERT INTO plurks (id, base_id, content_raw) VALUES (?, ?, ?)",
            (19811612, "bsmqk", "Test content"),
        )
        yield conn
        conn.close()

    def test_own_plurk_url_found(self, db_with_plurks):
        """Detect URL pointing to own plurk."""
        # 19811612 in base36 = "bsmqk"
        assert is_own_plurk_url("https://www.plurk.com/p/bsmqk", db_with_plurks) is True

    def test_own_plurk_mobile_url_found(self, db_with_plurks):
        """Detect mobile URL pointing to own plurk."""
        assert is_own_plurk_url("https://www.plurk.com/m/p/bsmqk", db_with_plurks) is True

    def test_other_plurk_url_not_found(self, db_with_plurks):
        """Don't match URL pointing to someone else's plurk."""
        assert is_own_plurk_url("https://www.plurk.com/p/zzzzz", db_with_plurks) is False

    def test_non_plurk_url(self, db_with_plurks):
        """Return False for non-Plurk URLs."""
        assert is_own_plurk_url("https://example.com/page", db_with_plurks) is False

    def test_image_url_not_matched(self, db_with_plurks):
        """Return False for image URLs."""
        assert is_own_plurk_url("https://example.com/photo.jpg", db_with_plurks) is False


class TestExtractSkipsOwnPlurks:
    """Tests for skipping own-plurk URLs during extract/upsert."""

    @pytest.fixture
    def db_with_plurks(self):
        """Create DB with plurks table and link_metadata table."""
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE plurks (
                id INTEGER PRIMARY KEY,
                base_id TEXT,
                content_raw TEXT,
                posted TEXT,
                response_count INTEGER,
                qualifier TEXT
            )
        """)
        # "bsmqk" in base36 = 19811612
        conn.execute(
            "INSERT INTO plurks (id, base_id, content_raw) VALUES (?, ?, ?)",
            (19811612, "bsmqk", "Test content"),
        )
        create_link_metadata_table(conn)
        yield conn
        conn.close()

    def test_own_plurk_url_not_inserted(self, db_with_plurks):
        """Own-plurk URL should be filtered before upsert."""
        url = "https://www.plurk.com/p/bsmqk"
        sources = {"plurk_ids": [999], "response_ids": []}

        # Simulate extract filtering logic
        if not is_own_plurk_url(url, db_with_plurks):
            upsert_link(db_with_plurks, url, sources)

        row = db_with_plurks.execute(
            "SELECT COUNT(*) FROM link_metadata WHERE url = ?", (url,)
        ).fetchone()
        assert row[0] == 0

    def test_external_url_still_inserted(self, db_with_plurks):
        """Non-own URLs should still be inserted."""
        url = "https://example.com/article"
        sources = {"plurk_ids": [999], "response_ids": []}

        if not is_own_plurk_url(url, db_with_plurks):
            upsert_link(db_with_plurks, url, sources)

        row = db_with_plurks.execute(
            "SELECT COUNT(*) FROM link_metadata WHERE url = ?", (url,)
        ).fetchone()
        assert row[0] == 1


class TestExtractLinksFromFiles:
    """Tests for extract_links_from_files() reusable function."""

    def _setup_backup(self, tmp_path: Path):
        """Create minimal backup files with known URLs."""
        plurk_file = tmp_path / "2018_10.js"
        plurk_file.write_text(
            'BackupData.plurks["2018_10"]=['
            '{"id": 100, "base_id": "abc", "content_raw": "See https://example.com/article"},'
            '{"id": 200, "base_id": "def", "content_raw": "Image https://example.com/photo.jpg"}'
            '];'
        )
        response_file = tmp_path / "abc.js"
        response_file.write_text(
            'BackupData.responses["abc"]=['
            '{"id": 301, "content_raw": "Reply with https://example.com/article", "user": {"id": 1, "nick_name": "test"}}'
            '];'
        )
        return [plurk_file], [response_file]

    def test_basic_extraction(self, tmp_path: Path):
        """Extract links from plurk and response files."""
        plurk_files, response_files = self._setup_backup(tmp_path)
        db_path = tmp_path / "test.db"

        # Create plurks table (needed for own-plurk URL check)
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE plurks (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        result = extract_links_from_files(
            plurk_files=plurk_files,
            response_files=response_files,
            db_path=db_path,
        )

        assert result["new_count"] == 2  # example.com/article + photo.jpg
        assert result["total_urls"] == 2
        assert result["image_count"] == 1  # photo.jpg
        assert result["own_plurk_count"] == 0

    def test_merged_sources(self, tmp_path: Path):
        """Same URL in plurk and response merges source IDs."""
        plurk_files, response_files = self._setup_backup(tmp_path)
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE plurks (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        extract_links_from_files(
            plurk_files=plurk_files,
            response_files=response_files,
            db_path=db_path,
        )

        # Check that example.com/article has both plurk and response sources
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT sources FROM link_metadata WHERE url = ?",
            ("https://example.com/article",),
        ).fetchone()
        conn.close()

        sources = json.loads(row[0])
        assert 100 in sources["plurk_ids"]
        assert 301 in sources["response_ids"]

    def test_idempotent_rerun(self, tmp_path: Path):
        """Running twice reports 0 new, N merged."""
        plurk_files, response_files = self._setup_backup(tmp_path)
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE plurks (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        # First run
        result1 = extract_links_from_files(
            plurk_files=plurk_files,
            response_files=response_files,
            db_path=db_path,
        )
        assert result1["new_count"] == 2

        # Second run — all merged, none new
        result2 = extract_links_from_files(
            plurk_files=plurk_files,
            response_files=response_files,
            db_path=db_path,
        )
        assert result2["new_count"] == 0
        assert result2["merged_count"] == 2

    def test_progress_callback(self, tmp_path: Path):
        """Progress callback receives messages."""
        plurk_files, response_files = self._setup_backup(tmp_path)
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE plurks (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        messages: list[str] = []
        extract_links_from_files(
            plurk_files=plurk_files,
            response_files=response_files,
            db_path=db_path,
            progress_callback=messages.append,
        )

        assert len(messages) > 0
        assert any("plurk" in m.lower() for m in messages)
        assert any("response" in m.lower() for m in messages)

    def test_own_plurk_urls_skipped(self, tmp_path: Path):
        """Own-plurk URLs are not inserted."""
        # Create a plurk that contains a URL to itself
        # "2s" in base36 = 100 in decimal
        plurk_file = tmp_path / "2018_10.js"
        plurk_file.write_text(
            'BackupData.plurks["2018_10"]=['
            '{"id": 100, "base_id": "abc", "content_raw": "Check https://www.plurk.com/p/2s"}'
            '];'
        )
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE plurks (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO plurks (id) VALUES (100)")
        conn.commit()
        conn.close()

        result = extract_links_from_files(
            plurk_files=[plurk_file],
            response_files=[],
            db_path=db_path,
        )

        assert result["own_plurk_count"] == 1
        assert result["new_count"] == 0


class TestICUExtensionLoading:
    """Tests that ICU extension is loaded when writing to FTS-triggered tables.

    The link_metadata_fts table may use 'icu zh' tokenizer. Any INSERT/UPDATE
    on link_metadata fires FTS triggers that need the ICU extension loaded.
    Without it: 'no such tokenizer: icu'.
    """

    def _setup_db_with_icu_fts(self, db_path: Path) -> None:
        """Create a DB where link_metadata_fts uses 'icu zh' tokenizer.

        We can't actually create with 'icu zh' (no extension in tests),
        so we simulate the scenario: create with unicode61, then verify
        the code paths that load ICU are exercised.
        """
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE plurks (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

    def _setup_backup(self, tmp_path: Path) -> tuple[list[Path], list[Path]]:
        """Create minimal backup files with a URL."""
        plurk_file = tmp_path / "2018_10.js"
        plurk_file.write_text(
            'BackupData.plurks["2018_10"]=['
            '{"id": 100, "base_id": "abc", "content_raw": "See https://example.com/test"}'
            '];'
        )
        return [plurk_file], []

    def test_extract_loads_icu_extension(self, tmp_path: Path):
        """extract_links_from_files loads ICU extension when path provided."""
        db_path = tmp_path / "test.db"
        self._setup_db_with_icu_fts(db_path)
        plurk_files, response_files = self._setup_backup(tmp_path)

        with patch("database.load_icu_extension") as mock_load:
            extract_links_from_files(
                plurk_files=plurk_files,
                response_files=response_files,
                db_path=db_path,
                icu_extension_path="/fake/libfts5_icu.dylib",
            )
            mock_load.assert_called_once()
            # load_icu_extension(conn, extension_path) - check second positional arg
            assert mock_load.call_args[0][1] == "/fake/libfts5_icu.dylib"

    def test_extract_skips_icu_when_no_path(self, tmp_path: Path):
        """extract_links_from_files does not load ICU when path is None."""
        db_path = tmp_path / "test.db"
        self._setup_db_with_icu_fts(db_path)
        plurk_files, response_files = self._setup_backup(tmp_path)

        with patch("database.load_icu_extension") as mock_load, \
             patch("database.resolve_icu_extension", return_value=None):
            extract_links_from_files(
                plurk_files=plurk_files,
                response_files=response_files,
                db_path=db_path,
                icu_extension_path=None,
            )
            mock_load.assert_not_called()

    def test_update_og_metadata_with_fts_triggers(self, tmp_path: Path):
        """Verify update_og_metadata works when FTS triggers are active.

        The link_metadata_fts triggers fire on every UPDATE to link_metadata.
        If the FTS table was created with 'icu zh' tokenizer, the ICU extension
        must be loaded on the connection — otherwise: 'no such tokenizer: icu'.
        This test uses unicode61 (built-in) to verify the trigger path works.
        """
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))

        # Create table + FTS + triggers first, then insert data
        create_link_metadata_table(conn)

        conn.execute(
            "INSERT INTO link_metadata (url, sources, status) VALUES (?, ?, ?)",
            ("https://example.com", '{"plurk_ids": [1]}', "pending"),
        )
        conn.commit()

        # UPDATE fires the link_metadata_au trigger → writes to FTS
        result = OGResult(
            url="https://example.com",
            status="success",
            title="Example",
            description="An example page",
        )
        update_og_metadata(conn, result)
        conn.commit()

        row = conn.execute(
            "SELECT og_title, status FROM link_metadata WHERE url = ?",
            ("https://example.com",),
        ).fetchone()
        assert row[0] == "Example"
        assert row[1] == "success"

        # Verify FTS was updated too (trigger worked)
        fts_row = conn.execute(
            "SELECT og_title FROM link_metadata_fts WHERE link_metadata_fts MATCH ?",
            ('"Example"',),
        ).fetchone()
        assert fts_row is not None
        assert fts_row[0] == "Example"
        conn.close()


class TestOgMetadataSanitization:
    """Tests that OG metadata with problematic characters doesn't break FTS5.

    Facebook and other sites sometimes return OG metadata containing NUL bytes
    or control characters. These can cause 'SQL logic error' when the FTS5
    after-update trigger tries to tokenize the text.

    Regression test for: https://www.facebook.com/share/p/1PfsYXp3hc/
    which caused 'DB error: SQL logic error' during links fetch.
    """

    @pytest.fixture
    def db_with_pending_url(self):
        """Create in-memory DB with FTS5 triggers and a pending URL."""
        conn = sqlite3.connect(":memory:")
        create_link_metadata_table(conn)
        conn.execute(
            "INSERT INTO link_metadata (url, sources, status, source_month) VALUES (?, ?, ?, ?)",
            ("https://www.facebook.com/share/p/1PfsYXp3hc/",
             '{"plurk_ids": [1], "response_ids": []}', "pending", "2025_07"),
        )
        conn.commit()
        yield conn
        conn.close()

    def test_nul_bytes_in_og_title(self, db_with_pending_url):
        """OG title with NUL bytes should not cause SQL logic error."""
        conn = db_with_pending_url
        result = OGResult(
            url="https://www.facebook.com/share/p/1PfsYXp3hc/",
            status="success",
            title="Some\x00Title\x00Here",
            description="Normal description",
            site_name="Facebook",
        )
        update_og_metadata(conn, result)
        conn.commit()

        row = conn.execute(
            "SELECT og_title, status FROM link_metadata WHERE url = ?",
            (result.url,),
        ).fetchone()
        assert row[1] == "success"
        assert "\x00" not in row[0]  # NUL bytes should be stripped

    def test_control_chars_in_og_description(self, db_with_pending_url):
        """OG description with control characters should not cause SQL logic error."""
        conn = db_with_pending_url
        result = OGResult(
            url="https://www.facebook.com/share/p/1PfsYXp3hc/",
            status="success",
            title="Normal Title",
            description="Text with\x01bell\x02and\x03control\x1fchars",
            site_name="Facebook",
        )
        update_og_metadata(conn, result)
        conn.commit()

        row = conn.execute(
            "SELECT og_description FROM link_metadata WHERE url = ?",
            (result.url,),
        ).fetchone()
        # Control chars should be stripped, but text preserved
        assert "Text with" in row[0]
        assert "control" in row[0]

    def test_preserves_tabs_newlines(self, db_with_pending_url):
        """Tabs, newlines, and carriage returns should be preserved."""
        conn = db_with_pending_url
        result = OGResult(
            url="https://www.facebook.com/share/p/1PfsYXp3hc/",
            status="success",
            title="Title\twith\ttabs",
            description="Line1\nLine2\r\nLine3",
        )
        update_og_metadata(conn, result)
        conn.commit()

        row = conn.execute(
            "SELECT og_title, og_description FROM link_metadata WHERE url = ?",
            (result.url,),
        ).fetchone()
        assert "\t" in row[0]
        assert "\n" in row[1]

    def test_fts_searchable_after_sanitization(self, db_with_pending_url):
        """FTS index should be searchable after sanitized update."""
        conn = db_with_pending_url
        result = OGResult(
            url="https://www.facebook.com/share/p/1PfsYXp3hc/",
            status="success",
            title="Facebook\x00Post",
            description="Interesting\x00content here",
            site_name="Facebook",
        )
        update_og_metadata(conn, result)
        conn.commit()

        # Should be searchable in FTS after sanitization
        fts_row = conn.execute(
            "SELECT og_title FROM link_metadata_fts WHERE link_metadata_fts MATCH ?",
            ('"FacebookPost"',),
        ).fetchone()
        assert fts_row is not None


class TestTransactionRollback:
    """Tests that DB errors during fetch don't leave the database locked.

    If update_og_metadata raises (e.g., 'no such tokenizer: icu'), the
    transaction must be rolled back so the connection and database remain
    usable. Without rollback, the dirty transaction locks the database.
    """

    def _create_db_with_pending_urls(self, db_path: Path, urls: list[str]) -> None:
        """Create a DB with link_metadata table and pending URLs."""
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE plurks (id INTEGER PRIMARY KEY)")
        create_link_metadata_table(conn)
        for url in urls:
            conn.execute(
                "INSERT INTO link_metadata (url, sources, status) VALUES (?, ?, ?)",
                (url, '{"plurk_ids": [1]}', "pending"),
            )
        conn.commit()
        conn.close()

    def test_rollback_after_update_error(self, tmp_path: Path):
        """After a failed update_og_metadata, rollback keeps the DB usable."""
        db_path = tmp_path / "test.db"
        self._create_db_with_pending_urls(db_path, ["https://example.com"])

        conn = sqlite3.connect(str(db_path))
        create_link_metadata_table(conn)

        # Simulate a trigger error by dropping the FTS table
        # (update trigger references it, so UPDATE will fail)
        conn.execute("DROP TABLE link_metadata_fts")
        conn.commit()

        result = OGResult(
            url="https://example.com",
            status="success",
            title="Test",
        )

        # update_og_metadata should raise because the trigger can't
        # write to the now-missing FTS table
        with pytest.raises(sqlite3.OperationalError):
            update_og_metadata(conn, result)

        # Without rollback, the connection has a dirty transaction
        # and the DB would be locked. Rollback fixes it.
        conn.rollback()

        # Verify the connection is still usable after rollback
        row = conn.execute(
            "SELECT status FROM link_metadata WHERE url = ?",
            ("https://example.com",),
        ).fetchone()
        assert row[0] == "pending"  # unchanged, update was rolled back
        conn.close()

    def test_dirty_transaction_locks_db(self, tmp_path: Path):
        """A dirty transaction (no commit/rollback) locks the DB for others."""
        db_path = tmp_path / "test.db"
        self._create_db_with_pending_urls(db_path, ["https://example.com"])

        conn = sqlite3.connect(str(db_path))
        # Start a write transaction without committing
        conn.execute(
            "UPDATE link_metadata SET status = 'fetching' WHERE url = ?",
            ("https://example.com",),
        )
        # deliberately skip commit — simulates what happens when
        # update_og_metadata raises and we don't rollback

        # A second connection should fail to write (DB is locked)
        conn2 = sqlite3.connect(str(db_path), timeout=0.1)
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            conn2.execute(
                "UPDATE link_metadata SET status = 'failed' WHERE url = ?",
                ("https://example.com",),
            )
        conn2.close()
        conn.close()

    def test_rollback_releases_lock(self, tmp_path: Path):
        """After rollback, another connection can write to the DB."""
        db_path = tmp_path / "test.db"
        self._create_db_with_pending_urls(db_path, ["https://example.com"])

        conn = sqlite3.connect(str(db_path))
        # Start a write transaction
        conn.execute(
            "UPDATE link_metadata SET status = 'fetching' WHERE url = ?",
            ("https://example.com",),
        )
        # Rollback releases the lock
        conn.rollback()

        # A second connection should now be able to write
        conn2 = sqlite3.connect(str(db_path), timeout=0.1)
        conn2.execute(
            "UPDATE link_metadata SET status = 'failed' WHERE url = ?",
            ("https://example.com",),
        )
        conn2.commit()

        row = conn2.execute(
            "SELECT status FROM link_metadata WHERE url = ?",
            ("https://example.com",),
        ).fetchone()
        assert row[0] == "failed"
        conn2.close()
        conn.close()

    def test_close_releases_lock(self, tmp_path: Path):
        """Closing connection with dirty transaction releases the lock."""
        db_path = tmp_path / "test.db"
        self._create_db_with_pending_urls(db_path, ["https://example.com"])

        conn = sqlite3.connect(str(db_path))
        # Start a write transaction
        conn.execute(
            "UPDATE link_metadata SET status = 'fetching' WHERE url = ?",
            ("https://example.com",),
        )
        # Close without commit — implicitly rolls back
        conn.close()

        # Another connection should be able to write
        conn2 = sqlite3.connect(str(db_path), timeout=0.1)
        row = conn2.execute(
            "SELECT status FROM link_metadata WHERE url = ?",
            ("https://example.com",),
        ).fetchone()
        assert row[0] == "pending"  # rolled back, not 'fetching'

        conn2.execute(
            "UPDATE link_metadata SET status = 'failed' WHERE url = ?",
            ("https://example.com",),
        )
        conn2.commit()
        conn2.close()


# Note: CLI tests for links_cmd.py were removed since the standalone CLI was
# deprecated in favor of the unified CLI (plurk-tools links ...)
