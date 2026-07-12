# MiSTerPi Custom Game Library Handoff

## Purpose

This document describes the custom game-library work added around the MiSTerPi installation. It focuses on the parts that are **not standard MiSTer/MiSTerPi behavior**:

- the game-library CSV
- the custom Python scripts
- the physical game-file paths
- generated `.mgl` shortcut files
- the **Waian's Picks** menu hierarchy
- categories and multiplayer groupings
- console-name and core-name mapping
- library validation
- special handling for unusual cores and media formats

The normal MiSTer update process, standard cores, standard menu behavior, and ordinary ROM placement are outside the scope of this handoff except where the custom system depends on them.

---

## 1. High-Level Design

The customization has three distinct layers:

1. **Physical game library**  
   The actual ROM, disk, CD, and playlist files stored under:

   ```text
   /media/fat/games/
   ```

2. **Library metadata**  
   A manually maintained CSV named:

   ```text
   game-library.csv
   ```

   The CSV identifies each game, the file that launches it, its MiSTer core, its display names, and any curated categories.

3. **Generated menu shortcuts**  
   Python scripts read the CSV and generate `.mgl` launcher files under the custom **Waian's Picks** menu tree.

The `.mgl` files are menu shortcuts. They are **not copies of the games** and are not the authoritative source of game paths or metadata.

The intended data flow is:

```text
/media/fat/games/
        │
        │ actual ROMs, CHDs, ISOs, cue/bin sets, M3U files, etc.
        ▼
game-library.csv
        │
        │ read and validated by custom Python scripts
        ▼
generated .mgl shortcuts
        │
        ▼
_Waian's Picks menu folders
```

---

## 2. Important Paths

### 2.1 MiSTer storage root

```text
/media/fat/
```

This is the root used throughout the scripts and generated launcher files.

### 2.2 Physical games root

```text
/media/fat/games/
```

All `game_file` and `m3u` values in the CSV are relative to this directory unless a script explicitly converts them to absolute paths while writing an `.mgl`.

Examples:

```text
Genesis/Sonic the Hedgehog (USA, Europe).md
PSX/Final Fantasy VII/Final Fantasy VII.m3u
NeoGeo-CD/Metal Slug/Metal Slug.cue
```

These resolve to:

```text
/media/fat/games/Genesis/Sonic the Hedgehog (USA, Europe).md
/media/fat/games/PSX/Final Fantasy VII/Final Fantasy VII.m3u
/media/fat/games/NeoGeo-CD/Metal Slug/Metal Slug.cue
```

### 2.3 Custom menu root

The generated menu hierarchy is rooted at:

```text
/media/fat/_Waian's Picks/
```

The main generated subdirectories are:

```text
/media/fat/_Waian's Picks/
├── _Top Games by Console/
├── _All Games by Console/
└── _Top Games by Category/
```

Depending on the current script version, multiplayer groupings may be represented within the category hierarchy or in an additional generated grouping. The CSV remains authoritative for whether a game belongs to a curated grouping.

### 2.4 CSV and script location

The scripts are intended to be run with the CSV specified explicitly:

```bash
python waians_picks_mgl.py --csv game-library.csv
python check_library.py --csv game-library.csv
```

The project deliberately uses the stable filename:

```text
game-library.csv
```

Do not introduce revision-numbered working names such as:

```text
game-library-v2.csv
game-library-final.csv
game-library-rev3.csv
```

Version history should be handled by backups or source control rather than by changing the active filename.

The exact on-device directory containing the scripts and CSV should be confirmed on the system before moving anything. Their internal path assumptions are based primarily on `/media/fat` and `/media/fat/games`, not on the shell's current working directory except for locating the CSV passed with `--csv`.

---

## 3. Custom Files

The custom implementation has used the following files.

### 3.1 `game-library.csv`

The authoritative metadata catalog.

It records:

- MiSTer console/core information
- the actual game file used for launch
- optional M3U playlist information
- game title and display naming
- curated categories
- multiplayer metadata
- generated `.mgl` destinations or names

### 3.2 `waians_picks_mgl.py`

The current `.mgl` generation script.

