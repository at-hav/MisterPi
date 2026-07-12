#!/usr/bin/env python3
"""
mgl_smoketest.py

Launches *exact* .mgl files (MiSTer parses them) by sending:
  printf 'load_core %s\n' "/path/to/file.mgl" > /dev/MiSTer_cmd

PASS/FAIL heuristic:
  PASS if /tmp/CORENAME becomes != "MENU" within --core-timeout seconds
  and does not bounce back to "MENU" during --stable-window seconds.

Also validates that the <file path="..."> payload exists by parsing the .mgl.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import defaultdict

MISTER_CMD = Path("/dev/MiSTer_cmd")
CORENAME = Path("/tmp/CORENAME")

DEFAULT_BASE = Path("/media/fat/_Waian's Picks")
DEFAULT_TOP_CONSOLE = DEFAULT_BASE / "_Top Games by Console"
DEFAULT_ALL_CONSOLE = DEFAULT_BASE / "_All Games by Console"
DEFAULT_TOP_CATEGORY = DEFAULT_BASE / "_Top Games by Category"

BRACKET_CONSOLE_RE = re.compile(r"\[([^\]]+)\]\.mgl$", re.IGNORECASE)

def read_corename() -> str:
    try:
        return CORENAME.read_text(errors="ignore").strip()
    except FileNotFoundError:
        return ""

def mister_load_core(target_path: Path) -> None:
    """
    Equivalent to:
      printf 'load_core %s\n' "/abs/path" > /dev/MiSTer_cmd
    """
    line = f"load_core {str(target_path)}\n"
    # Use plain open/write (FIFO-friendly).
    with open(MISTER_CMD, "w", encoding="utf-8", errors="ignore") as f:
        f.write(line)
        f.flush()

def parse_mgl(mgl_path: Path):
    """Returns: (rbf_text, setname_text_or_None, file_path_text_or_None)"""
    try:
        xml_text = mgl_path.read_text(errors="ignore")
        root = ET.fromstring(xml_text)
    except Exception:
        return (None, None, None)

    rbf = root.findtext("rbf")
    setname = root.findtext("setname")
    file_elem = root.find("file")
    file_path = file_elem.get("path") if file_elem is not None else None
    return (rbf, setname, file_path)

def resolve_payload_path(setname: str | None, file_path: str | None) -> Path | None:
    """
    - If file_path is absolute => use it
    - If relative:
        - if setname is absolute => setname/file_path
        - else => /media/fat/games/<setname>/<file_path>
    """
    if not file_path:
        return None

    p = Path(file_path)
    if p.is_absolute():
        return p

    if not setname:
        # best-effort fallback
        return Path("/media/fat/games") / p

    sp = Path(setname)
    if sp.is_absolute():
        return sp / p

    return Path("/media/fat/games") / sp / p

def infer_console_from_filename(mgl_path: Path) -> str:
    m = BRACKET_CONSOLE_RE.search(mgl_path.name)
    if m:
        return m.group(1).strip()
    return mgl_path.parent.name.lstrip("_").strip() or "Unknown"

def pick_n_per_console(root: Path, n: int) -> list[Path]:
    picked: list[Path] = []
    if not root.exists():
        return picked
    for sub in sorted([p for p in root.iterdir() if p.is_dir()]):
        mgls = sorted([p for p in sub.rglob("*.mgl") if p.is_file()])
        picked.extend(mgls[:n])
    return picked

def pick_1_per_console_per_category(root: Path) -> list[Path]:
    """
    For each category folder:
      - pick 1 .mgl per console (console inferred from [Console] suffix)
    Works whether category is flat or has console subfolders.
    """
    picked: list[Path] = []
    if not root.exists():
        return picked

    for cat_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
        mgls = [p for p in cat_dir.rglob("*.mgl") if p.is_file()]
        by_console: dict[str, list[Path]] = defaultdict(list)

        for mgl in sorted(mgls):
            by_console[infer_console_from_filename(mgl)].append(mgl)

        for _console, files in sorted(by_console.items(), key=lambda kv: kv[0].lower()):
            picked.append(files[0])

    return picked

def wait_for_not_menu(timeout_s: int) -> tuple[bool, str]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cn = read_corename()
        if cn and cn != "MENU":
            return True, cn
        time.sleep(0.1)
    return False, read_corename()

def bounced_back_to_menu(stable_window_s: int) -> bool:
    deadline = time.time() + stable_window_s
    while time.time() < deadline:
        if read_corename() == "MENU":
            return True
        time.sleep(0.1)
    return False

def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke-test MiSTer .mgl files by loading them via /dev/MiSTer_cmd")

    ap.add_argument("--top-console", default=str(DEFAULT_TOP_CONSOLE))
    ap.add_argument("--all-console", default=str(DEFAULT_ALL_CONSOLE))
    ap.add_argument("--top-category", default=str(DEFAULT_TOP_CATEGORY))

    ap.add_argument("--seconds", type=int, default=15, help="Seconds to leave each title running")
    ap.add_argument("--core-timeout", type=int, default=12, help="Seconds to wait for CORENAME != MENU")
    ap.add_argument("--stable-window", type=int, default=3, help="Seconds to ensure it doesn't bounce back to MENU")

    ap.add_argument("--per-console", type=int, default=2, help="How many per console for Top/All console folders")
    ap.add_argument("--no-dedupe", action="store_true", help="Do not dedupe repeated .mgl paths across groups")
    ap.add_argument("--dry-run", action="store_true", help="Print plan only; do not launch anything")

    args = ap.parse_args()

    if not MISTER_CMD.exists():
        print(f"ERROR: {MISTER_CMD} not found. Run this on the MiSTer.")
        return 2

    top_console = Path(args.top_console)
    all_console = Path(args.all_console)
    top_category = Path(args.top_category)

    plan: list[tuple[str, Path]] = []
    plan += [("Top Games by Console", p) for p in pick_n_per_console(top_console, args.per_console)]
    plan += [("All Games by Console", p) for p in pick_n_per_console(all_console, args.per_console)]
    plan += [("Top Games by Category", p) for p in pick_1_per_console_per_category(top_category)]

    if not args.no_dedupe:
        seen = set()
        deduped = []
        for grp, p in plan:
            if p in seen:
                continue
            seen.add(p)
            deduped.append((grp, p))
        plan = deduped

    if not plan:
        print("No .mgl files found in the configured folders.")
        return 1

    print(f"Plan entries: {len(plan)}")
    grp_counts = defaultdict(int)
    for grp, _ in plan:
        grp_counts[grp] += 1
    for grp, ct in grp_counts.items():
        print(f"  {grp}: {ct}")

    if args.dry_run:
        for grp, p in plan:
            print(f"[PLAN] {grp}: {p}")
        return 0

    passes = 0
    fails = 0
    missing_payloads = 0

    for i, (grp, mgl) in enumerate(plan, start=1):
        print("\n" + "=" * 80)
        print(f"[{i}/{len(plan)}] {grp}: {mgl}")

        # Validate payload exists (optional but helpful)
        _rbf, setname, file_path = parse_mgl(mgl)
        payload = resolve_payload_path(setname, file_path)
        if payload is None:
            print("WARN: Could not parse <file path=\"...\"> from this MGL.")
        else:
            if payload.exists():
                print(f"OK: payload exists: {payload}")
            else:
                print(f"FAIL: payload missing: {payload}")
                missing_payloads += 1

        # Launch exact MGL
        mister_load_core(mgl)

        ok, corename = wait_for_not_menu(args.core_timeout)
        if not ok:
            print(f"FAIL: did not leave MENU within {args.core_timeout}s (CORENAME='{corename}')")
            fails += 1
            time.sleep(1)
            continue

        if bounced_back_to_menu(args.stable_window):
            print(f"FAIL: bounced back to MENU within {args.stable_window}s")
            fails += 1
            time.sleep(1)
            continue

        print(f"PASS: core appears loaded (CORENAME='{corename}')")
        passes += 1
        time.sleep(max(0, args.seconds))

    print("\n" + "=" * 80)
    print("DONE")
    print(f"PASS: {passes}")
    print(f"FAIL: {fails}")
    print(f"Missing payload files (from parsing MGL): {missing_payloads}")
    return 0 if fails == 0 else 4

if __name__ == "__main__":
    raise SystemExit(main())
