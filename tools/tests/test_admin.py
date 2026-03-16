"""Tests for admin_cmd.py - admin interface backend."""

import io
import json
import sqlite3
import zipfile
from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

import pytest

from admin_cmd import MAX_UPLOAD_SIZE, TaskTracker, extract_zip, make_admin_handler
from database import create_schema


# ============== TaskTracker ==============


class TestTaskTracker:
    def test_initial_state(self):
        t = TaskTracker()
        status = t.get_status()
        assert status["status"] == "idle"
        assert status["type"] is None
        assert status["log"] == []
        assert status["error"] is None

    def test_start(self):
        t = TaskTracker()
        assert t.start("upload") is True
        status = t.get_status()
        assert status["status"] == "running"
        assert status["type"] == "upload"

    def test_start_rejects_concurrent(self):
        t = TaskTracker()
        t.start("upload")
        assert t.start("init") is False

    def test_update_progress_and_log(self):
        t = TaskTracker()
        t.start("upload")
        t.update(progress="50%", log_line="Extracting...")
        status = t.get_status()
        assert status["progress"] == "50%"
        assert status["log"] == ["Extracting..."]

    def test_finish_success(self):
        t = TaskTracker()
        t.start("init")
        t.finish(True, "Done!")
        status = t.get_status()
        assert status["status"] == "done"
        assert "Done!" in status["log"]
        assert status["error"] is None

    def test_finish_error(self):
        t = TaskTracker()
        t.start("init")
        t.finish(False, "Something broke")
        status = t.get_status()
        assert status["status"] == "error"
        assert status["error"] == "Something broke"

    def test_can_restart_after_done(self):
        t = TaskTracker()
        t.start("upload")
        t.finish(True, "done")
        assert t.start("init") is True


# ============== Zip Extraction ==============


def make_test_zip(files: dict[str, str], wrapper: str = "") -> bytes:
    """Create a zip file in memory with given file structure.

    Args:
        files: Dict of {path: content} to include
        wrapper: Optional wrapper directory prefix
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            full_path = f"{wrapper}{path}" if wrapper else path
            zf.writestr(full_path, content)
    return buf.getvalue()


VALID_BACKUP_FILES = {
    "data/indexes.js": "var indexes = {};",
    "data/plurks/0.js": "var data = [];",
    "data/responses/0.js": "var data = [];",
    "index.html": "<html></html>",
}


class TestExtractZip:
    def test_extract_basic(self, tmp_path: Path):
        """Extract a valid backup zip."""
        zip_data = make_test_zip(VALID_BACKUP_FILES)
        tracker = TaskTracker()
        tracker.start("upload")
        dest = tmp_path / "backup"

        result = extract_zip(zip_data, dest, tracker)

        assert result is True
        assert (dest / "data" / "indexes.js").exists()
        assert (dest / "data" / "plurks" / "0.js").exists()
        assert (dest / "data" / "responses" / "0.js").exists()

    def test_extract_with_wrapper(self, tmp_path: Path):
        """Extract a zip with a wrapper directory (like Plurk exports)."""
        zip_data = make_test_zip(VALID_BACKUP_FILES, wrapper="ahbia-backup/")
        tracker = TaskTracker()
        tracker.start("upload")
        dest = tmp_path / "backup"

        result = extract_zip(zip_data, dest, tracker)

        assert result is True
        assert (dest / "data" / "indexes.js").exists()
        # Wrapper should be stripped
        assert not (dest / "ahbia-backup").exists()

    def test_extract_invalid_zip(self, tmp_path: Path):
        """Reject non-zip data."""
        tracker = TaskTracker()
        tracker.start("upload")
        dest = tmp_path / "backup"

        result = extract_zip(b"not a zip", dest, tracker)

        assert result is False
        assert tracker.get_status()["status"] == "error"

    def test_extract_invalid_structure(self, tmp_path: Path):
        """Reject zip with missing required structure."""
        zip_data = make_test_zip({"readme.txt": "hello"})
        tracker = TaskTracker()
        tracker.start("upload")
        dest = tmp_path / "backup"

        result = extract_zip(zip_data, dest, tracker)

        assert result is False
        assert "Invalid backup structure" in tracker.get_status()["error"]

    def test_extract_path_traversal(self, tmp_path: Path):
        """Reject zip with path traversal."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../../etc/passwd", "evil")
        tracker = TaskTracker()
        tracker.start("upload")
        dest = tmp_path / "backup"

        result = extract_zip(buf.getvalue(), dest, tracker)

        assert result is False
        assert "Unsafe path" in tracker.get_status()["error"]

    def test_extract_clears_existing(self, tmp_path: Path):
        """Overwrite existing backup on re-upload."""
        dest = tmp_path / "backup"
        dest.mkdir()
        (dest / "old_file.txt").write_text("old")

        zip_data = make_test_zip(VALID_BACKUP_FILES)
        tracker = TaskTracker()
        tracker.start("upload")

        extract_zip(zip_data, dest, tracker)

        assert not (dest / "old_file.txt").exists()
        assert (dest / "data" / "indexes.js").exists()