Earlier work may refer to this as:

```text
waians_picks.py
```

Treat `waians_picks_mgl.py` as the current descriptive name unless the deployed filesystem shows otherwise.

Its purpose is to:

- read `game-library.csv`
- validate required fields sufficiently to generate launchers
- create the **Waian's Picks** directory hierarchy
- generate one or more `.mgl` shortcut files per applicable CSV row
- place each shortcut in the correct console/category menu
- use `game_file` as the launch target
- apply console/core-specific `.mgl` formatting rules
- avoid using `m3u` as an alternate launch-selection mechanism unless that behavior is explicitly restored later

### 3.3 `check_library.py`

The validation script.

Its purpose is to detect broken catalog entries before `.mgl` generation or deployment.

The current intended validation behavior includes:

- confirm the CSV has all required columns
- validate the path in `game_file`
- resolve `game_file` relative to `/media/fat/games`
- report missing game files
- retain M3U path checking where an `m3u` value is present
- detect malformed or incomplete rows
- identify path or naming inconsistencies that would produce broken shortcuts

The important recent change is:

> `game_item` was renamed to `game_file`.

The checker must validate the complete `game_file` path, not merely the directory that contains the game.

### 3.4 Generated `.mgl` files

These are MiSTer launcher/shortcut files used to launch games from the generated menu.

They are disposable outputs. They should be regenerated from the CSV rather than edited manually.

---

## 4. CSV Schema

The schema evolved during development. The active CSV header on the deployed system is the final authority, but the current design uses the following concepts and column names.

## 4.1 Core identity columns

### `console`

The filesystem-oriented console identifier.

Historically this mirrored the first directory below:

```text
/media/fat/games/
```

Example values:

```text
Genesis
MegaDrive
PSX
NeoGeo-CD
SNES
NES
```

Where both `console` and newer naming fields exist, do not assume this value is the user-facing menu name.

### `console_common_name`

The human-readable console name used in menus and generated filenames.

Examples of mappings discussed during development include:

| Internal/folder name | Common display name |
|---|---|
| `MegaDrive` | `Genesis` |
| `MegaCD` | `Sega CD` |
| `PSX` | `PlayStation` |
| `GameGear` | `Game Gear` |

This separation avoids forcing physical folder names, MiSTer core names, and menu display names to be identical.

### `core_name`

The MiSTer core identifier used by the `.mgl`.

This must match the installed core naming expected by MiSTer. It is distinct from both the game-folder name and the human-readable console name.

Do not casually rename this value for presentation purposes. A friendly menu label belongs in `console_common_name`; the core-loading identifier belongs in `core_name`.

---

## 4.2 Game identity columns

### `game_title`

The curated display title for the game.

This is used when naming or labeling generated shortcuts. It should not include a path.

Title matching work treats:

```text
Pokémon
Pokemon
```

as equivalent when comparing titles.

### `game_folder`

The game's containing folder, relative to `/media/fat/games`, where applicable.

This was split out from the older all-in-one `rel_path` design.

Example:

```text
PSX/Final Fantasy VII
```

This field is useful as metadata, but it is **not** the final launch target.

### `game_file`

The complete launch-file path relative to:

```text
/media/fat/games/
```

Examples:

```text
Genesis/Sonic the Hedgehog (USA, Europe).md
PSX/Final Fantasy VII/Final Fantasy VII.m3u
NeoGeo-CD/Metal Slug/Metal Slug.cue
```

This field is used for both:

1. checking whether the launch target exists; and
2. populating the `<file>` element in generated `.mgl` files.

This replaces the previous `game_item` column.

Do not restore checks against `game_item`, and do not validate only `game_folder`.

### `m3u`

An optional path to an M3U playlist, relative to:

```text
/media/fat/games/
```

The M3U file may remain in the CSV and should remain on disk.

Current intended behavior:

- `check_library.py` may verify an M3U path when the field is populated.
- `waians_picks_mgl.py` should **not** use the `m3u` column to choose or replace the launch target.
- The `.mgl` generator should use `game_file`.
- For a multidisc game that should launch through an M3U, put that M3U path directly in `game_file`.

