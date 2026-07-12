# MisterPi project design

## Purpose

Manage the catalog, helper scripts, missing launch-target downloads, controller mappings, and generated Waian's Picks frontend without storing games in Git.

## Source of truth

- `game-library.csv` is authoritative metadata.
- Catalog targets resolve as `/media/fat/games/<console_dir>/<game_file>`.
- All populated `hash` values are SHA-1 checksums used to verify new downloads.
- Generated `.mgl` files are disposable and must not be hand-edited.
- `/media/fat/.waian/.env` holds the project-specific `GAME_BASE_URL` and is not versioned.

## Managed layout

- `/media/fat/.waian/repo`: last successfully installed repository snapshot
- `/media/fat/.waian/.env`: local HTTP source configuration
- `/media/fat/.waian/controller-maps.json`: upstream controller-map state
- `/media/fat/game-library.csv`: active catalog copy
- `/media/fat/*.py`: active helper copies
- `/media/fat/Scripts/update-waian.sh`: on-demand updater
- `/media/fat/_Waian's Picks`: transactionally generated frontend

## Update invariants

- Never traverse, copy, delete, or replace `/media/fat/games` as a tree.
- Only download an absent catalog target, validate its SHA-1, then atomically rename it.
- Generate a complete menu in staging and swap it only after generation succeeds.
- Escape XML text and attribute values in `.mgl` output.
- A missing core or target makes generation fail.
- Preserve controller files that differ from the last known upstream version.
- Preserve controller files not present upstream.
- Do not delete temporary files or directories outside `.waian`-owned paths.

## Known schema limitation

The catalog models one launch target, not all files needed by multi-file media. In particular, a `.cue` row does not enumerate its `.bin` tracks. Do not claim that HTTP synchronization can reconstruct those games until the source format is extended to downloadable bundles or a separate manifest.

## Validation

Run standard-library-only tests and shell syntax checks. On the target, a successful managed update must end with `check_library.py` reporting zero issues.
