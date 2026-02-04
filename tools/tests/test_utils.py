"""Tests for utils.py - parsing backup JS files."""

import json
import tempfile
from pathlib import Path

import pytest

from utils import parse_plurk_file, parse_response_file, validate_backup_dir


class TestParsePlurkFile:
    """Tests for parse_plurk_file function."""

    def test_parse_plurk_file_basic(self, tmp_path: Path):
        """Parse a basic plurk file with one entry."""
        content = '''BackupData.plurks["2008_12"]=[{"id": 19811612, "base_id": "bsmqk", "qualifier": "feels", "content_raw": "test content", "posted": "Wed, 31 Dec 2008 02:11:44 GMT", "response_count": 1}];'''

        file = tmp_path / "2008_12.js"
        file.write_text(content)

        month_key, plurks = parse_plurk_file(file)

        assert month_key == "2008_12"
        assert len(plurks) == 1
        assert plurks[0]["id"] == 19811612
        assert plurks[0]["base_id"] == "bsmqk"
        assert plurks[0]["content_raw"] == "test content"

    def test_parse_plurk_file_multiple_entries(self, tmp_path: Path):
        """Parse a plurk file with multiple entries."""
        content = '''BackupData.plurks["2009_01"]=[{"id": 1, "base_id": "a", "content_raw": "first"}, {"id": 2, "base_id": "b", "content_raw": "second"}];'''

        file = tmp_path / "2009_01.js"
        file.write_text(content)

        month_key, plurks = parse_plurk_file(file)

        assert month_key == "2009_01"
        assert len(plurks) == 2
        assert plurks[0]["id"] == 1
        assert plurks[1]["id"] == 2

    def test_parse_plurk_file_unicode(self, tmp_path: Path):
        """Parse plurk file with Chinese content."""
        content = '''BackupData.plurks["2008_12"]=[{"id": 1, "base_id": "x", "content_raw": "只是要看別人碎碎念都這樣麻煩嗎 orz"}];'''

        file = tmp_path / "2008_12.js"
        file.write_text(content, encoding="utf-8")

        month_key, plurks = parse_plurk_file(file)

        assert plurks[0]["content_raw"] == "只是要看別人碎碎念都這樣麻煩嗎 orz"


class TestParseResponseFile:
    """Tests for parse_response_file function."""

    def test_parse_response_file_basic(self, tmp_path: Path):
        """Parse a basic response file."""
        content = '''BackupData.responses["100o22"]=[{"id": 286488273, "content_raw": "test response", "posted": "Thu, 11 Jun 2009 06:15:45 GMT", "user": {"id": 3343980, "nick_name": "testuser", "display_name": "測試暱稱"}}];'''

        file = tmp_path / "100o22.js"
        file.write_text(content)

        base_id, responses = parse_response_file(file)

        assert base_id == "100o22"
        assert len(responses) == 1
        assert responses[0]["id"] == 286488273
        assert responses[0]["content_raw"] == "test response"
        assert responses[0]["user"]["nick_name"] == "testuser"

    def test_parse_response_file_multiple(self, tmp_path: Path):
        """Parse response file with multiple responses."""
        content = '''BackupData.responses["abc"]=[{"id": 1, "content_raw": "r1", "user": {"id": 1, "nick_name": "u1"}}, {"id": 2, "content_raw": "r2", "user": {"id": 2, "nick_name": "u2"}}];'''

        file = tmp_path / "abc.js"
        file.write_text(content)

        base_id, responses = parse_response_file(file)

        assert base_id == "abc"
        assert len(responses) == 2


class TestValidateBackupDir:
    """Tests for validate_backup_dir function."""

    def test_validate_valid_backup(self, tmp_path: Path):
        """Validate a properly structured backup directory."""
        # Create required structure
        (tmp_path / "data" / "plurks").mkdir(parents=True)
        (tmp_path / "data" / "responses").mkdir(parents=True)
        (tmp_path / "data" / "indexes.js").write_text("test")

        assert validate_backup_dir(tmp_path) is True

    def test_validate_missing_plurks(self, tmp_path: Path):
        """Reject backup missing plurks directory."""
        (tmp_path / "data" / "responses").mkdir(parents=True)
        (tmp_path / "data" / "indexes.js").write_text("test")

        assert validate_backup_dir(tmp_path) is False

    def test_validate_missing_responses(self, tmp_path: Path):
        """Reject backup missing responses directory."""
        (tmp_path / "data" / "plurks").mkdir(parents=True)
        (tmp_path / "data" / "indexes.js").write_text("test")

        assert validate_backup_dir(tmp_path) is False

    def test_validate_missing_indexes(self, tmp_path: Path):
        """Reject backup missing indexes.js."""
        (tmp_path / "data" / "plurks").mkdir(parents=True)
        (tmp_path / "data" / "responses").mkdir(parents=True)

        assert validate_backup_dir(tmp_path) is False