This avoids having two competing fields that can determine what the menu launches.

---

## 4.3 Curation columns

### `categories`

The game's curated category assignment or assignments.

Earlier versions used one general category field; later versions also supported multiple category-specific outputs. The deployed header determines whether categories are stored as one delimited field or as separate category columns.

A game should appear in category menus only when a category is actually populated.

Console/category export files should include **categorized games only** where that output is intended to represent curated picks.

Do not treat a blank category as a generic or uncategorized category unless the script explicitly defines such behavior.

### `multiplayer`

Records multiplayer classification used by the curated menus.

Its accepted values and delimiter convention should be preserved from the current CSV rather than normalized without reviewing the existing data.

A populated multiplayer value can qualify a game for curated/top-level output, depending on the script's current rules.

### `status`

Tracks the catalog or review state of a row.

The existing value vocabulary should be preserved. This field can be used to exclude incomplete or rejected records if the generator implements such filtering.

Do not assume every row should generate shortcuts without checking how `status` is used in the current script.

---

## 4.4 Generated shortcut columns

The CSV has used several `.mgl`-related columns during development.

Known column concepts include:

### `mgl`

A general `.mgl` filename or output reference.

### `console_mgl`

The `.mgl` generated for the all-games console menu.

This can exist for all games that are eligible for generation.

### `top_console_mgl`

The `.mgl` generated for:

```text
_Waian's Picks/_Top Games by Console/
```

Historically this was generated only for games that had a category or multiplayer classification.

### `category_1_mgl`

The `.mgl` generated for the first category assignment.

It should be blank when the corresponding category is blank.

### `category_2_mgl`

The `.mgl` generated for the second category assignment.

It should be blank when the corresponding category is blank.

The active CSV may contain additional or renamed output columns. These fields should be treated as generated metadata, not as substitutes for `game_file`.

---

## 4.5 Legacy columns

### `rel_path`

An older schema stored a path relative to `/media/fat/games` in a single `rel_path` column.

The newer design splits this into:

```text
game_folder
game_file
```

Do not add new dependencies on `rel_path` unless processing an older CSV for migration.

### `game_item`

The previous name for the launch-file field.

It has been replaced by:

```text
game_file
```

Any error such as:

```text
ERROR: CSV missing required columns:
  - game_item
```

means the script is stale and still expects the old schema.

---

## 4.6 Representative schema

A representative current-style header is:

```csv
console,console_common_name,core_name,game_title,categories,multiplayer,status,game_folder,game_file,m3u,mgl,console_mgl,top_console_mgl,category_1_mgl,category_2_mgl
```

The actual deployed header must be checked before changing code because the category fields may be represented differently in the current file.

A representative row might look conceptually like:

```csv
PSX,PlayStation,PSX,Final Fantasy VII,RPG,,approved,PSX/Final Fantasy VII,PSX/Final Fantasy VII/Final Fantasy VII.m3u,PSX/Final Fantasy VII/Final Fantasy VII.m3u,...
```

The generated-column values are omitted above because their exact naming conventions are script-controlled.

---

## 5. `.mgl` Shortcut Files

## 5.1 Role

An `.mgl` file lets a game appear as a directly launchable item in a MiSTer menu.

The generated file identifies:

- the core to load
- the game file to pass to that core
- optionally a set name, depending on the console/core

The shortcut is a pointer to a file under `/media/fat/games`; it does not contain the game itself.

## 5.2 General behavior

For most consoles, generated `.mgl` files use:

- a core reference based on `core_name`
- a `<setname>` element
- a `<file>` value derived from `game_file`
- the normal relative-path style expected by the existing generator

The exact XML must remain compatible with the known-good script output.

## 5.3 NeoGeo-CD special case

NeoGeo-CD requires custom formatting.

The agreed behavior is:

- do **not** include `<setname>`
- write an absolute game path
- use `/media/fat/games/NeoGeo-CD/...` in the `<file>` element

Conceptually:

```xml
<file path="/media/fat/games/NeoGeo-CD/...">...</file>
```

