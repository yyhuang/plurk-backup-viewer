"""Tests for ICU extension fail-fast behavior.

When an ICU extension path is resolved but loading fails,
connect_with_icu should raise instead of silently falling back.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from database import connect_with_icu


class TestConnectWithIcuFailFast:
    """connect_with_icu should raise when ICU path exists but load fails."""

    def test_explicit_path_load_failure_raises(self, tmp_path: Path):
        """If icu_extension_path is given but load fails, raise RuntimeError."""
        db_path = tmp_path / "test.db"
        with pytest.raises(RuntimeError, match="Failed to load ICU extension"):
            connect_with_icu(db_path, icu_extension_path="/nonexistent/libfts5_icu.so")

    def test_resolved_path_load_failure_raises(self, tmp_path: Path):
        """If resolve_icu_extension finds a path but load fails, raise RuntimeError."""
        db_path = tmp_path / "test.db"
        with patch("database.resolve_icu_extension", return_value="/fake/libfts5_icu.so"):
            with pytest.raises(RuntimeError, match="Failed to load ICU extension"):
                connect_with_icu(db_path)

    def test_no_path_resolved_returns_false(self, tmp_path: Path):
        """If no ICU path is found at all, return icu_loaded=False (no error)."""
        db_path = tmp_path / "test.db"
        with patch("database.resolve_icu_extension", return_value=None):
            conn, icu_loaded = connect_with_icu(db_path)
            assert icu_loaded is False
            conn.close()

    def test_connection_closed_on_failure(self, tmp_path: Path):
        """Connection should be closed when ICU load fails."""
        db_path = tmp_path / "test.db"
        with pytest.raises(RuntimeError):
            connect_with_icu(db_path, icu_extension_path="/nonexistent/libfts5_icu.so")

        # DB file was created but connection should be closed (not locked)
        # Verify by opening a new connection successfully
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()
