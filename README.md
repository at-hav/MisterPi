# Managed MisterPi library

This repository is the source of truth for Waian's curated MiSTer game catalog and generated `.mgl` frontend. It contains metadata and management code only; it does not contain games.

## Install

The GitHub repository owner still needs to be configured in `install.sh` and `update-waian.sh`. Once configured and published, install from the MiSTer shell as root:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/MisterPi/main/install.sh | bash
```

If catalog targets are missing, configure the HTTP mirror during the first install:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/MisterPi/main/install.sh \
  | GAME_BASE_URL=http://10.100.11.1/mister-games bash
```

The URL is saved in `/media/fat/.waian/.env`, which is never committed. It must mirror paths as:

```text
<GAME_BASE_URL>/<console_dir>/<game_file>
```

Each download is written to a temporary sibling, checked against the CSV SHA-1, and atomically renamed into place. Existing games are not downloaded or hashed during a normal update.

After installation, run an on-demand update from the MiSTer Scripts menu or shell:

```bash
/media/fat/Scripts/update-waian.sh
```

## Update sequence

An update:

1. downloads a clean repository snapshot into `/media/fat/.waian`;
2. synchronizes `misteraddons/Mister-Input-Maps`, updating previously managed files while preserving local overrides and extra mappings;
3. detects missing catalog launch targets and downloads them from the configured mirror;
4. builds the complete `_Waian's Picks` menu in a staging directory;
5. swaps the menu tree and validates every catalog target, core, `.mgl`, and `.mgl` reference;
6. installs the catalog, helper scripts, and `Scripts/update-waian.sh`.

If generation or validation fails, the previous menu is restored. The update lock prevents concurrent runs.

## Important limitation

The current CSV identifies one launch target per game. For `.cue` games, that does not describe associated `.bin` tracks. A fresh HTTP mirror must therefore already provide those dependent files out of band, or the catalog schema must be extended to describe downloadable game bundles before this can reproduce CD games on an empty system.

## Manual commands

```bash
python3 sync_games.py --csv game-library.csv --games-root /media/fat/games --no-download
python3 waians_picks.py --csv game-library.csv
python3 check_library.py --csv game-library.csv
```

Use `manage.sh --dry-run` to inspect a managed update without replacing the frontend.

## Controller mappings

The installed main controller set came from [misteraddons/Mister-Input-Maps](https://github.com/misteraddons/Mister-Input-Maps), specifically `Main_Inputs/MiSTer_Input_Maps-20211004.zip` at the time this repository was created. The device also has eight extra mappings and a locally modified `input_2dc8_0651_v3.map`; synchronization preserves these.
