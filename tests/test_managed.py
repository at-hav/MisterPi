from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sync_controller_maps
import sync_games
import check_library
import hash_game_library


class ManagedLibraryTests(unittest.TestCase):
    def test_catalog_paths_are_safe_and_unique(self) -> None:
        seen = set()
        mgl_paths = set()
        with (ROOT / "game-library.csv").open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                self.assertIn("download_url", row)
                relative = sync_games.safe_relative_path(row["console_dir"], row["game_file"])
                self.assertNotIn(relative, seen)
                seen.add(relative)
                self.assertRegex(row["hash"], r"^[0-9a-f]{40}$")
                for column, value in row.items():
                    if column.endswith("_mgl") and value:
                        folded = value.casefold()
                        self.assertNotIn(folded, mgl_paths)
                        mgl_paths.add(folded)
        self.assertEqual(2563, len(seen))
        self.assertEqual(6142, len(mgl_paths))

    def test_download_url_must_be_explicit_http(self) -> None:
        relative = sync_games.safe_relative_path("NES", "Game.nes")
        self.assertEqual(
            "https://example.test/Game.nes",
            sync_games.source_url("https://example.test/Game.nes", relative),
        )
        with self.assertRaises(ValueError):
            sync_games.source_url("", relative)

    def test_hasher_updates_authoritative_csv(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            game = root / "games" / "NES" / "Game.nes"
            game.parent.mkdir(parents=True)
            game.write_bytes(b"game")
            catalog = root / "game-library.csv"
            catalog.write_text("console_dir,game_file,hash,download_url\nNES,Game.nes,,https://example.test/Game.nes\n")
            with mock.patch.object(
                sys,
                "argv",
                ["hash_game_library.py", "--csv", str(catalog), "--root", str(root)],
            ):
                self.assertEqual(0, hash_game_library.main())
            with catalog.open(encoding="utf-8", newline="") as source:
                row = next(csv.DictReader(source))
            self.assertEqual(hashlib.sha1(b"game").hexdigest(), row["hash"])
            self.assertFalse(list(root.glob("game-library.csv.tmp.*")))

    def test_download_is_atomic_and_hash_checked(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            source = root / "source.bin"
            source.write_bytes(b"known game payload")
            destination = root / "games" / "test.bin"
            expected = hashlib.sha1(source.read_bytes()).hexdigest()
            sync_games.download(source.as_uri(), destination, expected, 5)
            self.assertEqual(source.read_bytes(), destination.read_bytes())
            with self.assertRaises(ValueError):
                sync_games.download(source.as_uri(), destination, "0" * 40, 5)
            self.assertFalse(any(destination.parent.glob("*.waian-part-*")))

    def test_checker_rejects_malformed_xml(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "bad.mgl"
            path.write_text('<mistergamedescription><file path="A & B"/></mistergamedescription>')
            target, detail = check_library.resolve_mgl_target_path(path, Path(directory))
            self.assertIsNone(target)
            self.assertIn("parse_error", detail)

    def test_controller_archive_selection_and_local_override_state(self) -> None:
        entries = [
            {"name": "MiSTer_Input_Maps-20211004.zip", "download_url": "https://example.test/old.zip"},
            {"name": "MiSTer_Input_Maps-20990101.zip", "download_url": "https://example.test/new.zip"},
        ]
        self.assertEqual(
            ("MiSTer_Input_Maps-20990101.zip", "https://example.test/new.zip"),
            sync_controller_maps.newest_archive_entry(entries),
        )
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as archive:
            archive.writestr("MiSTer_Input_Maps-20990101/input_test_v3.map", b"upstream")
        self.assertEqual({"input_test_v3.map": b"upstream"}, sync_controller_maps.map_files(inner.getvalue()))

    def test_generator_outputs_well_formed_complete_menu(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            fat = Path(directory) / "fat"
            games = fat / "games"
            console_cores = fat / "_Console"
            console_cores.mkdir(parents=True)
            with (ROOT / "game-library.csv").open(encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))
            for core in {row["core_name"] for row in rows}:
                (console_cores / f"{core}_20990101.rbf").touch()
            for row in rows:
                target = games / row["console_dir"] / row["game_file"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "waians_picks.py"),
                    "--csv",
                    str(ROOT / "game-library.csv"),
                    "--fat-root",
                    str(fat),
                    "--games-root",
                    str(games),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            mgl_files = list((fat / "_Waian's Picks").rglob("*.mgl"))
            self.assertEqual(6142, len(mgl_files))
            for path in mgl_files:
                ET.parse(path)
            ampersand = next(path for path in mgl_files if "Sonic & Knuckles" in path.name)
            self.assertIn("&amp;", ampersand.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
