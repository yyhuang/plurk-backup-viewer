"""Tests for patch_cmd.py - patching backup index.html."""

from pathlib import Path

from patch_cmd import patch_index_html


class TestPatchMultilineDiv:
    """patch_index_html should handle multiline plurk-logo div."""

    def test_patch_multiline_plurk_logo(self, tmp_path: Path):
        """Plurk-logo div with newlines between spans should be patched."""
        index = tmp_path / "index.html"
        index.write_text(
            '<div id="plurk-logo">\n'
            '  <span class="logo-icon"></span>\n'
            '  <span class="logo-text">Plurk</span>\n'
            '</div>',
            encoding="utf-8",
        )
        assert patch_index_html(tmp_path) is True
        content = index.read_text(encoding="utf-8")
        assert "plurk-logo-link" in content

    def test_patch_single_line_plurk_logo(self, tmp_path: Path):
        """Single-line plurk-logo div should still work."""
        index = tmp_path / "index.html"
        index.write_text(
            '<div id="plurk-logo"><span>Plurk</span></div>',
            encoding="utf-8",
        )
        assert patch_index_html(tmp_path) is True
        content = index.read_text(encoding="utf-8")
        assert "plurk-logo-link" in content