Other consoles should retain the normal behavior with `<setname>` and relative file-path handling unless another explicit core exception exists in the script.

This exception must not be removed during a general refactor.

## 5.4 Source of the launch path

The launch path must come from:

```text
game_file
```

The generator must not:

- reconstruct the path from `game_folder`
- depend on the removed `game_item` field
- silently swap in `m3u`
- infer a different ROM based on directory contents

The CSV should explicitly state the exact file that the menu launches.

## 5.5 Generated-file ownership

Treat generated `.mgl` files as build artifacts:

- do not hand-edit them
- do not put unique metadata only in an `.mgl`
- make CSV/script changes and regenerate
- stale `.mgl` files may need to be removed when rows or categories are deleted

The generator should ideally make its output deterministic so rerunning it produces the same directory tree from the same CSV.

---

## 6. Waian's Picks

**Waian's Picks** is a custom curated menu layered on top of the normal MiSTer game folders.

It is not a standard MiSTerPi feature.

## 6.1 `_All Games by Console`

Path:

```text
/media/fat/_Waian's Picks/_All Games by Console/
```

Purpose:

- expose all eligible cataloged games
- organize them under friendly console names
- launch the original files through generated `.mgl` shortcuts
- provide a curated interface without moving or duplicating ROMs

Typical source column:

```text
console_mgl
```

## 6.2 `_Top Games by Console`

Path:

```text
/media/fat/_Waian's Picks/_Top Games by Console/
```

Purpose:

- contain the selected or categorized subset for each console
- exclude ordinary uncategorized games where the script applies the established rule
- provide a smaller, curated list than `_All Games by Console`

Typical source column:

```text
top_console_mgl
```

Historically, a game qualified here when it had a category or multiplayer classification.

## 6.3 `_Top Games by Category`

Path:

```text
/media/fat/_Waian's Picks/_Top Games by Category/
```

Purpose:

- browse selected games across consoles by category
- allow one game to appear in more than one category
- generate separate `.mgl` files or output references for each category placement

Typical generated columns:

```text
category_1_mgl
category_2_mgl
```

A category shortcut should only be generated when its corresponding category is populated.

## 6.4 No ROM duplication

The same game may appear in several menu locations:

```text
_All Games by Console
_Top Games by Console
_Top Games by Category/<Category A>
_Top Games by Category/<Category B>
```

These are multiple `.mgl` references to one physical game file. The actual ROM/media should remain in one place under `/media/fat/games`.

---

## 7. Categories

Categories are manually curated metadata rather than data inferred from filenames or external databases.

Important rules:

- preserve the spelling already used in the CSV
- avoid creating near-duplicate categories through capitalization or punctuation changes
- do not generate a category shortcut for a blank field
- a game may belong to multiple categories
- category membership does not change the physical game path
- category changes require regenerating `.mgl` outputs
- category-oriented exports should contain only games with categories populated

When matching or normalizing titles, treat `Pokémon` and `Pokemon` as equivalent, but do not rewrite game filenames merely to normalize the title.

The exact category vocabulary should be read from the current CSV before bulk changes. The CSV, not this handoff, is the authoritative category list.

---

## 8. Multiplayer Metadata

The `multiplayer` field is part of curation rather than file discovery.

It may be used to:

- identify games suitable for multiplayer menus
- qualify games for the top-games subset
- annotate or group games independently of genre/category

Do not infer multiplayer support solely from a title or platform. Preserve the manually reviewed value in the CSV.

If a future script separates multiplayer into its own folder tree, it should use the CSV field and generate additional `.mgl` shortcuts rather than moving game files.

---

## 9. Script Workflows

## 9.1 Validate first

Run:

```bash
python check_library.py --csv game-library.csv
```

The checker should report at least:

- missing required columns
- missing `game_file` targets
- missing populated `m3u` targets
- malformed rows
- duplicate or conflicting output paths, if implemented
- invalid path assumptions

A clean validation run should be required before regenerating the production menu.

## 9.2 Generate shortcuts

Run:

```bash
python waians_picks_mgl.py --csv game-library.csv
```

The generator should:

