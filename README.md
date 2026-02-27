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
  # Needed to create/update PRs
  pull-requests: write

jobs:
  update-deps:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Update Modrinth Dependencies
        uses: Wurst-Imperium/update-modrinth-deps@v1
```

and add a `modrinth_deps.json` config file that maps your `gradle.properties` keys to Modrinth slugs:

```json
{
  "fabric_api_version": "fabric-api",
  "sodium_version": "sodium",
  "modmenu_version": "modmenu",
  "cloth_config_version": "cloth-config",
  "lootr_version": {
    "slug": "lootr",
    "use_id": true
  }
}
```

If one of your dependencies re-uses the same version, forcing you to specify it by version ID in your `gradle.properties`, set `"use_id": true` for that dependency.

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
	// some other Maven is fine as long as the versions are the same.

	// This is not the case for Lootr, which re-uses the same version
	// for Fabric and NeoForge builds. You have to load that one from
	// Modrinth Maven.
	modImplementation "maven.modrinth:lootr:${project.lootr_version}"
}
```

## Multiple branches

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
  # Needed to create/update PRs
  pull-requests: write

jobs:
  update-deps:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        branch: ['1.21.10', '1.21.11', '26.1']
    steps:
      - name: Checkout
        uses: actions/checkout@v6
        with:
          ref: ${{ matrix.branch }}

      - name: Update Modrinth Dependencies
        uses: Wurst-Imperium/update-modrinth-deps@v1
```

## Limitations

- This bot does not auto-delete PRs. You can set up auto-deletion in your repository settings under `General` > `Pull Requests` > `Automatically delete head branches`.

- When you make manual edits to the target branch, this bot won't rebase the PR automatically. Go to `Settings` > `General` > `Pull Requests` > `Always suggest updating pull request branches` and you'll have a button to do that on demand.

- When there is a new update before you've merged the previous one, this bot will re-create the PR branch and potentially overwrite your manual edits.
