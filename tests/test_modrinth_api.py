"""Tests that verify our assumptions about the Modrinth API.

These hit the real API — they validate that:
- Server-side filtering actually works as expected
- Sort order is newest-first
- Response schema matches what we rely on
"""

import json
import requests

MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "Wurst-Imperium/update-modrinth-deps-tests"
TIMEOUT = 30


def modrinth_versions(slug: str, mc_version: str, loader: str) -> list[dict]:
	"""Query Modrinth versions with proper array params."""
	resp = requests.get(
		f"{MODRINTH_API}/project/{slug}/version",
		params={
			"game_versions": json.dumps([mc_version]),
			"loaders": json.dumps([loader]),
		},
		headers={"User-Agent": USER_AGENT},
		timeout=TIMEOUT,
	)
	resp.raise_for_status()
	return resp.json()


# ── Server-side loader filtering ─────────────────────────────────────


class TestLoaderFiltering:
	"""Verify that the API actually filters by loader server-side.

	Uses cloth-config since it's available on both fabric and neoforge,
	so broken filtering would actually show cross-loader results.
	"""

	def test_fabric_only_returns_fabric(self):
		"""Fabric query on a multi-loader mod should only return fabric versions."""
		versions = modrinth_versions("cloth-config", "1.21.4", "fabric")
		assert len(versions) > 0
		for v in versions:
			assert "fabric" in [ldr.lower() for ldr in v["loaders"]], (
				f"Version {v['version_number']} has loaders {v['loaders']}, expected fabric"
			)

	def test_neoforge_only_returns_neoforge(self):
		"""NeoForge query on a multi-loader mod should only return neoforge versions."""
		versions = modrinth_versions("cloth-config", "1.21.4", "neoforge")
		assert len(versions) > 0
		for v in versions:
			assert "neoforge" in [ldr.lower() for ldr in v["loaders"]], (
				f"Version {v['version_number']} has loaders {v['loaders']}, expected neoforge"
			)

	def test_fabric_and_neoforge_return_different_results(self):
		"""Fabric and neoforge queries should not return identical version sets."""
		fabric = modrinth_versions("cloth-config", "1.21.4", "fabric")
		neoforge = modrinth_versions("cloth-config", "1.21.4", "neoforge")
		assert len(fabric) > 0
		assert len(neoforge) > 0
		fabric_ids = {v["id"] for v in fabric}
		neoforge_ids = {v["id"] for v in neoforge}
		assert fabric_ids != neoforge_ids, (
			"Fabric and NeoForge returned identical version sets — filtering may not be working"
		)


# ── Game version filtering ───────────────────────────────────────────


class TestGameVersionFiltering:
	"""Verify server-side game_versions filtering."""

	def test_mc_version_filter(self):
		versions = modrinth_versions("fabric-api", "1.21.4", "fabric")
		assert len(versions) > 0
		for v in versions:
			assert "1.21.4" in v["game_versions"], (
				f"Version {v['version_number']} doesn't list 1.21.4 in {v['game_versions']}"
			)

	def test_nonexistent_mc_version_returns_empty(self):
		versions = modrinth_versions("fabric-api", "99.99.99", "fabric")
		assert versions == []


# ── Sort order ───────────────────────────────────────────────────────


class TestSortOrder:
	"""Verify that versions come back newest-first (by date_published)."""

	def test_newest_first(self):
		versions = modrinth_versions("fabric-api", "1.21.4", "fabric")
		assert len(versions) >= 2, "Need at least 2 versions to test sort order"
		dates = [v["date_published"] for v in versions]
		assert dates == sorted(dates, reverse=True), f"Versions not sorted newest-first: {dates}"


# ── Response schema ──────────────────────────────────────────────────


class TestResponseSchema:
	"""Verify that the fields we rely on exist in the response."""

	REQUIRED_FIELDS = [
		"id",
		"version_number",
		"name",
		"date_published",
		"loaders",
		"game_versions",
		"version_type",
	]

	def test_required_fields_present(self):
		versions = modrinth_versions("fabric-api", "1.21.4", "fabric")
		assert len(versions) > 0
		for v in versions:
			for field in self.REQUIRED_FIELDS:
				assert field in v, f"Missing field '{field}' in version {v.get('id', '?')}"

	def test_version_type_values(self):
		"""version_type should be one of release/beta/alpha."""
		versions = modrinth_versions("fabric-api", "1.21.4", "fabric")
		for v in versions:
			assert v["version_type"] in ("release", "beta", "alpha"), (
				f"Unexpected version_type '{v['version_type']}' for {v['version_number']}"
			)

	def test_loaders_is_list(self):
		versions = modrinth_versions("fabric-api", "1.21.4", "fabric")
		for v in versions:
			assert isinstance(v["loaders"], list)

	def test_game_versions_is_list(self):
		versions = modrinth_versions("fabric-api", "1.21.4", "fabric")
		for v in versions:
			assert isinstance(v["game_versions"], list)


