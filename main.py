#!/usr/bin/env python3
"""Check for Modrinth dependency updates and open PRs."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "Wurst-Imperium/update-modrinth-deps (github.com/Wurst-Imperium)"


def detect_line_ending(text: str) -> str:
    """Detect dominant line ending in a file's text."""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def read_gradle_properties(path: Path) -> dict[str, str]:
    """Parse a gradle.properties file into a dict."""
    props = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            props[key.strip()] = value.strip()
    return props


def write_gradle_property(path: Path, key: str, new_value: str) -> None:
    """Update a single key in gradle.properties, preserving formatting and line endings."""
    raw = path.read_text()
    eol = detect_line_ending(raw)
    lines = raw.splitlines(keepends=True)
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={new_value}{eol}"
            break
    path.write_text("".join(lines))


def query_modrinth(
    slug: str, minecraft_version: str, mod_loader: str
) -> list[dict]:
    """Query Modrinth for versions matching the given MC version and loader."""
    params = {
        "game_versions": json.dumps([minecraft_version]),
        "loaders": json.dumps([mod_loader.lower()]),
    }
    resp = requests.get(
        f"{MODRINTH_API}/project/{slug}/version",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    versions = resp.json()

    # Filter out alpha/beta versions — only pick "release" channel
    return [v for v in versions if v.get("version_type") == "release"]


def get_version_value(version: dict, use_id: bool) -> str:
    """Get the value to write to gradle.properties."""
    if use_id:
        return version["id"]
    return version["version_number"]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, printing it first."""
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def git(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return run(["git", *args], **kwargs)


def gh(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return run(["gh", *args], **kwargs)


def branch_exists_on_remote(branch: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        capture_output=True,
        text=True,
    )
    return f"refs/heads/{branch}\n" in result.stdout or result.stdout.rstrip().endswith(f"refs/heads/{branch}")


def pr_exists(branch: str) -> bool:
    result = subprocess.run(
        ["gh", "pr", "view", branch, "--json", "state"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    try:
        state = json.loads(result.stdout).get("state")
        return state == "OPEN"
    except (json.JSONDecodeError, KeyError):
        return False


def detect_base_branch() -> str:
    """Detect the base branch, handling detached HEAD in GitHub Actions."""
    # Prefer GITHUB_REF_NAME in CI
    ref_name = os.environ.get("GITHUB_REF_NAME")
    if ref_name:
        # Ensure local branch exists tracking the remote
        subprocess.run(
            ["git", "checkout", "-B", ref_name, f"origin/{ref_name}"],
            capture_output=True,
        )
        return ref_name

    # Fallback: current branch name
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    branch = result.stdout.strip()
    if branch == "HEAD":
        print("❌ Detached HEAD and GITHUB_REF_NAME not set. Cannot determine base branch.")
        sys.exit(1)
    return branch


def safe_checkout(branch: str) -> None:
    """Checkout a branch, discarding local changes. Silently ignores errors."""
    subprocess.run(
        ["git", "checkout", "-f", branch],
        capture_output=True,
    )


def process_dependency(
    prop_key: str,
    dep_config: dict,
    gradle_path: Path,
    props: dict[str, str],
    minecraft_version: str,
    mod_loader: str,
    base_branch: str,
) -> bool:
    """Check and update a single dependency. Returns True if a PR was created/updated."""
    slug = dep_config["slug"]
    use_id = dep_config.get("use_id", False)
    current_value = props.get(prop_key)

    if current_value is None:
        print(f"⚠️  {prop_key} not found in gradle.properties, skipping")
        return False

    print(f"\n{'='*60}")
    print(f"Checking {slug} (property: {prop_key})")
    print(f"  Current: {current_value}")

    versions = query_modrinth(slug, minecraft_version, mod_loader)
    if not versions:
        print(f"  No compatible versions found for MC {minecraft_version} + {mod_loader}")
        return False

    latest = versions[0]  # Modrinth returns newest first
    new_value = get_version_value(latest, use_id)

    # Check if current value matches either version_number or id
    if current_value in (latest["version_number"], latest["id"]):
        print(f"  ✅ Already up to date")
        return False

    print(f"  🆕 Update available: {new_value}")
    print(f"     Name: {latest['name']}")
    print(f"     Published: {latest['date_published']}")

    # Create or update the PR branch
    branch = f"modrinth-deps/{slug}"

    # Start from the base branch (force-reset to clean state)
    git("checkout", base_branch)
    git("pull", "--ff-only", "origin", base_branch)

    if branch_exists_on_remote(branch):
        # Force-reset branch to base — intentional: we always rebuild from
        # the latest base branch to avoid merge conflicts. Any manual edits
        # on the PR branch will be overwritten.
        git("checkout", "-B", branch, f"origin/{base_branch}")
    else:
        git("checkout", "-b", branch)

    # Update gradle.properties
    write_gradle_property(gradle_path, prop_key, new_value)

    # Commit and push
    display_version = latest["version_number"] if use_id else new_value
    commit_msg = f"Update {slug} to {display_version}"

    git("add", str(gradle_path))

    # Check if there are actual changes
    result = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if result.returncode == 0:
        print(f"  ✅ No changes needed (branch may already be updated)")
        git("checkout", base_branch)
        return False

    git("commit", "-m", commit_msg)
    git("push", "--force-with-lease", "origin", branch)

    # Create or update PR
    pr_title = commit_msg
    pr_body = (
        f"Updates `{prop_key}` from `{current_value}` to `{new_value}`.\n\n"
        f"**Mod:** [{slug}](https://modrinth.com/mod/{slug})\n"
        f"**Version:** [{latest['name']}](https://modrinth.com/mod/{slug}/version/{latest['id']})\n"
        f"**Minecraft:** {minecraft_version}\n"
        f"**Loader:** {mod_loader}\n\n"
        f"---\n"
        f"*This PR was automatically created by "
        f"[update-modrinth-deps](https://github.com/Wurst-Imperium/update-modrinth-deps).*"
    )

    if pr_exists(branch):
        print(f"  📝 Updating existing PR")
        gh("pr", "edit", branch, "--title", pr_title, "--body", pr_body)
    else:
        print(f"  🔀 Creating PR")
        gh(
            "pr",
            "create",
            "--title",
            pr_title,
            "--body",
            pr_body,
            "--base",
            base_branch,
            "--head",
            branch,
        )

    git("checkout", base_branch)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="modrinth_deps.json",
        help="Path to dependency config JSON",
    )
    parser.add_argument(
        "--gradle-properties",
        default="gradle.properties",
        help="Path to gradle.properties",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    gradle_path = Path(args.gradle_properties)

    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)
    if not gradle_path.exists():
        print(f"❌ gradle.properties not found: {gradle_path}")
        sys.exit(1)

    config = json.loads(config_path.read_text())
    props = read_gradle_properties(gradle_path)

    minecraft_version = props.get("minecraft_version")
    mod_loader = props.get("mod_loader")

    if not minecraft_version:
        print("❌ minecraft_version not found in gradle.properties")
        sys.exit(1)
    if not mod_loader:
        print("❌ mod_loader not found in gradle.properties")
        sys.exit(1)

    print(f"Minecraft: {minecraft_version}")
    print(f"Loader: {mod_loader}")

    # Configure git
    git("config", "user.name", "github-actions[bot]")
    git(
        "config",
        "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com",
    )

    # Detect base branch (handles detached HEAD in CI)
    base_branch = detect_base_branch()
    print(f"Base branch: {base_branch}")

    updated = 0
    for prop_key, dep_config in config.items():
        # Allow shorthand: just a slug string instead of full config object
        if isinstance(dep_config, str):
            dep_config = {"slug": dep_config}
        try:
            if process_dependency(
                prop_key,
                dep_config,
                gradle_path,
                props,
                minecraft_version,
                mod_loader,
                base_branch,
            ):
                updated += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            safe_checkout(base_branch)
            continue

    print(f"\n{'='*60}")
    print(f"Done. {updated} PR(s) created/updated.")


if __name__ == "__main__":
    main()
