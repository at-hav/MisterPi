# Managed MisterPi library

This repository is the source of truth for Waian's curated MiSTer game catalog and generated `.mgl` frontend. It contains metadata and management code only; it does not contain games.

## Install

Install from the MiSTer shell as root:

```bash
wget -qO- https://raw.githubusercontent.com/at-hav/MisterPi/f6b1b46db133c9c56bd1b9e02a01ad68d2c83529/install.sh | bash
```

The installed MiSTer image has a 2021 CA bundle that causes its `curl` to reject GitHub's current certificate chain. `wget` on the same image validates GitHub successfully, so the bootstrap and updater use `wget` and never disable TLS verification.

Each CSV row owns its direct HTTP(S) source in `download_url`. A missing target without a URL stops the update. Downloads are written to a temporary sibling, checked against the row's SHA-1, and atomically renamed into place. Existing games are not downloaded or hashed during a normal update. Because the CSV is public, URLs must not contain credentials or private tokens.

After installation, run an on-demand update from the MiSTer Scripts menu or shell:

```bash
/media/fat/Scripts/update-waian.sh
```

## Update sequence

An update:

1. downloads a clean repository snapshot into `/media/fat/.waian`;
2. synchronizes `misteraddons/Mister-Input-Maps`, updating previously managed files while preserving local overrides and extra mappings;
3. detects missing catalog launch targets and downloads them from their CSV URLs;
4. builds the complete `_Waian's Picks` menu in a staging directory;
5. swaps the menu tree and validates every catalog target, core, `.mgl`, and `.mgl` reference;
6. installs the catalog, helper scripts, and `Scripts/update-waian.sh`.

If generation or validation fails, the previous menu is restored. The update lock prevents concurrent runs.

## Important limitation

The current CSV identifies one launch target per game. For `.cue` games, that does not describe associated `.bin` tracks. A fresh HTTP mirror must therefore already provide those dependent files out of band, or the catalog schema must be extended to describe downloadable game bundles before this can reproduce CD games on an empty system.

## Manual commands

```bash
python3 sync_games.py --csv game-library.csv --games-root /media/fat/games --no-download
python3 hash_game_library.py --csv game-library.csv
python3 waians_picks.py --csv game-library.csv
python3 check_library.py --csv game-library.csv
```

Use `manage.sh --dry-run` to inspect a managed update without replacing the frontend.

## Controller mappings

The installed main controller set came from [misteraddons/Mister-Input-Maps](https://github.com/misteraddons/Mister-Input-Maps), specifically `Main_Inputs/MiSTer_Input_Maps-20211004.zip` at the time this repository was created. The device also has eight extra mappings and a locally modified `input_2dc8_0651_v3.map`; synchronization preserves these.
