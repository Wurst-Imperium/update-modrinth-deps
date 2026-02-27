"""Tests for detect_base_branch() and safe_checkout()."""

import pytest
from main import detect_base_branch, is_usable_ci_branch_ref, safe_checkout
from unittest.mock import MagicMock, patch


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
	"""Test CI branch detection priority and failure modes.

	Priority order:
	1. Named branch (git rev-parse --abbrev-ref HEAD != "HEAD")
	2. Remote branch matching HEAD (git branch -r --points-at HEAD)
	3. GITHUB_BASE_REF / GITHUB_REF_NAME env vars
	"""

	def _mock_run_for(self, rev_parse="HEAD\n", points_at="", points_at_rc=0, checkout_rc=0):
		"""Build a side_effect function for subprocess.run based on the command."""

		def side_effect(cmd, **kwargs):
			if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
				return MagicMock(returncode=0, stdout=rev_parse)
			if cmd[:4] == ["git", "branch", "-r", "--points-at"]:
				return MagicMock(returncode=points_at_rc, stdout=points_at)
			if cmd[:3] == ["git", "checkout", "-B"]:
				return MagicMock(
					returncode=checkout_rc,
					stderr="fatal: error" if checkout_rc else "",
				)
			return MagicMock(returncode=0, stdout="")

		return side_effect

	# ── Priority 1: Named branch ─────────────────────────────────────

	@patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": ""}, clear=False)
	@patch("subprocess.run")
	def test_uses_named_branch(self, mock_run):
		"""If HEAD is on a named branch, use it directly."""
		mock_run.side_effect = self._mock_run_for(rev_parse="my-feature\n")
		assert detect_base_branch() == "my-feature"

	@patch.dict(
		"os.environ",
		{"GITHUB_BASE_REF": "main", "GITHUB_REF_NAME": "master"},
		clear=False,
	)
	@patch("subprocess.run")
	def test_named_branch_takes_priority_over_env(self, mock_run):
		"""Named branch should be preferred even when env vars are set."""
		mock_run.side_effect = self._mock_run_for(rev_parse="1.21.11-neoforge\n")
		assert detect_base_branch() == "1.21.11-neoforge"

	# ── Priority 2: Remote branch matching HEAD ──────────────────────

	@patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": ""}, clear=False)
	@patch("subprocess.run")
	def test_detached_head_finds_remote_branch(self, mock_run):
		"""Detached HEAD should find the matching remote branch."""
		mock_run.side_effect = self._mock_run_for(
			rev_parse="HEAD\n",
			points_at="  origin/1.21.11-neoforge\n",
		)
		assert detect_base_branch() == "1.21.11-neoforge"

	@patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": ""}, clear=False)
	@patch("subprocess.run")
	def test_detached_head_skips_head_pointer(self, mock_run):
		"""Should skip 'origin/HEAD -> origin/master' lines."""
		mock_run.side_effect = self._mock_run_for(
			rev_parse="HEAD\n",
			points_at="  origin/HEAD -> origin/master\n  origin/my-branch\n",
		)
		assert detect_base_branch() == "my-branch"

	@patch.dict(
		"os.environ",
		{"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": "master"},
		clear=False,
	)
	@patch("subprocess.run")
	def test_detached_head_remote_branch_over_env(self, mock_run):
		"""Remote branch detection should take priority over GITHUB_REF_NAME."""
		mock_run.side_effect = self._mock_run_for(
			rev_parse="HEAD\n",
			points_at="  origin/1.21.11-neoforge\n",
		)
		assert detect_base_branch() == "1.21.11-neoforge"

	# ── Priority 3: CI env var fallbacks ─────────────────────────────

	@patch.dict(
		"os.environ",
		{"GITHUB_BASE_REF": "main", "GITHUB_REF_NAME": "123/merge"},
		clear=False,
	)
	@patch("subprocess.run")
	def test_env_fallback_prefers_base_ref(self, mock_run):
		"""When detached with no remote match, prefer GITHUB_BASE_REF."""
		mock_run.side_effect = self._mock_run_for(
			rev_parse="HEAD\n",
			points_at="",
		)
		assert detect_base_branch() == "main"

	@patch.dict(
		"os.environ",
		{"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": "develop"},
		clear=False,
	)
	@patch("subprocess.run")
	def test_env_fallback_uses_ref_name(self, mock_run):
		"""Falls back to GITHUB_REF_NAME when GITHUB_BASE_REF is empty."""
		mock_run.side_effect = self._mock_run_for(
			rev_parse="HEAD\n",
			points_at="",
		)
		assert detect_base_branch() == "develop"

	@patch.dict(
		"os.environ",
		{"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": "123/merge"},
		clear=False,
	)
	@patch("subprocess.run")
	def test_env_fallback_skips_synthetic_ref(self, mock_run):
		"""Synthetic refs like 123/merge should be skipped."""
		mock_run.side_effect = self._mock_run_for(
			rev_parse="HEAD\n",
			points_at="",
		)
		with pytest.raises(SystemExit):
			detect_base_branch()

	# ── Failure cases ────────────────────────────────────────────────

	@patch.dict("os.environ", {"GITHUB_BASE_REF": "", "GITHUB_REF_NAME": ""}, clear=False)
	@patch("subprocess.run")
	def test_detached_head_no_remote_no_env_exits(self, mock_run):
		"""Detached HEAD with no remote match and no env vars should exit."""
		mock_run.side_effect = self._mock_run_for(
			rev_parse="HEAD\n",
			points_at="",
		)
		with pytest.raises(SystemExit):
			detect_base_branch()

	@patch.dict(
		"os.environ",
		{"GITHUB_BASE_REF": "main", "GITHUB_REF_NAME": ""},
		clear=False,
	)
	@patch("subprocess.run")
	def test_env_checkout_failure_exits(self, mock_run):
		"""If env var checkout fails, should exit immediately."""
		mock_run.side_effect = self._mock_run_for(
			rev_parse="HEAD\n",
			points_at="",
			checkout_rc=1,
		)
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