1. load the CSV
2. create required output directories
3. derive menu placement from console/category metadata
4. use `core_name` for the core
5. use `game_file` for the launch file
6. apply special core rules such as NeoGeo-CD
7. write the `.mgl` files
8. report skipped or invalid rows

## 9.3 Test an exact `.mgl`

For automated or manual test harnesses, launch the generated `.mgl` itself rather than bypassing it and loading the ROM directly.

The known command pattern is:

```bash
printf 'load_core %s\n' "/path/to/file.mgl" > /dev/MiSTer_cmd
```

This validates the artifact the user will actually select from the menu.

A prior test approach used `/tmp/CORENAME` as part of a core-load success heuristic. Treat that as a heuristic, not a complete gameplay or media validation.

---

## 10. File and Path Rules

### 10.1 Paths in CSV

Unless otherwise documented:

- `game_file` is relative to `/media/fat/games`
- `m3u` is relative to `/media/fat/games`
- generated `.mgl` output paths are under `/media/fat/_Waian's Picks`
- `game_folder` is metadata and not the launch target

### 10.2 Preserve exact filename case

MiSTer runs on a case-sensitive filesystem in normal Linux operation.

These may be different paths:

```text
PSX/Game.cue
PSX/game.cue
```

The CSV must match the actual path exactly.

### 10.3 Spaces and punctuation

Paths may contain:

- spaces
- apostrophes
- parentheses
- brackets
- accented characters

Scripts must use Python path handling or correctly quoted shell usage. Do not split paths on spaces.

The directory name:

```text
_Waian's Picks
```

contains an apostrophe and must be quoted in shell commands.

Example:

```bash
ls "/media/fat/_Waian's Picks"
```

### 10.4 Do not flatten multidisc folders

Multidisc and CD-based games may depend on:

- `.m3u`
- `.cue`
- `.bin`
- `.chd`
- multiple-disc subdirectories

Do not flatten or rename these structures without updating the CSV and verifying core behavior.

### 10.5 Game path is authoritative

The physical file referenced by `game_file` is the only launch target that should be assumed.

Do not scan the containing directory and select the first ROM-like file.

---

## 11. What Is Custom vs. Standard

## 11.1 Custom

The following are custom and must be backed up or recreated separately from standard MiSTer updates:

```text
game-library.csv
waians_picks_mgl.py
check_library.py
/media/fat/_Waian's Picks/
any test harness used for generated .mgl files
any console/common-name mapping embedded in the scripts
any special-core formatting rules
```

Also custom:

- category definitions
- manual multiplayer assignments
- status values
- hand-curated game titles
- generated output naming conventions
- NeoGeo-CD `.mgl` handling
- the `game_file`-based validation/generation model

## 11.2 Standard or externally managed

Generally standard MiSTer/MiSTerPi components include:

- `/media/fat/games`
- installed cores
- MiSTer menu parsing
- `/dev/MiSTer_cmd`
- the normal update mechanism
- ordinary ROM/core compatibility behavior

The contents under `/media/fat/games` are user data, even though the directory itself is a standard location.

---

## 12. Update and Maintenance Risks

## 12.1 Standard updater interaction

A normal MiSTer update should not be treated as a backup mechanism for:

- the CSV
- custom scripts
- the `_Waian's Picks` tree
- manual metadata

Confirm updater exclusion behavior before assuming custom files are safe.

## 12.2 Stale generated files

If a game is:

- removed from the CSV
- moved to another category
- renamed
- assigned a different console/core
- pointed at a new `game_file`

an old `.mgl` may remain unless the generator cleans its managed output tree.

Before generation, either:

- use the script's built-in cleanup behavior; or
- remove only the known generated directories and regenerate them.

Do not delete the physical `/media/fat/games` tree during cleanup.

## 12.3 Schema drift

The most common failure mode is a mismatch between the CSV header and script expectations.

Known migration:

```text
game_item -> game_file
```

When changing a column:

1. update both scripts
2. update documentation
3. migrate the CSV header/data
4. run the checker
5. regenerate a small test subset
6. verify the resulting `.mgl` on MiSTer

## 12.4 Core-name drift