# ── use_id mode ──────────────────────────────────────────────────────


class TestUseIdMode:
	"""Verify that version IDs are stable identifiers we can rely on."""

	def test_ids_are_strings(self):
		versions = modrinth_versions("fabric-api", "1.21.4", "fabric")
		for v in versions:
			assert isinstance(v["id"], str)
			assert len(v["id"]) > 0

	def test_ids_are_unique(self):
		versions = modrinth_versions("fabric-api", "1.21.4", "fabric")
		ids = [v["id"] for v in versions]
		assert len(ids) == len(set(ids)), "Duplicate version IDs found"


# ── Stability filtering logic ────────────────────────────────────────


class TestStabilityFiltering:
	"""Test the stability ranking logic (unit-level, no API needed)."""

	STABILITY_RANK = {"release": 0, "beta": 1, "alpha": 2}

	def _filter(self, versions: list[dict], current_type: str) -> list[dict]:
		max_rank = self.STABILITY_RANK.get(current_type, 0)
		return [
			v
			for v in versions
			if self.STABILITY_RANK.get(v.get("version_type", "release"), 2) <= max_rank
		]

	def test_release_only_gets_releases(self):
		versions = [
			{"version_type": "release", "version_number": "1.0"},
			{"version_type": "beta", "version_number": "1.1-beta"},
			{"version_type": "alpha", "version_number": "1.2-alpha"},
		]
		filtered = self._filter(versions, "release")
		assert len(filtered) == 1
		assert filtered[0]["version_number"] == "1.0"

	def test_beta_gets_release_and_beta(self):
		versions = [
			{"version_type": "release", "version_number": "1.0"},
			{"version_type": "beta", "version_number": "1.1-beta"},
			{"version_type": "alpha", "version_number": "1.2-alpha"},
		]
		filtered = self._filter(versions, "beta")
		assert len(filtered) == 2
		types = {v["version_type"] for v in filtered}
		assert types == {"release", "beta"}

	def test_alpha_gets_everything(self):
		versions = [
			{"version_type": "release", "version_number": "1.0"},
			{"version_type": "beta", "version_number": "1.1-beta"},
			{"version_type": "alpha", "version_number": "1.2-alpha"},
		]
		filtered = self._filter(versions, "alpha")
		assert len(filtered) == 3

	def test_unknown_type_defaults_to_release_only(self):
		versions = [
			{"version_type": "release", "version_number": "1.0"},
			{"version_type": "beta", "version_number": "1.1-beta"},
		]
		filtered = self._filter(versions, "unknown")
		assert len(filtered) == 1
		assert filtered[0]["version_type"] == "release"

	def test_missing_version_type_treated_as_release(self):
		versions = [
			{"version_number": "1.0"},  # no version_type key
			{"version_type": "beta", "version_number": "1.1-beta"},
		]
		filtered = self._filter(versions, "release")
		assert len(filtered) == 1
		assert filtered[0]["version_number"] == "1.0"


# ── branch_exists_on_remote logic ────────────────────────────────────


class TestBranchExistsLogic:
	"""Test the exact-match logic for branch_exists_on_remote."""

	def _check(self, stdout: str, branch: str) -> bool:
		return f"refs/heads/{branch}\n" in stdout or stdout.rstrip().endswith(
			f"refs/heads/{branch}"
		)

	def test_exact_match(self):
		stdout = "abc123\trefs/heads/modrinth-deps/sodium\n"
		assert self._check(stdout, "modrinth-deps/sodium")

	def test_no_match(self):
		stdout = "abc123\trefs/heads/modrinth-deps/sodium\n"
		assert not self._check(stdout, "modrinth-deps/sod")

	def test_substring_no_false_positive(self):
		stdout = "abc123\trefs/heads/modrinth-deps/sodium-extra\n"
		assert not self._check(stdout, "modrinth-deps/sodium")

	def test_empty_output(self):
		assert not self._check("", "modrinth-deps/sodium")

	def test_no_trailing_newline(self):
		stdout = "abc123\trefs/heads/modrinth-deps/sodium"
		assert self._check(stdout, "modrinth-deps/sodium")

	def test_multiple_refs(self):
		stdout = (
			"abc123\trefs/heads/modrinth-deps/fabric-api\ndef456\trefs/heads/modrinth-deps/sodium\n"
		)
		assert self._check(stdout, "modrinth-deps/sodium")
		assert self._check(stdout, "modrinth-deps/fabric-api")
		assert not self._check(stdout, "modrinth-deps/modmenu")