# ============== Admin HTTP API ==============


@pytest.fixture
def admin_server(tmp_path: Path):
    """Start an admin server on a random port and return (url, data_dir, tracker)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    viewer_dir = tmp_path / "viewer"
    viewer_dir.mkdir()
    # Create a minimal admin.html
    (viewer_dir / "admin.html").write_text("<html>admin</html>")

    tracker = TaskTracker()
    handler = make_admin_handler(data_dir, viewer_dir, tracker)
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}", data_dir, tracker

    server.shutdown()


class TestAdminAPI:
    def test_root_redirects(self, admin_server):
        url, _, _ = admin_server
        req = Request(f"{url}/", method="GET")
        # urllib follows redirects, so check we get the admin page
        res = urlopen(req)
        assert res.status == 200

    def test_info_empty(self, admin_server):
        url, _, _ = admin_server
        res = urlopen(f"{url}/api/admin/info")
        info = json.loads(res.read())
        assert info["backup_exists"] is False
        assert info["db_exists"] is False

    def test_info_with_backup(self, admin_server, tmp_path):
        url, data_dir, _ = admin_server
        # Create a valid backup structure
        backup = data_dir / "backup"
        (backup / "data" / "plurks").mkdir(parents=True)
        (backup / "data" / "responses").mkdir(parents=True)
        (backup / "data" / "indexes.js").write_text("var indexes = {};")

        res = urlopen(f"{url}/api/admin/info")
        info = json.loads(res.read())
        assert info["backup_exists"] is True

    def test_info_with_db(self, admin_server):
        url, data_dir, _ = admin_server
        # Create a database with schema
        db_path = data_dir / "plurks.db"
        conn = sqlite3.connect(str(db_path))
        create_schema(conn)
        conn.execute(
            "INSERT INTO plurks (id, base_id, content_raw, posted, response_count, qualifier) "
            "VALUES (1, 'abc', 'test', '2018-01-01', 0, 'says')"
        )
        conn.commit()
        conn.close()

        res = urlopen(f"{url}/api/admin/info")
        info = json.loads(res.read())
        assert info["db_exists"] is True
        assert info["plurk_count"] == 1

    def test_status_idle(self, admin_server):
        url, _, _ = admin_server
        res = urlopen(f"{url}/api/admin/status")
        status = json.loads(res.read())
        assert status["status"] == "idle"

    def test_upload_empty_body(self, admin_server):
        url, _, _ = admin_server
        from urllib.error import HTTPError
        req = Request(f"{url}/api/admin/upload", method="POST", data=b"",
                      headers={"Content-Type": "application/zip", "Content-Length": "0"})
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req)
        assert exc_info.value.code == 400

    def test_upload_valid_zip(self, admin_server):
        url, data_dir, tracker = admin_server
        zip_data = make_test_zip(VALID_BACKUP_FILES)
        req = Request(f"{url}/api/admin/upload", method="POST", data=zip_data,
                      headers={"Content-Type": "application/zip",
                               "Content-Length": str(len(zip_data))})
        res = urlopen(req)
        data = json.loads(res.read())
        assert data["status"] == "started"

        # Wait for extraction to complete
        import time
        for _ in range(20):
            time.sleep(0.2)
            s = tracker.get_status()
            if s["status"] != "running":
                break

        assert tracker.get_status()["status"] == "done"
        assert (data_dir / "backup" / "data" / "indexes.js").exists()

    def test_concurrent_task_rejected(self, admin_server):
        url, _, tracker = admin_server
        # Manually start a task
        tracker.start("upload")

        from urllib.error import HTTPError
        req = Request(f"{url}/api/admin/init", method="POST", data=b"",
                      headers={"Content-Length": "0"})
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req)
        assert exc_info.value.code == 409

    def test_upload_too_large(self, admin_server):
        """Upload with Content-Length exceeding MAX_UPLOAD_SIZE is rejected."""
        url, _, _ = admin_server
        from urllib.error import HTTPError
        fake_size = MAX_UPLOAD_SIZE + 1
        req = Request(
            f"{url}/api/admin/upload", method="POST", data=b"x",
            headers={"Content-Type": "application/zip",
                     "Content-Length": str(fake_size)},
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req)
        assert exc_info.value.code == 413
        body = json.loads(exc_info.value.read())
        assert "too large" in body["error"].lower()

    def test_not_found(self, admin_server):
        url, _, _ = admin_server
        from urllib.error import HTTPError
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{url}/api/admin/nope")
        assert exc_info.value.code == 404
