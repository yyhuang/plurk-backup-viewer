"""Tests for links_cmd.py (renamed from build_link_db.py) - URL extraction and OG metadata fetching."""

import json
import sqlite3
from pathlib import Path

import pytest

from links_cmd import (
    create_link_metadata_table,
    extract_urls,
    is_image_content_type,
    is_image_url,
    process_plurk_file,
    process_response_file,
    upsert_link,
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
        assert url_sources["https://example.com"] == {"plurk_ids": [123], "response_ids": []}

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
        assert url_sources["https://example.com"] == {"plurk_ids": [], "response_ids": [789]}


class TestUpsertLink:
    """Tests for upserting links to database."""

    @pytest.fixture
    def db(self, tmp_path: Path):
        """Create in-memory database with schema."""
        conn = sqlite3.connect(":memory:")
        create_link_metadata_table(conn)
        return conn

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

        # Check FTS5 table exists
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='link_metadata_fts'"
        ).fetchone()
        assert result is not None

    def test_create_table_idempotent(self):
        """Creating table twice doesn't error."""
        conn = sqlite3.connect(":memory:")
        create_link_metadata_table(conn)
        create_link_metadata_table(conn)  # Should not raise


class TestCLI:
    """Tests for CLI argument parsing."""

    def test_no_subcommand_fails(self):
        """Running without subcommand should fail."""
        import subprocess

        result = subprocess.run(
            ["python", "links_cmd.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "usage" in result.stderr.lower()

    def test_extract_requires_month(self, tmp_path: Path):
        """extract without --month should fail."""
        import subprocess

        # Create minimal backup structure
        backup_dir = tmp_path / "backup"
        (backup_dir / "data" / "plurks").mkdir(parents=True)
        (backup_dir / "data" / "responses").mkdir(parents=True)
        (backup_dir / "data" / "indexes.js").write_text("BackupData.indexes={};")

        result = subprocess.run(
            ["python", "links_cmd.py", "extract", str(backup_dir)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode != 0
        assert "--month" in result.stderr

    def test_extract_validates_month_format_length(self, tmp_path: Path):
        """extract with invalid --month length should fail."""
        import subprocess

        backup_dir = tmp_path / "backup"
        (backup_dir / "data" / "plurks").mkdir(parents=True)
        (backup_dir / "data" / "responses").mkdir(parents=True)
        (backup_dir / "data" / "indexes.js").write_text("BackupData.indexes={};")

        result = subprocess.run(
            ["python", "links_cmd.py", "extract", str(backup_dir), "--month", "2018"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode != 0
        assert "YYYYMM" in result.stderr

    def test_extract_validates_month_format_invalid_month(self, tmp_path: Path):
        """extract with invalid month number should fail."""
        import subprocess

        backup_dir = tmp_path / "backup"
        (backup_dir / "data" / "plurks").mkdir(parents=True)
        (backup_dir / "data" / "responses").mkdir(parents=True)
        (backup_dir / "data" / "indexes.js").write_text("BackupData.indexes={};")

        result = subprocess.run(
            ["python", "links_cmd.py", "extract", str(backup_dir), "--month", "201813"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode != 0
        assert "01-12" in result.stderr

    def test_extract_requires_backup_path(self):
        """extract without backup_path should fail."""
        import subprocess

        result = subprocess.run(
            ["python", "links_cmd.py", "extract", "--month", "201810"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode != 0

    def test_fetch_previews_no_required_options(self, tmp_path: Path):
        """fetch-previews only needs backup_path, other options have defaults."""
        import subprocess

        # Create backup structure with database
        backup_dir = tmp_path / "backup"
        (backup_dir / "data" / "plurks").mkdir(parents=True)
        (backup_dir / "data" / "responses").mkdir(parents=True)
        (backup_dir / "data" / "indexes.js").write_text("BackupData.indexes={};")

        # Create database with link_metadata table
        db_path = backup_dir / "data" / "plurks.db"
        conn = sqlite3.connect(db_path)
        create_link_metadata_table(conn)
        conn.close()

        result = subprocess.run(
            ["python", "links_cmd.py", "fetch-previews", str(backup_dir)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        # Should succeed (with "No pending URLs" message)
        assert result.returncode == 0
        assert "No pending URLs" in result.stdout

    def test_fetch_previews_accepts_optional_limit(self, tmp_path: Path):
        """fetch-previews accepts --limit option."""
        import subprocess

        backup_dir = tmp_path / "backup"
        (backup_dir / "data" / "plurks").mkdir(parents=True)
        (backup_dir / "data" / "responses").mkdir(parents=True)
        (backup_dir / "data" / "indexes.js").write_text("BackupData.indexes={};")

        db_path = backup_dir / "data" / "plurks.db"
        conn = sqlite3.connect(db_path)
        create_link_metadata_table(conn)
        conn.close()

        result = subprocess.run(
            ["python", "links_cmd.py", "fetch-previews", str(backup_dir), "--limit", "100"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0

    def test_fetch_previews_accepts_optional_timeout_and_retries(self, tmp_path: Path):
        """fetch-previews accepts --timeout and --retries options."""
        import subprocess

        backup_dir = tmp_path / "backup"
        (backup_dir / "data" / "plurks").mkdir(parents=True)
        (backup_dir / "data" / "responses").mkdir(parents=True)
        (backup_dir / "data" / "indexes.js").write_text("BackupData.indexes={};")

        db_path = backup_dir / "data" / "plurks.db"
        conn = sqlite3.connect(db_path)
        create_link_metadata_table(conn)
        conn.close()

        result = subprocess.run(
            [
                "python", "links_cmd.py", "fetch-previews", str(backup_dir),
                "--timeout", "5000", "--retries", "2"
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0

    def test_status_no_required_options(self, tmp_path: Path):
        """status only needs backup_path."""
        import subprocess

        backup_dir = tmp_path / "backup"
        (backup_dir / "data" / "plurks").mkdir(parents=True)
        (backup_dir / "data" / "responses").mkdir(parents=True)
        (backup_dir / "data" / "indexes.js").write_text("BackupData.indexes={};")

        db_path = backup_dir / "data" / "plurks.db"
        conn = sqlite3.connect(db_path)
        create_link_metadata_table(conn)
        conn.close()

        result = subprocess.run(
            ["python", "links_cmd.py", "status", str(backup_dir)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0
        assert "Total URLs" in result.stdout

    def test_invalid_backup_path(self, tmp_path: Path):
        """Commands should fail with invalid backup path."""
        import subprocess

        result = subprocess.run(
            ["python", "links_cmd.py", "status", str(tmp_path / "nonexistent")],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode != 0
        assert "Invalid backup directory" in result.stderr
