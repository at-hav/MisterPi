#!/usr/bin/env python3
"""
check_library_paths.py

Validates MiSTer library paths from a CSV.

Checks:
  1) /media/fat/games/<console_dir>/<game_file> exists (file or folder)
  2) (optional) /media/fat/games/<console_dir>/<m3u> exists (when m3u is non-empty)
  3) Core name resolves to an installed .rbf:
       /media/fat/_Console/<core_name>*.rbf  OR /media/fat/_Computer/<core_name>*.rbf
  4) MGL file paths exist under /media/fat using any *_mgl columns (always checked)

Usage:
  python3 check_library_paths.py --csv game-library.csv
  python3 check_library_paths.py --csv game-library.csv --check-m3u

Notes:
  - console_dir and m3u are expected to be console-relative (no leading "/").
  - game_file may include subfolders (e.g., "USA/Game Name (USA)" or "Game Name (USA).md").
"""

from __future__ import annotations

import argparse
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple


EXPECTED_MGL_SKIPPED = 6673


def _norm_rel(s: str) -> str:
    """Normalize a relative path-ish string (strip whitespace, leading slashes)."""
    s = (s or "").strip()
    while s.startswith("/"):
        s = s[1:]
    return s


def find_core_file(core_name: str, fat_root: Path) -> Tuple[bool, str]:
    """
    Check whether core_name appears to be installed.

    MiSTer MGL uses <rbf>_Console/<Name></rbf> (without suffix).
    The actual file on disk is typically:
      _Console/<Name>_YYYYMMDD.rbf
    or sometimes:
      _Console/<Name>.rbf
    """
    core = (core_name or "").strip()
    if not core:
        return (False, "blank core_name")

    console_dir = fat_root / "_Console"
    computer_dir = fat_root / "_Computer"

    hits: List[Path] = []
    for base in (console_dir, computer_dir):
        if base.exists():
            hits.extend(base.glob(f"{core}*.rbf"))

    if not hits:
        return (False, f"no .rbf matching {core}*.rbf in _Console/_Computer")

    # Prefer an exact match (rare) or the shortest match; otherwise just show first.
    hits_sorted = sorted(hits, key=lambda p: (len(p.name), p.name))
    return (True, str(hits_sorted[0]))



