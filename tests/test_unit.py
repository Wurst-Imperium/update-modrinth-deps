"""Unit tests for pure functions — no network, no git."""

import textwrap
from pathlib import Path

import pytest

from main import (
    detect_line_ending,
    get_version_value,
    read_gradle_properties,
    write_gradle_property,
)


# ── detect_line_ending ───────────────────────────────────────────────

class TestDetectLineEnding:
    def test_lf(self):
        assert detect_line_ending("a\nb\nc\n") == "\n"

    def test_crlf(self):
        assert detect_line_ending("a\r\nb\r\nc\r\n") == "\r\n"

    def test_mixed_majority_crlf(self):
        assert detect_line_ending("a\r\nb\r\nc\n") == "\r\n"

    def test_mixed_majority_lf(self):
        assert detect_line_ending("a\nb\nc\r\n") == "\n"

    def test_empty(self):
        assert detect_line_ending("") == "\n"

    def test_no_newlines(self):
        assert detect_line_ending("hello") == "\n"


# ── read_gradle_properties ───────────────────────────────────────────

class TestReadGradleProperties:
    def test_basic(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_text("minecraft_version=1.21.11\nmod_loader=fabric\n")
        props = read_gradle_properties(f)
        assert props == {"minecraft_version": "1.21.11", "mod_loader": "fabric"}

    def test_comments_and_blanks(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_text("# comment\n\nkey=value\n")
        assert read_gradle_properties(f) == {"key": "value"}

    def test_spaces_around_equals(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_text("  key  =  value  \n")
        assert read_gradle_properties(f) == {"key": "value"}

    def test_value_with_equals(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_text("key=a=b=c\n")
        assert read_gradle_properties(f) == {"key": "a=b=c"}

    def test_empty_value(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_text("key=\n")
        assert read_gradle_properties(f) == {"key": ""}

    def test_crlf(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_text("a=1\r\nb=2\r\n")
        assert read_gradle_properties(f) == {"a": "1", "b": "2"}


# ── write_gradle_property ────────────────────────────────────────────

class TestWriteGradleProperty:
    def test_basic_update(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_text("minecraft_version=1.21.10\nmod_loader=fabric\n")
        write_gradle_property(f, "minecraft_version", "1.21.11")
        assert "minecraft_version=1.21.11\n" in f.read_text()
        assert "mod_loader=fabric\n" in f.read_text()

    def test_preserves_lf(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_text("a=1\nb=2\n")
        write_gradle_property(f, "a", "99")
        raw = f.read_text()
        assert "\r\n" not in raw
        assert raw == "a=99\nb=2\n"

    def test_preserves_crlf(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        f.write_bytes(b"a=1\r\nb=2\r\n")
        write_gradle_property(f, "a", "99")
        raw = f.read_bytes()
        assert b"a=99\r\n" in raw
        assert b"b=2\r\n" in raw

    def test_preserves_other_lines(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        original = "# header\nfoo=bar\ntarget=old\nbaz=qux\n"
        f.write_text(original)
        write_gradle_property(f, "target", "new")
        lines = f.read_text().splitlines()
        assert lines == ["# header", "foo=bar", "target=new", "baz=qux"]

    def test_key_not_found_no_change(self, tmp_path: Path):
        f = tmp_path / "gradle.properties"
        original = "a=1\nb=2\n"
        f.write_text(original)
        write_gradle_property(f, "nonexistent", "value")
        assert f.read_text() == original

    def test_spaces_in_original_key(self, tmp_path: Path):
        """Key with spaces around = should still match."""
        f = tmp_path / "gradle.properties"
        f.write_text("key = old_value\n")
        write_gradle_property(f, "key", "new_value")
        assert "key=new_value\n" in f.read_text()


# ── get_version_value ────────────────────────────────────────────────

class TestGetVersionValue:
    def test_version_number(self):
        v = {"id": "abc123", "version_number": "1.0.0"}
        assert get_version_value(v, use_id=False) == "1.0.0"

    def test_id(self):
        v = {"id": "abc123", "version_number": "1.0.0"}
        assert get_version_value(v, use_id=True) == "abc123"
