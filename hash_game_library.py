#!/usr/bin/env python3
"""
hash_game_library.py

MiSTer Pi CSV hasher (SHA-1):

- Requires columns: console_dir, game_file
- Resolves each file as: /media/fat/games/<console_dir>/<game_file>
- Computes SHA-1 and stores it in a 'hash' column (created if missing)
- Does NOT add any other columns.

Usage (run from /media/fat, as you described):
  python3 hash_game_library.py --csv game-library.csv

Recompute all hashes:
  python3 hash_game_library.py --csv game-library.csv --force
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
from typing import List, Tuple


def sha1_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-1 by streaming the file (Pi-friendly)."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def norm(p: str) -> str:
    return os.path.normpath(os.path.expandvars(os.path.expanduser(p.strip())))

def build_full_path(root: str, console_dir: str, game_file: str) -> str:
    # /media/fat/games/<console_dir>/<game_file>
    return norm(os.path.join(root, "games", console_dir.strip(), game_file.strip()))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate MiSTer game files and store SHA-1 hash in CSV.")
    p.add_argument("--csv", required=True, help="CSV to update (must include console_dir + game_file).")
    p.add_argument("--root", default="/media/fat", help="MiSTer root (default: /media/fat).")
    p.add_argument("--hash-col", default="hash", help="Column to store SHA-1 (default: hash).")
    p.add_argument("--force", action="store_true", help="Recompute hash even if hash column already has a value.")
    p.add_argument("--delimiter", default=",", help="CSV delimiter (default: ,).")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    in_path = args.csv
    if not os.path.isfile(in_path):
        print(f"ERROR: CSV not found: {in_path}", file=sys.stderr)
        return 2

    root = norm(args.root)
    games_dir = os.path.join(root, "games")
    if not os.path.isdir(games_dir):
        print(f"ERROR: games directory not found: {games_dir}", file=sys.stderr)
        return 2

    # Always rewrite the authoritative CSV through an adjacent temporary file.
    out_path = f"{in_path}.tmp.{os.getpid()}"

    total = 0
    hashed = 0
    kept = 0
    missing = 0
    errored = 0
    missing_list: List[Tuple[int, str]] = []
    error_list: List[Tuple[int, str, str]] = []

    with open(in_path, "r", newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin, delimiter=args.delimiter)
        if reader.fieldnames is None:
            print("ERROR: CSV appears to have no header row.", file=sys.stderr)
            return 2

        fieldnames = list(reader.fieldnames)

        for required in ("console_dir", "game_file"):
            if required not in fieldnames:
                print(f"ERROR: CSV missing required column: {required}", file=sys.stderr)
                return 2

        if args.hash_col not in fieldnames:
            fieldnames.append(args.hash_col)

        with open(out_path, "w", newline="", encoding="utf-8") as fout:
            writer = csv.DictWriter(fout, fieldnames=fieldnames, delimiter=args.delimiter)
            writer.writeheader()

            for line_no, row in enumerate(reader, start=2):  # header is line 1
                total += 1

                # Keep existing hash unless forcing
                existing_hash = (row.get(args.hash_col) or "").strip()
                if existing_hash and not args.force:
                    kept += 1
                    writer.writerow(row)
                    continue

                console_dir = (row.get("console_dir") or "").strip()
                game_file = (row.get("game_file") or "").strip()

                if not console_dir or not game_file:
                    row[args.hash_col] = ""
                    missing += 1
                    if len(missing_list) < 50:
                        missing_list.append((line_no, f"{console_dir}/{game_file}".strip("/")))
                    writer.writerow(row)
                    continue

                full_path = build_full_path(root, console_dir, game_file)

                if not os.path.isfile(full_path):
                    row[args.hash_col] = ""
                    missing += 1
                    if len(missing_list) < 50:
                        missing_list.append((line_no, f"{console_dir}/{game_file}"))
                    writer.writerow(row)
                    continue

                try:
                    row[args.hash_col] = sha1_file(full_path)
                    hashed += 1
                except Exception as e:
                    row[args.hash_col] = ""
                    errored += 1
                    if len(error_list) < 20:
                        error_list.append((line_no, f"{console_dir}/{game_file}", str(e)))

                writer.writerow(row)

    os.replace(out_path, in_path)
    out_path = in_path

    print("Done.")
    print(f"CSV:        {out_path}")
    print(f"Rows:       {total}")
    print(f"Hashed:     {hashed}")
    print(f"Kept hash:  {kept}")
    print(f"Missing:    {missing}")
    print(f"Errored:    {errored}")

    if missing_list:
        print("\nMissing files (CSV line, console_dir/game_file):")
        for ln, item in missing_list:
            print(f"  L{ln}: {item}")
        if missing > len(missing_list):
            print(f"  ... and {missing - len(missing_list)} more")

    if error_list:
        print("\nErrors (CSV line, console_dir/game_file, error):")
        for ln, item, err in error_list:
            print(f"  L{ln}: {item} -> {err}")
        if errored > len(error_list):
            print(f"  ... and {errored - len(error_list)} more")

    return 1 if (missing > 0 or errored > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