A MiSTer core update or rename can invalidate `core_name` or generated `.mgl` references.

Keep:

- friendly console names
- filesystem console folders
- MiSTer core identifiers

as separate concepts.

## 12.5 Generated-column drift

Columns such as `console_mgl`, `top_console_mgl`, and `category_1_mgl` may contain derived data.

Do not manually correct large numbers of these values without checking whether the generator can recreate them. Derived values should ideally be overwritten consistently by the script.

---

## 13. Recommended Backup Set

Back up at minimum:

```text
game-library.csv
waians_picks_mgl.py
check_library.py
```

Also preserve:

```text
/media/fat/_Waian's Picks/
```

The generated menu can theoretically be rebuilt, but retaining it is useful for comparison and emergency restoration.

Separately back up the physical game library:

```text
/media/fat/games/
```

The metadata backup and physical game backup serve different purposes. Neither replaces the other.

A complete restore requires:

1. the physical game/media files
2. the CSV
3. the custom scripts
4. compatible MiSTer cores
5. regeneration of the `.mgl` hierarchy

---

## 14. Safe Change Procedure

When adding or changing a game:

1. Confirm the actual file exists under `/media/fat/games`.
2. Add or update the CSV row.
3. Set `game_file` to the exact launch target.
4. Leave `m3u` as optional metadata/checking unless the M3U itself is the `game_file`.
5. Set `console_common_name` for display.
6. Set `core_name` to the installed MiSTer core identifier.
7. Assign categories and multiplayer metadata deliberately.
8. Run:

   ```bash
   python check_library.py --csv game-library.csv
   ```

9. Run:

   ```bash
   python waians_picks_mgl.py --csv game-library.csv
   ```

10. Test the generated `.mgl`, not merely the underlying ROM.
11. Confirm the game appears in the intended Waian's Picks folders.
12. Confirm no stale shortcut remains in a former category.

---

## 15. Troubleshooting

### Error: CSV missing `game_item`

Cause:

- an old script version is being used

Correction:

- update the script to require and read `game_file`
- use `game_file` for existence checks
- use `game_file` for the generated `<file>` tag

### Game folder exists but validation fails

Check the complete `game_file` value.

The checker now validates the actual launch file, not just its parent directory.

### `.mgl` appears but does not launch

Check:

- `core_name`
- exact `game_file` case and spelling
- XML escaping
- relative versus absolute path behavior
- whether the core expects a playlist, cue, CHD, or ROM
- whether the game is a special case such as NeoGeo-CD

### Multidisc game launches the wrong item

The generator uses `game_file`.

Put the intended `.m3u` directly in `game_file` when the playlist is the proper launch target.

Do not rely on the separate `m3u` column to override `game_file`.

### NeoGeo-CD launcher fails

Confirm that the generated `.mgl`:

- has no `<setname>`
- uses an absolute `/media/fat/games/NeoGeo-CD/...` path
- points to the intended file

### Duplicate menu entries

Check for:

- duplicate CSV rows
- repeated category values
- stale `.mgl` files from a previous generation
- output filename collisions
- multiple titles normalizing to the same generated filename

---

## 16. Maintainer Notes

The central design principle is:

> The CSV explicitly states what each menu item launches.

Do not replace this with automatic ROM discovery unless redesigning and retesting the entire workflow.

The most important current conventions are:

- active CSV filename is `game-library.csv`
- use `--csv game-library.csv`
- physical games live under `/media/fat/games`
- use `game_file`, not `game_item`
- `game_file` is the `.mgl` launch target
- `m3u` may be retained and checked but does not override `game_file`
- generated shortcuts live under `_Waian's Picks`
- category outputs contain only games with populated categories
- NeoGeo-CD uses its special absolute-path/no-`setname` format
- generated `.mgl` files should be tested directly through `/dev/MiSTer_cmd`
- generated shortcuts can be rebuilt; the CSV and physical game files are authoritative

Before performing a broad refactor, capture the current CSV header and compare the deployed versions of both scripts. Some schema details evolved during development, and the files on the MiSTerPi should be treated as the final source of truth where they differ from historical notes.
