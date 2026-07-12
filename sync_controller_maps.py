#!/usr/bin/env python3
"""Synchronize Mister Input Maps while preserving local controller overrides."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple


DEFAULT_INDEX_URL = "https://api.github.com/repos/misteraddons/Mister-Input-Maps/contents/Main_Inputs?ref=master"
MAP_ARCHIVE_RE = re.compile(r"^MiSTer_Input_Maps-(\d{8})\.zip$")
CHUNK_SIZE = 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_state(path: Optional[Path]) -> Dict[str, str]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files", {})
    if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
        raise ValueError(f"Invalid controller state: {path}")
    return files


def save_state(path: Optional[Path], archive_name: str, files: Dict[str, str]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    payload = {"upstream_archive": archive_name, "files": dict(sorted(files.items()))}
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def fetch_bytes(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Waian-MisterPi/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def newest_archive_entry(entries: List[object]) -> Tuple[str, str]:
    candidates = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        url = entry.get("download_url")
        match = MAP_ARCHIVE_RE.fullmatch(name) if isinstance(name, str) else None
        if match and isinstance(url, str) and url.startswith("https://"):
            candidates.append((match.group(1), name, url))
    if not candidates:
        raise ValueError("Upstream repository contains no downloadable Main_Inputs archive")
    _, name, url = max(candidates, key=lambda item: item[0])
    return name, url


def discover_map_archive(index_url: str, timeout: int) -> Tuple[str, bytes]:
    entries = json.loads(fetch_bytes(index_url, timeout).decode("utf-8"))
    if not isinstance(entries, list):
        raise ValueError("Unexpected response from controller-map index")
    name, url = newest_archive_entry(entries)
    return name, fetch_bytes(url, timeout)


def map_files(archive_bytes: bytes) -> Dict[str, bytes]:
    maps: Dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if member.is_dir() or "__MACOSX" in path.parts or path.suffix.lower() != ".map":
                continue
            name = path.name
            if name in maps:
                raise ValueError(f"Duplicate map in upstream archive: {name}")
            maps[name] = archive.read(member)
    if not maps:
        raise ValueError("Selected upstream archive contains no .map files")
    return maps


def atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", default=Path("/media/fat/config/inputs"), type=Path)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    parser.add_argument("--archive-url", help="Use one explicit Main_Inputs ZIP instead of discovery")
    parser.add_argument("--timeout", default=60, type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        previous = load_state(args.state_file)
        if args.archive_url:
            archive_name = PurePosixPath(urllib.parse.urlsplit(args.archive_url).path).name
            if not MAP_ARCHIVE_RE.fullmatch(archive_name):
                raise ValueError("--archive-url must end with MiSTer_Input_Maps-YYYYMMDD.zip")
            archive_bytes = fetch_bytes(args.archive_url, args.timeout)
        else:
            archive_name, archive_bytes = discover_map_archive(args.index_url, args.timeout)
        upstream = map_files(archive_bytes)
        current_manifest = {name: sha256(data) for name, data in upstream.items()}

        args.dest.mkdir(parents=True, exist_ok=True)
        added = updated = unchanged = overrides = 0
        for name, data in sorted(upstream.items()):
            destination = args.dest / name
            upstream_hash = current_manifest[name]
            if not destination.exists():
                added += 1
                if not args.dry_run:
                    atomic_write(destination, data)
                continue
            if not destination.is_file():
                raise ValueError(f"Controller-map destination is not a file: {destination}")
            installed_hash = sha256_file(destination)
            if installed_hash == upstream_hash:
                unchanged += 1
            elif previous.get(name) == installed_hash:
                updated += 1
                if not args.dry_run:
                    atomic_write(destination, data)
            else:
                overrides += 1
                print(f"Preserving local override: {name}")

        if not args.dry_run:
            save_state(args.state_file, archive_name, current_manifest)
        print(f"Controller source: misteraddons/Mister-Input-Maps {archive_name}")
        print(f"Upstream maps: {len(upstream)}")
        print(f"Added: {added}")
        print(f"Updated: {updated}")
        print(f"Unchanged: {unchanged}")
        print(f"Local overrides preserved: {overrides}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
