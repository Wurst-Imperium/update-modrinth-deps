"""Unit tests for pure functions — no network, no git."""

from main import (
	apply_version_transform,
	detect_line_ending,
	get_remote_branch_head,
	get_version_value,
	push_branch,
	read_gradle_properties,
	write_gradle_property,
)
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestApplyVersionTransform:
	def test_no_transform(self):
		assert apply_version_transform("21.11.153+neoforge", None) == "21.11.153+neoforge"

	def test_strip_plus_suffix(self):
		transform = {"pattern": r"\+.*$", "replacement": ""}
		assert apply_version_transform("21.11.153+neoforge", transform) == "21.11.153"

	def test_strip_fabric_suffix(self):
		transform = {"pattern": r"\+.*$", "replacement": ""}
		assert apply_version_transform("21.11.153+fabric", transform) == "21.11.153"

	def test_no_match(self):
		transform = {"pattern": r"\+.*$", "replacement": ""}
		assert apply_version_transform("21.11.153", transform) == "21.11.153"

	def test_custom_replacement(self):
		transform = {"pattern": r"\+neoforge", "replacement": "-nf"}
		assert apply_version_transform("21.11.153+neoforge", transform) == "21.11.153-nf"

	def test_empty_transform(self):
		assert apply_version_transform("21.11.153", {}) == "21.11.153"


class TestGetVersionValue:
	def test_version_number(self):
		v = {"id": "abc123", "version_number": "1.0.0"}
		assert get_version_value(v, use_id=False) == "1.0.0"

	def test_id(self):
		v = {"id": "abc123", "version_number": "1.0.0"}
		assert get_version_value(v, use_id=True) == "abc123"

	def test_with_transform(self):
		v = {"id": "abc123", "version_number": "21.11.153+neoforge"}
		transform = {"pattern": r"\+.*$", "replacement": ""}
		assert get_version_value(v, use_id=False, transform=transform) == "21.11.153"

	def test_id_ignores_transform(self):
		v = {"id": "abc123", "version_number": "21.11.153+neoforge"}
		transform = {"pattern": r"\+.*$", "replacement": ""}
		assert get_version_value(v, use_id=True, transform=transform) == "abc123"


# ── remote branch / push helpers ────────────────────────────────────


class TestRemoteBranchHelpers:
	@patch("subprocess.run")
	def test_get_remote_branch_head_parses_exact_match(self, mock_run):
		mock_run.return_value = MagicMock(
			stdout=(
				"deadbeef1234567890\trefs/heads/modrinth-deps/main/modmenu\n"
				"cafebabe1234567890\trefs/heads/something-else\n"
			)
		)

		assert get_remote_branch_head("modrinth-deps/main/modmenu") == "deadbeef1234567890"

	@patch("subprocess.run")
	def test_get_remote_branch_head_returns_none_when_missing(self, mock_run):
		mock_run.return_value = MagicMock(stdout="")
		assert get_remote_branch_head("modrinth-deps/main/modmenu") is None

	@patch("main.git")
	@patch("main.get_remote_branch_head", return_value="deadbeef1234567890")
	def test_push_branch_uses_explicit_lease_for_existing_branch(self, mock_head, mock_git):
		push_branch("modrinth-deps/main/modmenu")
		mock_git.assert_called_once_with(
			"push",
			"--force-with-lease=refs/heads/modrinth-deps/main/modmenu:deadbeef1234567890",
			"origin",
			"modrinth-deps/main/modmenu",
		)

	@patch("main.git")
	@patch("main.get_remote_branch_head", return_value=None)
	def test_push_branch_uses_regular_force_with_lease_for_new_branch(self, mock_head, mock_git):
		push_branch("modrinth-deps/main/modmenu")
		mock_git.assert_called_once_with(
			"push",
			"--force-with-lease",
			"origin",
			"modrinth-deps/main/modmenu",
		)
