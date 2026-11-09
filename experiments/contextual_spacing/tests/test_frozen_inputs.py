#!/usr/bin/env python3
"""Focused checks for the v3 frozen-inputs export/verify/restore recipe.

Mechanical checks only: archive membership, checksum enforcement,
duplicate/corrupt/unexpected rejection, and conflicting-target and
symbolic-link protection. Restores run in temporary directories; the
working tree is only read.
"""

import hashlib
import importlib.util
import json
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "frozen_inputs",
    REPO / "experiments/contextual_spacing/frozen_inputs.py",
)
frozen_inputs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(frozen_inputs)

ARCHIVE = (
    REPO / "out/diagnostics/contextual-spacing/input-archives/v3-frozen-1"
)
SOURCE_SITE = REPO / "experiments/contextual_spacing/yinyangfit_interactive_v3_source"
LOCK = json.loads(
    (REPO / "experiments/contextual_spacing/frozen-inputs.lock.json").read_text()
)


def copy_archive_to_temp(tmp):
    dest = Path(tmp) / "carried"
    shutil.copytree(ARCHIVE, dest)
    return dest


class FrozenInputsTest(unittest.TestCase):
    def test_membership_narrow(self):
        files = LOCK["files"]
        self.assertEqual(len(files), 56)
        captures = [k for k in files if "/captures/" in k]
        curves = [k for k in files if "/curves/" in k]
        runtime = [k for k in files if "oriented_engine/pkg-" in k]
        self.assertEqual(len(captures), 26)
        self.assertEqual(len(curves), 26)
        self.assertEqual(len(runtime), 4)
        self.assertEqual(sorted(files), sorted(set(files)))

    def test_catalogue_pin_reconciled(self):
        actual = hashlib.sha256(
            (SOURCE_SITE / "catalogue.json").read_bytes()
        ).hexdigest()
        self.assertEqual(actual, LOCK["source_catalogue_sha"])
        self.assertEqual(actual, frozen_inputs.builder_catalogue_pin())

    def test_working_tree_matches_lock(self):
        expected = frozen_inputs.check_working_tree(SOURCE_SITE)
        self.assertEqual(len(expected), 56)

    def test_verify_retained_archive(self):
        manifest = frozen_inputs.verify_archive(ARCHIVE, SOURCE_SITE)
        self.assertEqual(manifest["archive"]["members"], 56)

    def test_round_trip_temp_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "restore"
            dest.mkdir()
            manifest = frozen_inputs.restore_archive(ARCHIVE, dest, SOURCE_SITE)
            self.assertEqual(manifest["archive"]["members"], 56)
            for rel, want in manifest["files"].items():
                have = hashlib.sha256((dest / rel).read_bytes()).hexdigest()
                self.assertEqual(have, want, rel)
                live = hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
                self.assertEqual(have, live, rel)

    def test_restore_skips_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "restore"
            dest.mkdir()
            frozen_inputs.restore_archive(ARCHIVE, dest, SOURCE_SITE)
            manifest = frozen_inputs.restore_archive(ARCHIVE, dest, SOURCE_SITE)
            self.assertEqual(manifest["archive"]["members"], 56)

    def test_loader_wiring(self):
        here = REPO / "experiments/contextual_spacing/oriented_engine"
        node_glue = (here / "pkg-nodejs/yinyang_oriented_engine.js").read_text()
        self.assertIn("yinyang_oriented_engine_bg.wasm", node_glue)
        self.assertIn("__dirname", node_glue)
        for rel in LOCK["files"]:
            if rel.endswith(".wasm"):
                self.assertEqual(LOCK["files"][rel], LOCK["ship_wasm_sha"])
        self.assertTrue((here / "pkg-web/yinyang_oriented_engine.js").stat().st_size > 0)

    def test_verify_rejects_duplicate_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            carried = copy_archive_to_temp(tmp)
            tarball = carried / frozen_inputs.ARCHIVE_NAME
            with tarfile.open(tarball, "r:gz") as tar:
                entries = [
                    (m, tar.extractfile(m).read())
                    for m in tar.getmembers()
                    if m.isfile()
                ]
            first_info, first_data = entries[0]
            with tarfile.open(tarball, "w:gz", format=tarfile.PAX_FORMAT) as tar:
                for info, data in entries:
                    entry = tarfile.TarInfo(name=info.name)
                    entry.size = len(data)
                    entry.mtime = 0
                    import io

                    tar.addfile(entry, io.BytesIO(data))
                dup = tarfile.TarInfo(name=first_info.name)
                dup.size = len(first_data)
                dup.mtime = 0
                import io

                tar.addfile(dup, io.BytesIO(first_data))
            manifest_path = carried / frozen_inputs.MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text())
            manifest["archive"]["sha256"] = frozen_inputs.sha_file(tarball)
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            with self.assertRaises(ValueError):
                frozen_inputs.verify_archive(carried, SOURCE_SITE)

    def test_verify_rejects_corrupt_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            carried = copy_archive_to_temp(tmp)
            tarball = carried / frozen_inputs.ARCHIVE_NAME
            with tarfile.open(tarball, "r:gz") as tar:
                entries = [
                    (m, tar.extractfile(m).read())
                    for m in tar.getmembers()
                    if m.isfile()
                ]
            info, data = entries[0]
            bad = b"\x00" + data[1:] if data[:1] != b"\x00" else b"\xff" + data[1:]
            with tarfile.open(tarball, "w:gz", format=tarfile.PAX_FORMAT) as tar:
                for entry_info, entry_data in entries:
                    payload = bad if entry_info.name == info.name else entry_data
                    entry = tarfile.TarInfo(name=entry_info.name)
                    entry.size = len(payload)
                    entry.mtime = 0
                    import io

                    tar.addfile(entry, io.BytesIO(payload))
            manifest_path = carried / frozen_inputs.MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text())
            manifest["archive"]["sha256"] = frozen_inputs.sha_file(tarball)
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            with self.assertRaises(ValueError):
                frozen_inputs.verify_archive(carried, SOURCE_SITE)

    def test_verify_rejects_unexpected_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            carried = copy_archive_to_temp(tmp)
            tarball = carried / frozen_inputs.ARCHIVE_NAME
            with tarfile.open(tarball, "r:gz") as tar:
                entries = [
                    (m, tar.extractfile(m).read())
                    for m in tar.getmembers()
                    if m.isfile()
                ]
            with tarfile.open(tarball, "w:gz", format=tarfile.PAX_FORMAT) as tar:
                for info, data in entries:
                    entry = tarfile.TarInfo(name=info.name)
                    entry.size = len(data)
                    entry.mtime = 0
                    import io

                    tar.addfile(entry, io.BytesIO(data))
                extra = tarfile.TarInfo(name="out/diagnostics/extra.json")
                extra.size = 2
                extra.mtime = 0
                import io

                tar.addfile(extra, io.BytesIO(b"{}"))
            manifest_path = carried / frozen_inputs.MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text())
            manifest["archive"]["sha256"] = frozen_inputs.sha_file(tarball)
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            with self.assertRaises(ValueError):
                frozen_inputs.verify_archive(carried, SOURCE_SITE)

    def test_restore_refuses_conflicting_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "restore"
            dest.mkdir()
            rel = sorted(LOCK["files"])[0]
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"conflicting content")
            with self.assertRaises(ValueError):
                frozen_inputs.restore_archive(ARCHIVE, dest, SOURCE_SITE)
            self.assertEqual(target.read_bytes(), b"conflicting content")
            self.assertEqual(
                [p for p in dest.rglob("*") if p.is_file()], [target]
            )

    def test_restore_refuses_link_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "restore"
            dest.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (dest / "out").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                frozen_inputs.restore_archive(ARCHIVE, dest, SOURCE_SITE)
            self.assertEqual(list(outside.iterdir()), [])

    def test_restore_refuses_link_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "restore"
            dest.mkdir()
            rel = sorted(LOCK["files"])[0]
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            elsewhere = Path(tmp) / "elsewhere.json"
            elsewhere.write_bytes(b"{}")
            target.symlink_to(elsewhere)
            with self.assertRaises(ValueError):
                frozen_inputs.restore_archive(ARCHIVE, dest, SOURCE_SITE)
            self.assertTrue(target.is_symlink())
            self.assertEqual(elsewhere.read_bytes(), b"{}")


if __name__ == "__main__":
    unittest.main()
