# Update Modrinth Deps Action

Dependabot for Minecraft mods.

- Keeps your dependencies up to date, as long as they are available on Modrinth.
- Creates/updates PRs just like other dependency bots.
- Works even if your mod isn't on Modrinth. Just your dependencies need to be.

## How to use

Make a workflow like this:

```yaml
# .github/workflows/update_modrinth_deps.yml
name: Update Modrinth Dependencies

on:
  schedule:
    - cron: "0 0 * * *"  # Every day at midnight (UTC)
  workflow_dispatch:

permissions:
  # Needed to edit gradle.properties on the PR branches
  contents: write

jobs:
  update-deps:
    runs-on: ubuntu-latest
    steps:
      - name: Update Modrinth Dependencies
        uses: Wurst-Imperium/update-modrinth-deps@v1
        with:
          ref: ${{ github.ref_name }}
          # Needed to have CI run against the generated PRs
          token: ${{ secrets.PR_TOKEN }}
```

For the `PR_TOKEN` secret, generate a [Personal Access Token](https://github.com/settings/personal-access-tokens) with `pull-requests: write` permission. (See below if you want to use the default `GITHUB_TOKEN` instead, but be aware that a PAT is required if you want CI to run on the generated PRs.)

**Note:** Older versions had a manual `actions/checkout` step instead of the `ref` input. This is no longer recommended as it can cause skipped CI runs on the generated PRs.

Then add a `modrinth_deps.json` config file that maps your `gradle.properties` keys to Modrinth slugs:

```json
{
  "fabric_api_version": "fabric-api",
  "sodium_version": "sodium",
  "modmenu_version": "modmenu",
  "lootr_version": {
    "slug": "lootr",
    "use_id": true
  },
  "cloth_config_version": {
    "slug": "cloth-config",
    "version_transform": {
      "pattern": "\\+(fabric|neoforge)$",
      "replacement": ""
    }
  }
}
```

If one of your dependencies re-uses the same version, forcing you to specify it by version ID in your `gradle.properties`, set `"use_id": true` for that dependency.

If you are loading a dependency from its own Maven and it uses slightly different versioning there than it does on Modrinth, you may be able to work around that by adding a `version_transform` regex (e.g. to remove Cloth Config's `+fabric` or `+neoforge` suffixes). Be warned that this won't always work. It is much more reliable to load such mods directly from Modrinth Maven if possible.

And if you haven't already, make it so your `build.gradle` reads versions from `gradle.properties` instead of hardcoding them:

```gradle
// Add Modrinth Maven (optional, depending on which mods you use)
repositories {
	exclusiveContent {
		forRepository {
			maven {
				name = "Modrinth"
				url = "https://api.modrinth.com/maven"
			}
		}
		filter {
			includeGroup "maven.modrinth"
		}
	}
}

dependencies {
	// Fabric API - you probably already have this
	modImplementation "net.fabricmc.fabric-api:fabric-api:${project.fabric_api_version}"

	// Sodium example loaded from Modrinth Maven
	modImplementation "maven.modrinth:sodium:${project.sodium_version}"

	// Mod Menu example from their own Maven
	modApi "com.terraformersmc:modmenu:${project.modmenu_version}"
	include "com.terraformersmc:modmenu:${project.modmenu_version}"

	// The dependencies just have to exist on Modrinth. Loading them from
	// some other Maven is fine as long as the versions are the same (or
	// you've `version_transform`ed them to be the same).

	// This is not the case for Lootr, which re-uses the same version
	// for Fabric and NeoForge builds. You have to load that one from
	// Modrinth Maven.
	modImplementation "maven.modrinth:lootr:${project.lootr_version}"
}
```

## Special case: Multiple branches

By default, scheduled workflows only run on your default branch. If you want to keep your dependencies up to date across multiple branches (e.g. all of your supported Minecraft versions), you can use a matrix like so:

```yaml
# .github/workflows/update_modrinth_deps.yml
name: Update Modrinth Dependencies

on:
  schedule:
    - cron: "0 0 * * *"  # Every day at midnight (UTC)
  workflow_dispatch:

permissions:
  # Needed to edit gradle.properties on the PR branches
  contents: write

jobs:
  update-deps:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        branch: ['1.21.10', '1.21.11', '26.1']
    steps:
      - name: Update Modrinth Dependencies
        uses: Wurst-Imperium/update-modrinth-deps@v1
        with:
          ref: ${{ matrix.branch }}
          # Needed to have CI run against the generated PRs
          token: ${{ secrets.PR_TOKEN }}
```

## Special case: No PAT, no CI

PRs created with the default `GITHUB_TOKEN` won't trigger CI workflows (GitHub prevents recursive runs). If that's fine for your use case, you can skip creating a PAT and just add the two required permissions to the workflow like so:

```yaml
# .github/workflows/update_modrinth_deps.yml
name: Update Modrinth Dependencies

on:
  schedule:
    - cron: "0 0 * * *"  # Every day at midnight (UTC)
  workflow_dispatch:

permissions:
  # Needed to edit gradle.properties on the PR branches
  contents: write
  # Needed to create/update PRs
  pull-requests: write

jobs:
  update-deps:
    runs-on: ubuntu-latest
    steps:
      - name: Update Modrinth Dependencies
        uses: Wurst-Imperium/update-modrinth-deps@v1
        with:
          ref: ${{ github.ref_name }}
```

## Limitations

- This bot does not auto-delete PRs. You can set up auto-deletion in your repository settings under `General` > `Pull Requests` > `Automatically delete head branches`.

- When you make manual edits to the target branch, this bot won't rebase the PR automatically. Go to `Settings` > `General` > `Pull Requests` > `Always suggest updating pull request branches` and you'll have a button to do that on demand.

- When there is a new update before you've merged the previous one, this bot will re-create the PR branch and potentially overwrite your manual edits.

- Modrinth is the source of truth for everything this bot does. That can cause issues with dependencies loaded from other Maven repositories. Tools like `version_transform` are included to help with this, but it will never be perfect.
