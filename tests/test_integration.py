"""Integration tests using mocked git/gh but real Modrinth API for query_modrinth.

Tests the process_dependency flow end-to-end with a fake git repo.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from main import process_dependency, query_modrinth


# ── query_modrinth integration (real API) ────────────────────────────

class TestQueryModrinthIntegration:
    """These hit the real API to verify query_modrinth works end-to-end."""

    def test_fabric_api_returns_results(self):
        versions = query_modrinth("fabric-api", "1.21.4", "fabric")
        assert len(versions) > 0
        assert all("fabric" in [l.lower() for l in v["loaders"]] for v in versions)

    def test_case_insensitive_loader(self):
        lower = query_modrinth("fabric-api", "1.21.4", "fabric")
        upper = query_modrinth("fabric-api", "1.21.4", "Fabric")
        # Should get same results
        assert len(lower) == len(upper)
        assert {v["id"] for v in lower} == {v["id"] for v in upper}

    def test_nonexistent_slug(self):
        """Nonexistent project should raise HTTP error."""
        with pytest.raises(Exception):
            query_modrinth("this-mod-definitely-does-not-exist-12345", "1.21.4", "fabric")

    def test_lootr_with_use_id(self):
        """Lootr example from the config — verify it works with use_id pattern."""
        versions = query_modrinth("lootr", "1.21.1", "fabric")
        if versions:
            # Every version should have an id and version_number
            for v in versions:
                assert v["id"]
                assert v["version_number"]


# ── process_dependency with mocked git ───────────────────────────────

class TestProcessDependencyMocked:
    """Test process_dependency logic with mocked git/gh/modrinth."""

    def _make_versions(self, version_number="2.0.0", version_type="release"):
        return [{
            "id": "newid123",
            "version_number": version_number,
            "name": f"Test {version_number}",
            "date_published": "2026-01-01T00:00:00Z",
            "loaders": ["fabric"],
            "game_versions": ["1.21.4"],
            "version_type": version_type,
        }]

    @patch("main.query_modrinth")
    @patch("main.git")
    @patch("main.branch_exists_on_remote", return_value=False)
    @patch("main.pr_exists", return_value=False)
    @patch("main.gh")
    @patch("subprocess.run")
    def test_creates_pr_when_update_available(
        self, mock_subrun, mock_gh, mock_pr, mock_branch, mock_git, mock_query, tmp_path
    ):
        mock_query.return_value = self._make_versions("2.0.0")
        # git diff --cached --quiet returns 1 (changes exist)
        mock_subrun.return_value = MagicMock(returncode=1)

        gradle = tmp_path / "gradle.properties"
        gradle.write_text("dep_version=1.0.0\nminecraft_version=1.21.4\nmod_loader=fabric\n")

        result = process_dependency(
            "dep_version",
            {"slug": "test-mod"},
            gradle,
            {"dep_version": "1.0.0"},
            "1.21.4",
            "fabric",
            "main",
        )
        assert result is True
        # Verify PR was created via gh
        mock_gh.assert_called()

    @patch("main.query_modrinth")
    def test_skips_when_up_to_date(self, mock_query, tmp_path):
        mock_query.return_value = [{
            "id": "curid",
            "version_number": "1.0.0",
            "name": "Test",
            "date_published": "2026-01-01T00:00:00Z",
            "loaders": ["fabric"],
            "game_versions": ["1.21.4"],
            "version_type": "release",
        }]

        result = process_dependency(
            "dep_version",
            {"slug": "test-mod"},
            tmp_path / "gradle.properties",
            {"dep_version": "1.0.0"},
            "1.21.4",
            "fabric",
            "main",
        )
        assert result is False

    @patch("main.query_modrinth")
    def test_skips_when_up_to_date_by_id(self, mock_query, tmp_path):
        """When use_id=True, current value is an ID — should still detect up-to-date."""
        mock_query.return_value = [{
            "id": "abc123",
            "version_number": "1.0.0",
            "name": "Test",
            "date_published": "2026-01-01T00:00:00Z",
            "loaders": ["fabric"],
            "game_versions": ["1.21.4"],
            "version_type": "release",
        }]

        result = process_dependency(
            "dep_version",
            {"slug": "test-mod", "use_id": True},
            tmp_path / "gradle.properties",
            {"dep_version": "abc123"},
            "1.21.4",
            "fabric",
            "main",
        )
        assert result is False

    @patch("main.query_modrinth")
    def test_skips_missing_property(self, mock_query, tmp_path):
        result = process_dependency(
            "nonexistent_key",
            {"slug": "test-mod"},
            tmp_path / "gradle.properties",
            {},
            "1.21.4",
            "fabric",
            "main",
        )
        assert result is False
        mock_query.assert_not_called()

    @patch("main.query_modrinth")
    def test_skips_when_no_versions(self, mock_query, tmp_path):
        mock_query.return_value = []
        result = process_dependency(
            "dep_version",
            {"slug": "test-mod"},
            tmp_path / "gradle.properties",
            {"dep_version": "1.0.0"},
            "1.21.4",
            "fabric",
            "main",
        )
        assert result is False

    @patch("main.query_modrinth")
    def test_stability_filtering_skips_beta_when_on_release(self, mock_query, tmp_path):
        """If current is a release, a newer beta should not be picked."""
        mock_query.return_value = [
            {
                "id": "beta1",
                "version_number": "2.0.0-beta.1",
                "name": "Beta",
                "date_published": "2026-02-01T00:00:00Z",
                "loaders": ["fabric"],
                "game_versions": ["1.21.4"],
                "version_type": "beta",
            },
            {
                "id": "rel1",
                "version_number": "1.0.0",
                "name": "Release",
                "date_published": "2026-01-01T00:00:00Z",
                "loaders": ["fabric"],
                "game_versions": ["1.21.4"],
                "version_type": "release",
            },
        ]

        result = process_dependency(
            "dep_version",
            {"slug": "test-mod"},
            tmp_path / "gradle.properties",
            {"dep_version": "1.0.0"},
            "1.21.4",
            "fabric",
            "main",
        )
        assert result is False  # 1.0.0 is already the latest release

    @patch("main.query_modrinth")
    @patch("main.git")
    @patch("main.branch_exists_on_remote", return_value=False)
    @patch("main.pr_exists", return_value=False)
    @patch("main.gh")
    @patch("subprocess.run")
    def test_stability_filtering_allows_beta_when_on_beta(
        self, mock_subrun, mock_gh, mock_pr, mock_branch, mock_git, mock_query, tmp_path
    ):
        """If current is a beta, a newer beta should be picked."""
        mock_query.return_value = [
            {
                "id": "beta2",
                "version_number": "2.0.0-beta.2",
                "name": "Beta 2",
                "date_published": "2026-02-01T00:00:00Z",
                "loaders": ["fabric"],
                "game_versions": ["1.21.4"],
                "version_type": "beta",
            },
            {
                "id": "beta1",
                "version_number": "2.0.0-beta.1",
                "name": "Beta 1",
                "date_published": "2026-01-01T00:00:00Z",
                "loaders": ["fabric"],
                "game_versions": ["1.21.4"],
                "version_type": "beta",
            },
        ]
        mock_subrun.return_value = MagicMock(returncode=1)

        gradle = tmp_path / "gradle.properties"
        gradle.write_text("dep_version=2.0.0-beta.1\n")

        result = process_dependency(
            "dep_version",
            {"slug": "test-mod"},
            gradle,
            {"dep_version": "2.0.0-beta.1"},
            "1.21.4",
            "fabric",
            "main",
        )
        assert result is True
