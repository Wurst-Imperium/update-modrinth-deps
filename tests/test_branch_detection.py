"""Tests for detect_base_branch() and safe_checkout()."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from main import detect_base_branch, safe_checkout


class TestDetectBaseBranch:
    """Test CI branch detection priority and failure modes."""

    @patch.dict("os.environ", {"GITHUB_BASE_REF": "main", "GITHUB_REF_NAME": "123/merge"}, clear=False)
    @patch("subprocess.run")
    def test_prefers_base_ref_over_ref_name(self, mock_run):
        """On PR events, GITHUB_BASE_REF should be used, not GITHUB_REF_NAME."""
        mock_run.return_value = MagicMock(returncode=0)
        assert detect_base_branch() == "main"
        # Should checkout the base ref
        mock_run.assert_called_once_with(
            ["git", "checkout", "-B", "main", "origin/main"],
            capture_output=True,
            text=True,
        )

    @patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": "develop"}, clear=False)
    @patch("subprocess.run")
    def test_falls_back_to_ref_name(self, mock_run):
        """When GITHUB_BASE_REF is empty, use GITHUB_REF_NAME."""
        mock_run.return_value = MagicMock(returncode=0)
        assert detect_base_branch() == "develop"

    @patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": "123/merge"}, clear=False)
    @patch("subprocess.run")
    def test_skips_ref_name_with_slash(self, mock_run):
        """GITHUB_REF_NAME like '123/merge' should be skipped (not a branch name)."""
        # Falls through to git rev-parse
        mock_run.return_value = MagicMock(returncode=0, stdout="my-branch\n")
        assert detect_base_branch() == "my-branch"

    @patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": ""}, clear=False)
    @patch("subprocess.run")
    def test_falls_back_to_git_rev_parse(self, mock_run):
        """When no env vars set, falls back to git rev-parse."""
        mock_run.return_value = MagicMock(returncode=0, stdout="feature-branch\n")
        assert detect_base_branch() == "feature-branch"

    @patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": ""}, clear=False)
    @patch("subprocess.run")
    def test_detached_head_exits(self, mock_run):
        """Detached HEAD with no env vars should exit."""
        mock_run.return_value = MagicMock(returncode=0, stdout="HEAD\n")
        with pytest.raises(SystemExit):
            detect_base_branch()

    @patch.dict("os.environ", {"GITHUB_BASE_REF": "main", "GITHUB_REF_NAME": ""}, clear=False)
    @patch("subprocess.run")
    def test_checkout_failure_exits(self, mock_run):
        """If git checkout fails, should exit immediately."""
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal: not a git repo")
        with pytest.raises(SystemExit):
            detect_base_branch()


class TestSafeCheckout:
    """Test that safe_checkout never raises."""

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        safe_checkout("main")  # should not raise
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_failure_is_silent(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        safe_checkout("nonexistent")  # should not raise

    @patch("subprocess.run", side_effect=Exception("boom"))
    def test_exception_propagates(self, mock_run):
        """subprocess.run itself throwing is not swallowed (unexpected)."""
        with pytest.raises(Exception, match="boom"):
            safe_checkout("main")
