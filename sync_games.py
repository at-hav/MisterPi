#!/usr/bin/env python3
"""Find missing catalog targets and optionally download them from an HTTP mirror."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, Optional, Tuple


CHUNK_SIZE = 1024 * 1024
ENV_KEY = "GAME_BASE_URL"
REQUIRED_COLUMNS = ("console_dir", "game_file", "hash")


def read_env_file(path: Optional[Path]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if path is None or not path.exists():
        return values
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
            raise ValueError(f"{path}:{number}: invalid environment key")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def safe_relative_path(console_dir: str, game_file: str) -> PurePosixPath:
    if "\\" in console_dir or "\\" in game_file:
        raise ValueError("backslashes are not valid in catalog paths")
    relative = PurePosixPath(console_dir.strip()) / PurePosixPath(game_file.strip())
    if relative.is_absolute() or not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError("path must be a non-empty relative path without dot segments")
    return relative


def destination_for(games_root: Path, relative: PurePosixPath) -> Path:
    root = games_root.resolve()
    destination = (root / Path(*relative.parts)).resolve()
    if os.path.commonpath((str(root), str(destination))) != str(root):
        raise ValueError("path escapes the games root")
    return destination


def source_url(base_url: str, relative: PurePosixPath) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{ENV_KEY} must be an http:// or https:// URL")
    suffix = "/".join(urllib.parse.quote(part, safe="") for part in relative.parts)
    return base_url.rstrip("/") + "/" + suffix


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha1: str, timeout: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.waian-part-{os.getpid()}")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Waian-MisterPi/1"})
        digest = hashlib.sha1()
        with urllib.request.urlopen(request, timeout=timeout) as response, temporary.open("wb") as output:
            for chunk in iter(lambda: response.read(CHUNK_SIZE), b""):
                digest.update(chunk)
                output.write(chunk)
        actual = digest.hexdigest()
        if actual != expected_sha1:
            raise ValueError(f"SHA-1 mismatch: expected {expected_sha1}, received {actual}")
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def rows(path: Path) -> Iterable[Tuple[int, Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("CSV missing required columns: " + ", ".join(missing))
        for number, row in enumerate(reader, start=2):
            yield number, row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--games-root", default=Path("/media/fat/games"), type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--base-url", help=f"HTTP mirror root; overrides {ENV_KEY}")
    parser.add_argument("--no-download", action="store_true", help="Report missing targets without downloading")
    parser.add_argument("--verify-existing", action="store_true", help="SHA-1 check existing files (slow)")
    parser.add_argument("--timeout", default=60, type=int)
    parser.add_argument("--max-print", default=50, type=int)
    args = parser.parse_args()

    try:
        file_environment = read_env_file(args.env_file)
        base_url = args.base_url or os.environ.get(ENV_KEY) or file_environment.get(ENV_KEY, "")
        seen = set()
        missing = []
        verified = 0

        for number, row in rows(args.csv):
            relative = safe_relative_path(row["console_dir"], row["game_file"])
            if relative in seen:
                raise ValueError(f"CSV line {number}: duplicate target {relative}")
            seen.add(relative)
            expected = row["hash"].strip().lower()
            if not re.fullmatch(r"[0-9a-f]{40}", expected):
                raise ValueError(f"CSV line {number}: invalid SHA-1 for {relative}")
            destination = destination_for(args.games_root, relative)
            if destination.is_file():
                if args.verify_existing and sha1_file(destination) != expected:
                    raise ValueError(f"Existing file has wrong SHA-1: {destination}")
                verified += 1
            elif destination.exists():
                raise ValueError(f"Catalog target is not a regular file: {destination}")
            else:
                missing.append((relative, destination, expected))

        print(f"Catalog targets: {len(seen)}")
        print(f"Present: {verified}")
        print(f"Missing: {len(missing)}")
        for relative, _, _ in missing[: args.max_print]:
            print(f"  - {relative}")
        if len(missing) > args.max_print:
            print(f"  ... and {len(missing) - args.max_print} more")

        if not missing:
            return 0
        if args.no_download:
            return 1
        if not base_url:
            print(f"ERROR: missing games require {ENV_KEY} in the managed .env file", file=sys.stderr)
            return 1

        downloaded = 0
        for index, (relative, destination, expected) in enumerate(missing, start=1):
            print(f"Downloading [{index}/{len(missing)}] {relative}")
            download(source_url(base_url, relative), destination, expected, args.timeout)
            downloaded += 1
        print(f"Downloaded: {downloaded}")
        return 0
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
