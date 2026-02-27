"""Tests for detect_base_branch() and safe_checkout()."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from main import detect_base_branch, is_usable_ci_branch_ref, safe_checkout


class TestIsUsableCiBranchRef:
    def test_accepts_normal_branch(self):
        assert is_usable_ci_branch_ref("main")

    def test_accepts_branch_with_slash(self):
        assert is_usable_ci_branch_ref("feature/foo")

    def test_rejects_synthetic_merge_ref(self):
        assert not is_usable_ci_branch_ref("123/merge")

    def test_rejects_empty_or_head(self):
        assert not is_usable_ci_branch_ref("")
        assert not is_usable_ci_branch_ref("HEAD")


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
    def test_skips_synthetic_merge_ref_name(self, mock_run):
        """Synthetic PR merge refs like '123/merge' should be skipped."""
        # Falls through to git rev-parse
        mock_run.return_value = MagicMock(returncode=0, stdout="my-branch\n")
        assert detect_base_branch() == "my-branch"

    @patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": "feature/foo"}, clear=False)
    @patch("subprocess.run")
    def test_allows_ref_name_with_slash_for_real_branches(self, mock_run):
        """Real branch names may contain '/' and should be accepted."""
        mock_run.return_value = MagicMock(returncode=0)
        assert detect_base_branch() == "feature/foo"
        mock_run.assert_called_once_with(
            ["git", "checkout", "-B", "feature/foo", "origin/feature/foo"],
            capture_output=True,
            text=True,
        )

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
