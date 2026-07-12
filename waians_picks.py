#!/usr/bin/env python3
"""
Build MiSTer .mgl launchers from game-library CSV (new-format schema).

Expected CSV columns (required):
  console, console_common_name, game_title, category_1, category_2, multiplayer,
  core_name, console_dir, game_file,
  category_1_mgl, category_2_mgl, multiplayer_mgl, top_console_mgl, console_mgl

Behavior:
- Always uses game_file for the <file ... path="..."/> attribute (uses only game_file)
- Writes .mgl files to the non-empty mgl path columns (relative to FAT root /media/fat)
- Creates any missing parent folders
- Verifies: core exists, target exists, and (optionally) verifies mgl written
- Prints per-console/per-category counts and totals
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr


DEFAULT_CSV = "game-library.csv"
DEFAULT_FAT_ROOT = "/media/fat"
DEFAULT_GAMES_ROOT = "/media/fat/games"


REQUIRED_COLS = [
    "console",
    "console_common_name",
    "game_title",
    "category_1",
    "category_2",
    "multiplayer",
    "core_name",
    "console_dir",
    "game_file",
    "category_1_mgl",
    "category_2_mgl",
    "multiplayer_mgl",
    "top_console_mgl",
    "console_mgl",
]


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def truthy(val: str) -> bool:
    if val is None:
        return False
    v = str(val).strip().lower()
    return v in {"1", "true", "t", "yes", "y", "on"}


def clean(s: str) -> str:
    return (s or "").strip()


def detect_file_ext(path_str: str) -> str:
    """Return lowercase file extension (including dot), e.g. '.chd'."""
    p = clean(path_str)
    if not p:
        return ""
    # Defensive: strip URL-ish fragments if any.
    p = p.split('?', 1)[0].split('#', 1)[0]
    return PurePosixPath(p).suffix.lower()



def normalize_key(s: str) -> str:
    """Loose key for mapping: uppercase alnum only."""
    s = clean(s).upper()
    return "".join(ch for ch in s if ch.isalnum())


@dataclass(frozen=True)
class SystemArgs:
    delay: int
    index: int
    type_char: str  # 'f' or 's'


# Best-effort mapping based on MiSTer launcher conventions + mrext docs examples.
# Keys are normalized (alnum uppercase). We try multiple candidates per row.
# Delay/Type/Index values sourced from mrext docs/systems.md
SYSTEM_FILE_ARGS: Dict[str, Dict[str, SystemArgs]] = {
    # Nintendo
    normalize_key("NES"): {".nes": SystemArgs(delay=2, index=1, type_char="f")},
    normalize_key("SNES"): {
        ".sfc": SystemArgs(delay=2, index=0, type_char="f"),
        ".smc": SystemArgs(delay=2, index=0, type_char="f"),
        ".bin": SystemArgs(delay=2, index=0, type_char="f"),
        ".bs":  SystemArgs(delay=2, index=0, type_char="f"),
    },
    normalize_key("N64"): {
        ".n64": SystemArgs(delay=1, index=1, type_char="f"),
        ".z64": SystemArgs(delay=1, index=1, type_char="f"),
        ".v64": SystemArgs(delay=1, index=1, type_char="f"),  # common variant
    },
    normalize_key("GAMEBOY"): {
        ".gb":  SystemArgs(delay=2, index=1, type_char="f"),
        ".gbc": SystemArgs(delay=2, index=1, type_char="f"),  # some packs keep GB-compatible carts here
    },
    normalize_key("GBC"): {".gbc": SystemArgs(delay=2, index=1, type_char="f")},
    normalize_key("GBA"): {".gba": SystemArgs(delay=2, index=1, type_char="f")},

    # Sega
    normalize_key("SMS"): {
        ".sms": SystemArgs(delay=1, index=1, type_char="f"),
        ".gg":  SystemArgs(delay=1, index=2, type_char="f"),  # GG uses SMS core, index=2
    },
    normalize_key("GAMEGEAR"): {".gg": SystemArgs(delay=1, index=2, type_char="f")},
    normalize_key("MEGADRIVE"): {
        ".bin": SystemArgs(delay=1, index=1, type_char="f"),
        ".gen": SystemArgs(delay=1, index=1, type_char="f"),
        ".md":  SystemArgs(delay=1, index=1, type_char="f"),
        ".smd": SystemArgs(delay=1, index=1, type_char="f"),  # common variant
    },
    normalize_key("S32X"): {".32x": SystemArgs(delay=1, index=1, type_char="f")},
    normalize_key("MEGACD"): {
        ".cue": SystemArgs(delay=1, index=0, type_char="s"),
        ".chd": SystemArgs(delay=1, index=0, type_char="s"),
    },
    normalize_key("SATURN"): {
        ".cue": SystemArgs(delay=1, index=0, type_char="s"),
        ".chd": SystemArgs(delay=1, index=0, type_char="s"),
    },

    # Sony
    normalize_key("PSX"): {
        ".cue": SystemArgs(delay=1, index=1, type_char="s"),
        ".chd": SystemArgs(delay=1, index=1, type_char="s"),
        ".exe": SystemArgs(delay=1, index=1, type_char="f"),
    },

    # SNK
    normalize_key("NEOGEO"): {".neo": SystemArgs(delay=1, index=1, type_char="f")},
    normalize_key("NEOGEOCD"): {
        ".cue": SystemArgs(delay=1, index=1, type_char="s"),
        ".chd": SystemArgs(delay=1, index=1, type_char="s"),
    },
}



def detect_system_args(row: dict) -> SystemArgs:
    # Determine which system we're launching (core_name / console_dir / console / common name).
    # Important: the *core_name* can be shared across multiple "systems" (e.g., NeoGeo vs NeoGeoCD).
    # So we prefer an exact (system, extension) match over "first system that matches".
    candidates = [
        row.get("core_name", ""),
        row.get("console_dir", ""),
        row.get("console", ""),
        row.get("console_common_name", ""),
    ]

    target_rel = clean(row.get("game_file", ""))
    ext = detect_file_ext(target_rel)

    first_system_ext_map = None

    for c in candidates:
        k = normalize_key(str(c))
        if k not in SYSTEM_FILE_ARGS:
            continue

        ext_map = SYSTEM_FILE_ARGS[k]
        if first_system_ext_map is None:
            first_system_ext_map = ext_map

        if ext and ext in ext_map:
            return ext_map[ext]

    # If we found a known system but didn't find a matching extension rule,
    # fall back to that system's first declared rule.
    if first_system_ext_map:
        return next(iter(first_system_ext_map.values()))

    # Unknown system: default to "flat file" conventions.
    return SystemArgs(delay=1, index=1, type_char="f")




def gather_installed_cores(fat_root: Path) -> Dict[str, str]:
    """
    Returns mapping: core_base_name -> directory ('_Console' or '_Computer') where it exists.
    We treat 'Core_YYYYMMDD' and 'Core' as the same base name 'Core'.
    """
    cmd = ["find", "_Console", "_Computer", "-maxdepth", "1", "-type", "f", "-name", "*.rbf"]
    try:
        proc = subprocess.run(cmd, cwd=str(fat_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    except FileNotFoundError:
        eprint("ERROR: 'find' not available. Cannot auto-detect installed cores.")
        return {}

    if proc.returncode != 0:
        eprint("WARNING: find returned non-zero exit code. stderr:")
        eprint(proc.stderr.strip())

    cores: Dict[str, str] = {}
    for line in proc.stdout.splitlines():
        p = line.strip()
        if not p:
            continue
        # Example: _Console/MegaDrive_20250707.rbf
        pp = Path(p)
        directory = pp.parent.name  # _Console or _Computer
        stem = pp.stem  # MegaDrive_20250707
        base = stem.split("_", 1)[0]  # MegaDrive
        # Prefer _Console over _Computer if both.
        if base not in cores or (cores[base] != "_Console" and directory == "_Console"):
            cores[base] = directory
    return cores


def build_target_rel(row: dict) -> str:
    """Return target path relative to /media/fat/games/{console_dir}."""
    # game_file is the single source of truth for launching.
    return clean(row.get("game_file", ""))


def _normalize_system_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def make_mgl_xml(
    rbf_dir: str,
    core_name: str,
    console_dir: str,
    sys_args: SystemArgs,
    target_rel: str,
    games_root: Path,
) -> str:
    """
    Build an .mgl XML payload.

    Default behavior (most systems):
      - Use <setname> pointing at /media/fat/games/<console_dir>
      - Use a relative <file ... path="...">

    Special-case behavior (NeoGeo-CD):
      - Do NOT emit <setname>
      - Emit an absolute <file ... path="/media/fat/games/NeoGeo-CD/...">
      This matches the behavior of MiSTer's own "Last Played.mgl" for NeoGeo-CD
      and avoids core-specific setname/relative path resolution issues.
    """
    # NeoGeo-CD needs absolute file paths and no <setname>.
    if _normalize_system_key(console_dir) == "neogeocd":
        if target_rel.startswith("/"):
            target_path = target_rel
        else:
            target_path = str(games_root / console_dir / target_rel)
        return (
            "<mistergamedescription>\n"
            f"  <rbf>{escape(rbf_dir)}/{escape(core_name)}</rbf>\n"
            f"  <file delay=\"{sys_args.delay}\" type=\"{sys_args.type_char}\" index=\"{sys_args.index}\" path={quoteattr(target_path)}/>\n"
            "</mistergamedescription>\n"
        )

    # Default: Use absolute setname pointing to the directory where target_rel lives.
    # This lets us keep 'path' relative but still load reliably for most cores.
    setname = str(games_root / console_dir)
    return (
        "<mistergamedescription>\n"
        f"  <rbf>{escape(rbf_dir)}/{escape(core_name)}</rbf>\n"
        f"  <setname>{escape(setname)}</setname>\n"
        f"  <file delay=\"{sys_args.delay}\" type=\"{sys_args.type_char}\" index=\"{sys_args.index}\" path={quoteattr(target_rel)}/>\n"
        "</mistergamedescription>\n"
    )


def ensure_parent_dir(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)


def safe_write_text(path: Path, text: str, dry_run: bool) -> None:
    ensure_parent_dir(path, dry_run=dry_run)
    if dry_run:
        return
    # Python 3.9 Path.write_text has no 'newline' kwarg; open() does.
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate MiSTer .mgl files from game-library CSV (new format).")
    ap.add_argument("--csv", dest="csv", default=DEFAULT_CSV, help=f"CSV path (default: {DEFAULT_CSV})")
    ap.add_argument("--fat-root", default=DEFAULT_FAT_ROOT, help=f"MiSTer FAT root (default: {DEFAULT_FAT_ROOT})")
    ap.add_argument("--games-root", default=DEFAULT_GAMES_ROOT, help=f"Games root (default: {DEFAULT_GAMES_ROOT})")
    ap.add_argument("--output-root", default=None,
                    help="Write MGL paths below this root (default: --fat-root)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write anything; just report.")
    args = ap.parse_args()

    fat_root = Path(args.fat_root)
    games_root = Path(args.games_root)
    output_root = Path(args.output_root) if args.output_root else fat_root

    csv_arg = getattr(args, "csv")
    csv_path = Path(csv_arg)
    if not csv_path.is_file():
        # Allow relative-to-CWD convenience.
        csv_path = Path.cwd() / csv_arg
    if not csv_path.is_file():
        eprint(f"ERROR: CSV not found: {csv_arg}")
        return 2

    installed_cores = gather_installed_cores(fat_root)

    rows = 0
    written = 0
    skipped_blank_mgl = 0

    issues: List[Tuple[str, str, str]] = []  # (code, game_title, details)

    games_per_console: Dict[str, int] = {}
    games_per_category: Dict[str, int] = {}
    output_owners: Dict[str, Tuple[str, str]] = {}

    # Read CSV
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing_cols = [c for c in REQUIRED_COLS if c not in (reader.fieldnames or [])]
        # Backward compat: allow legacy 'game_file' column if 'game_file' is missing
        if 'game_file' in missing_cols and 'game_file' in (reader.fieldnames or []):
            missing_cols = [c for c in missing_cols if c != 'game_file']
        if missing_cols:
            eprint("ERROR: CSV missing required columns:")
            for c in missing_cols:
                eprint(f"  - {c}")
            return 3

        for row in reader:
            rows += 1
            game_title = clean(row.get("game_title", f"Row {rows}"))
            console_dir = clean(row.get("console_dir", ""))
            console = clean(row.get("console", ""))
            core_name = clean(row.get("core_name", ""))

            games_per_console[console] = games_per_console.get(console, 0) + 1

            c1 = clean(row.get("category_1", ""))
            c2 = clean(row.get("category_2", ""))
            if c1:
                games_per_category[c1] = games_per_category.get(c1, 0) + 1
            if c2:
                games_per_category[c2] = games_per_category.get(c2, 0) + 1

            # Core check
            rbf_dir = "_Console"
            if core_name:
                if core_name in installed_cores:
                    rbf_dir = installed_cores[core_name]
                else:
                    issues.append(("core_missing", game_title, f"{core_name} (expected under {fat_root}/_Console or _Computer)"))
            else:
                issues.append(("row_bad", game_title, "core_name is blank"))

            # Target check
            target_rel = build_target_rel(row)
            if not console_dir:
                issues.append(("row_bad", game_title, "console_dir is blank"))
                continue
            if not target_rel:
                issues.append(("row_bad", game_title, "game_file target is blank"))
                continue
            target_parts = PurePosixPath(target_rel).parts
            if PurePosixPath(target_rel).is_absolute() or ".." in target_parts:
                issues.append(("row_bad", game_title, f"unsafe game_file target: {target_rel}"))
                continue

            target_abs = games_root / console_dir / target_rel
            if not target_abs.exists():
                issues.append(("target_missing", game_title, str(target_abs)))

            # Generate XML
            sys_args = detect_system_args(row)
            xml = make_mgl_xml(rbf_dir, core_name, console_dir, sys_args, target_rel, games_root)

            # Write to each mgl output column if present (non-empty)
            mgl_cols = ["category_1_mgl", "category_2_mgl", "multiplayer_mgl", "top_console_mgl", "console_mgl"]

            # Only write category_2 if category_2 itself is non-empty
            # Only write multiplayer if multiplayer is truthy
            for col in mgl_cols:
                rel_mgl = clean(row.get(col, ""))
                if not rel_mgl:
                    skipped_blank_mgl += 1
                    continue

                if col == "category_2_mgl" and not c2:
                    skipped_blank_mgl += 1
                    continue
                if col == "multiplayer_mgl" and not truthy(row.get("multiplayer", "")):
                    skipped_blank_mgl += 1
                    continue

                mgl_relative = PurePosixPath(rel_mgl)
                if mgl_relative.is_absolute() or ".." in mgl_relative.parts:
                    issues.append(("row_bad", game_title, f"unsafe MGL path: {rel_mgl}"))
                    continue
                collision_key = str(mgl_relative).casefold()
                owner = output_owners.get(collision_key)
                if owner and owner != (game_title, target_rel):
                    issues.append((
                        "mgl_collision",
                        game_title,
                        f"{rel_mgl} conflicts with {owner[0]} ({owner[1]})",
                    ))
                    continue
                output_owners[collision_key] = (game_title, target_rel)
                out_path = output_root / Path(*mgl_relative.parts)
                try:
                    safe_write_text(out_path, xml, dry_run=args.dry_run)
                    written += 1
                except Exception as ex:
                    issues.append(("mgl_write_fail", game_title, f"{out_path}: {ex}"))

    # Report
    print(f"Rows processed: {rows}")
    print(f"MGL files written: {written}{' (dry-run)' if args.dry_run else ''}")
    print(f"MGL paths skipped (blank/disabled): {skipped_blank_mgl}")

    total_games = sum(games_per_console.values())
    print(f"\nTotal games: {total_games}")

    print("\nGames per console:")
    for k, v in sorted(games_per_console.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {k}: {v}")

    print("\nGames per category (category_1 + category_2):")
    for k, v in sorted(games_per_category.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {k}: {v}")

    # Summarize issues
    by_code: Dict[str, int] = {}
    for code, _, _ in issues:
        by_code[code] = by_code.get(code, 0) + 1

    print(f"\nIssues found: {len(issues)}")
    for code, cnt in sorted(by_code.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {code}: {cnt}")

    if issues:
        print("\nFirst issues:")
        for code, title, detail in issues[:50]:
            print(f"- [{code}] {title}: {detail}")

    # Never publish a menu that references a missing core or game.
    critical = any(
        code in {"core_missing", "target_missing", "row_bad", "mgl_collision", "mgl_write_fail"}
        for code, _, _ in issues
    )
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