def resolve_mgl_target_path(mgl_path: Path, fat_root: Path) -> Tuple[Optional[Path], str]:
    """Return (resolved_path, detail) for the <file path="..."> referenced by an .mgl."""
    try:
        xml = mgl_path.read_text(encoding="utf-8", errors="replace")
        root = ET.fromstring(xml)
    except Exception as e:
        return (None, f"parse_error: {e}")

    # Find optional <setname> and required <file ... path="..."/>
    setname = ""
    sn = root.find("setname")
    if sn is not None and (sn.text or "").strip():
        setname = (sn.text or "").strip()

    fnode = root.find("file")
    if fnode is None:
        return (None, "no <file> element")
    fpath = (fnode.attrib.get("path") or "").strip()
    if not fpath:
        return (None, "empty file path")

    # Resolve: absolute path stays absolute; relative joins setname if present, otherwise fat_root
    if fpath.startswith("/"):
        return (Path(fpath), "absolute")
    if setname:
        return (Path(setname) / fpath, f"setname={setname}")
    return (fat_root / fpath, "relative_to_fat_root")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", dest="csv_path", default="game-library.csv",
                    help="Path to CSV (default: game-library.csv)")
    ap.add_argument("--games-root", dest="games_root", default="/media/fat/games",
                    help="Games root (default: /media/fat/games)")
    ap.add_argument("--fat-root", dest="fat_root", default="/media/fat",
                    help="MiSTer FAT root (default: /media/fat)")
    ap.add_argument("--check-m3u", action="store_true",
                    help="Also verify m3u paths exist (off by default)")
    ap.add_argument("--max-print", type=int, default=200,
                    help="Max number of missing entries to print per category (default: 200)")
    args = ap.parse_args()

    skipped_mgl = 0
    checked_mgl = 0
    scanned_multiplayer = 0

    csv_path = Path(args.csv_path)
    games_root = Path(args.games_root)
    fat_root = Path(args.fat_root)

    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    rows = 0
    issues: Dict[str, List[str]] = {
        "target_missing": [],
        "m3u_missing": [],
        "core_missing": [],
        "mgl_missing": [],
        "mgl_ref_missing": [],
        "row_bad": [],
    }

    # Read CSV
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        mgl_fields = [c for c in fieldnames if c.lower().endswith("_mgl")]

        for row in reader:
            rows += 1
            game_title = (row.get("game_title") or "").strip() or f"(row {rows})"
            console_dir = _norm_rel(row.get("console_dir") or "")
            # Primary launch target (relative to /media/fat/games/<console_dir>)
            game_file = _norm_rel(row.get("game_file") or "")
            m3u = _norm_rel(row.get("m3u") or "")
            core_name = (row.get("core_name") or "").strip()

            if not console_dir or not game_file:
                issues["row_bad"].append(f"{game_title}: missing console_dir or game_file")
                continue

            # 1) Target exists
            target_path = games_root / console_dir / game_file
            if not target_path.exists():
                issues["target_missing"].append(f"{game_title}: {target_path}")

            # 2) m3u exists (when provided)
            if args.check_m3u and m3u:
                m3u_path = games_root / console_dir / m3u
                if not m3u_path.exists():
                    issues["m3u_missing"].append(f"{game_title}: {m3u_path}")

            # 3) core exists
            ok_core, core_detail = find_core_file(core_name, fat_root)
            if not ok_core:
                issues["core_missing"].append(f"{game_title}: core_name={core_name!r} ({core_detail})")

            # 4) MGL paths exist (always checked when *_mgl columns exist)
            if mgl_fields:
                for mf in mgl_fields:
                    mgl_rel = _norm_rel(row.get(mf) or "")
                    if not mgl_rel:
                        skipped_mgl += 1
                        continue
                    mgl_path = fat_root / mgl_rel
                    checked_mgl += 1
                    if not mgl_path.exists():
                        issues["mgl_missing"].append(f"{game_title}: {mf} -> {mgl_path}")
                    else:
                        # Validate that the .mgl points at a real file/folder
                        ref_path, ref_detail = resolve_mgl_target_path(mgl_path, fat_root)
                        if not ref_path or not ref_path.exists():
                            issues["mgl_ref_missing"].append(
                                f"{game_title}: {mf} -> {mgl_path} references missing: {ref_path} ({ref_detail})"
                            )


    # 5) Scan _Multiplayer folder (top-level .mgl only) and validate referenced <file path="..."> targets
    multiplayer_dir = fat_root / "_Waian's Picks" / "_Top Games by Category" / "_Multiplayer"
    if multiplayer_dir.exists() and multiplayer_dir.is_dir():
        for mgl_path in sorted(multiplayer_dir.glob("*.mgl")):
            scanned_multiplayer += 1
            ref_path, ref_detail = resolve_mgl_target_path(mgl_path, fat_root)
            if not ref_path or not ref_path.exists():
                issues["mgl_ref_missing"].append(
                    f"_Multiplayer: {mgl_path} references missing: {ref_path} ({ref_detail})"
                )

    def print_bucket(name: str) -> None:
        items = issues[name]
        if not items:
            return
        print(f"\n{name}: {len(items)}")
        for line in items[: args.max_print]:
            print(f"  - {line}")
        if len(items) > args.max_print:
            print(f"  ... {len(items) - args.max_print} more")

    print(f"Rows checked: {rows}")
    print(f"Games root: {games_root}")
    print(f"FAT root: {fat_root}")
    print("check_mgl: True")
    print(f"check_m3u: {args.check_m3u}")

    print(f"MGL paths checked: {checked_mgl}")
    skipped_label = str(skipped_mgl) if skipped_mgl <= EXPECTED_MGL_SKIPPED else "1+"
    print(f"MGL paths skipped (blank/disabled): {skipped_label}")
    if scanned_multiplayer:
        print(f"_Multiplayer .mgl scanned: {scanned_multiplayer}")

    total_issues = sum(len(v) for v in issues.values())
    print(f"\nIssues found: {total_issues}")
    for k in ("row_bad", "core_missing", "target_missing", "m3u_missing", "mgl_missing", "mgl_ref_missing"):
        print(f"  {k}: {len(issues[k])}")

    # Detailed output
    for bucket in ("row_bad", "core_missing", "target_missing", "m3u_missing", "mgl_missing", "mgl_ref_missing"):
        print_bucket(bucket)

    # Exit status: nonzero if any issues
    return 1 if total_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
