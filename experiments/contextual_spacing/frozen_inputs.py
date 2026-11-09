#!/usr/bin/env python3
"""Offline export/verify/restore for the v3 gallery frozen prerequisites.

Frozen build inputs are the 26 captures named by the frozen source
catalogue (13 cases x mono/gray), the 26 Class-L calibration curves the
staging builder reads, and the 4 shipped runtime files (pkg-web and
pkg-nodejs glue plus WASM bytes). Files are opaque and preserved
byte-for-byte. Fonts stay in their owning repository locations and are
not archived. Export checks the catalogue bytes against the lock pin,
which is reconciled with the builder pin; membership is derived from
the parsed catalogue plus the builder paths below.
"""

import argparse
import hashlib
import json
import os
import re
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ENGINE = HERE / "oriented_engine"
BUILDER_PATH = HERE / "yinyangfit_interactive_v3.py"
SOURCE_FORMAT = "yinyangfit-interactive-v3-source-catalogue/1"
SOURCE_CATALOGUE_SHA = (
    "71e374ca218d75cf7657b7e008fc16f437165affe3ca27937330c8cfb3a9a6ec"
)
SHIP_WASM_SHA = (
    "c27fe2e2c7d53114fbaace7829c6eec13d06e2ee28039b6a18296207dea7f855"
)
ENGINE_PKG_VERSION = "0.0.0"
LOCK_FORMAT = "frozen-inputs/1"
ARCHIVES_PARENT = (
    REPO / "out/diagnostics/contextual-spacing/input-archives"
)
CURVES_DIR = (
    REPO
    / "out/diagnostics/contextual-spacing/yinyang-normalization-repair"
    / "target-calibration/curves"
)
ARCHIVE_NAME = "frozen-inputs.tar.gz"
MANIFEST_NAME = "manifest.json"
LOCK_PATH = HERE / "frozen-inputs.lock.json"

RUNTIME_RELS = [
    "experiments/contextual_spacing/oriented_engine/pkg-web/yinyang_oriented_engine.js",
    "experiments/contextual_spacing/oriented_engine/pkg-web/yinyang_oriented_engine_bg.wasm",
    "experiments/contextual_spacing/oriented_engine/pkg-nodejs/yinyang_oriented_engine.js",
    "experiments/contextual_spacing/oriented_engine/pkg-nodejs/yinyang_oriented_engine_bg.wasm",
]


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def builder_catalogue_pin():
    """Catalogue pin the staging builder enforces, parsed from its source."""
    text = BUILDER_PATH.read_text()
    match = re.search(
        r'SOURCE_CATALOGUE_SHA\s*=\s*\(\s*"([0-9a-f]+)"\s*"([0-9a-f]+)"\s*\)',
        text,
    )
    if not match:
        raise ValueError("builder catalogue pin shape changed; reconcile by hand")
    return match.group(1) + match.group(2)


def load_catalogue(source_site):
    catalogue_path = Path(source_site) / "catalogue.json"
    catalogue = json.loads(catalogue_path.read_text())
    if catalogue.get("format") != SOURCE_FORMAT:
        raise ValueError("source catalogue format drift")
    if len(catalogue.get("cases", [])) != 13:
        raise ValueError("catalogue must hold 13 cases")
    return catalogue


def membership(source_site):
    """Repo-relative frozen files plus expected SHAs.

    Capture paths and SHAs come from the parsed catalogue; curves follow
    the builder curve directory per dataset; runtime files are the pinned
    glue and WASM bytes the builder and rescore helper resolve.
    """
    catalogue = load_catalogue(source_site)
    files = {}
    for case in catalogue["cases"]:
        case_id = case["id"]
        for profile in ("mono", "gray"):
            prof = case["profiles"][profile]
            capture_rel = prof["capture"]
            files[capture_rel] = prof["capture_sha256"]
            curve_rel = (
                CURVES_DIR / f"{case_id}-{profile}.json"
            ).relative_to(REPO).as_posix()
            files[curve_rel] = None
    for rel in RUNTIME_RELS:
        files[rel] = None
    return catalogue, files


def resolve_expected(source_site):
    _, members = membership(source_site)
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("format") != LOCK_FORMAT:
        raise ValueError("frozen-inputs lock format drift")
    if lock.get("ship_wasm_sha") != SHIP_WASM_SHA:
        raise ValueError("ship wasm pin drift")
    builder_pin = builder_catalogue_pin()
    if builder_pin != SOURCE_CATALOGUE_SHA:
        raise ValueError("frozen_inputs catalogue pin differs from builder pin")
    if lock.get("source_catalogue_sha") != builder_pin:
        raise ValueError("lock catalogue pin differs from builder pin")
    expected = {}
    for rel, catalogue_sha in members.items():
        if rel not in lock["files"]:
            raise ValueError(f"lock missing frozen input: {rel}")
        expected[rel] = lock["files"][rel]
        if catalogue_sha is not None and catalogue_sha != expected[rel]:
            raise ValueError(f"catalogue pin mismatch: {rel}")
    extra = sorted(set(lock["files"]) - set(members))
    if extra:
        raise ValueError(f"lock lists unexpected inputs: {extra}")
    return lock, expected


def check_working_tree(source_site):
    lock, expected = resolve_expected(source_site)
    catalogue_bytes = (Path(source_site) / "catalogue.json").read_bytes()
    if hashlib.sha256(catalogue_bytes).hexdigest() != lock["source_catalogue_sha"]:
        raise ValueError(
            "source catalogue bytes differ from lock pin; "
            "restore the canonical source catalogue before exporting"
        )
    for rel, want in expected.items():
        path = REPO / rel
        if not path.is_file():
            raise ValueError(f"missing frozen input: {rel}")
        have = sha_file(path)
        if have != want:
            raise ValueError(f"frozen input drift: {rel}")
        if rel.endswith(".wasm") and have != SHIP_WASM_SHA:
            raise ValueError(f"shipping wasm moved: {rel}")
    cargo = (ENGINE / "Cargo.toml").read_text()
    if 'version = "0.0.0"' not in cargo:
        raise ValueError("engine pkg version drift")
    return expected


def check_archive_dir(archive_dir):
    archive_dir = Path(archive_dir)
    try:
        archive_dir.resolve().relative_to(ARCHIVES_PARENT.resolve())
    except ValueError:
        raise ValueError("archive directory must be inside input-archives")
    return archive_dir


def write_archive(expected, archive_dir):
    archive_dir.mkdir(parents=True, exist_ok=False)
    archive_path = archive_dir / ARCHIVE_NAME
    with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for rel in sorted(expected):
            path = REPO / rel
            info = tarfile.TarInfo(name=rel)
            info.size = path.stat().st_size
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            with path.open("rb") as handle:
                tar.addfile(info, handle)
    digest = sha_file(archive_path)
    manifest = {
        "format": LOCK_FORMAT,
        "source_format": SOURCE_FORMAT,
        "source_catalogue_sha": SOURCE_CATALOGUE_SHA,
        "ship_wasm_sha": SHIP_WASM_SHA,
        "engine_pkg_version": ENGINE_PKG_VERSION,
        "files": dict(sorted(expected.items())),
        "archive": {
            "file": ARCHIVE_NAME,
            "sha256": digest,
            "bytes": archive_path.stat().st_size,
            "members": len(expected),
        },
    }
    (archive_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return archive_path, manifest


def read_archive_manifest(archive_dir):
    manifest_path = Path(archive_dir) / MANIFEST_NAME
    archive_path = Path(archive_dir) / ARCHIVE_NAME
    if not manifest_path.is_file() or not archive_path.is_file():
        raise ValueError("archive directory must hold manifest and tarball")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != LOCK_FORMAT:
        raise ValueError("archive manifest format drift")
    return archive_path, manifest


def verify_archive(archive_dir, source_site):
    _, expected = resolve_expected(source_site)
    archive_path, manifest = read_archive_manifest(archive_dir)
    if manifest.get("ship_wasm_sha") != SHIP_WASM_SHA:
        raise ValueError("archive wasm pin mismatch")
    if manifest.get("files") != dict(sorted(expected.items())):
        raise ValueError("archive manifest does not match lock membership")
    if sha_file(archive_path) != manifest["archive"]["sha256"]:
        raise ValueError("archive tarball corrupt")
    seen = {}
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                raise ValueError(f"unexpected archive entry: {member.name}")
            if member.name in seen:
                raise ValueError(f"duplicate archived input: {member.name}")
            if member.name not in expected:
                raise ValueError(f"unexpected archived input: {member.name}")
            data = tar.extractfile(member).read()
            if hashlib.sha256(data).hexdigest() != expected[member.name]:
                raise ValueError(f"archived input corrupt: {member.name}")
            seen[member.name] = True
    missing = sorted(set(expected) - set(seen))
    if missing:
        raise ValueError(f"archive missing inputs: {missing}")
    return manifest


def safe_target(dest_resolved, rel):
    """Destination path for one archived input, refusing link escapes.

    Rejects absolute names and parent references, refuses to write
    through an existing symbolic link component, and refuses an existing
    symbolic link at the target itself.
    """
    parts = Path(rel).parts
    if Path(rel).is_absolute() or ".." in parts:
        raise ValueError(f"unsafe archived path: {rel}")
    target = dest_resolved / rel
    cursor = dest_resolved
    for part in target.relative_to(dest_resolved).parts[:-1]:
        cursor = cursor / part
        if os.path.lexists(cursor) and cursor.is_symlink():
            raise ValueError(f"refusing to write through link: {cursor}")
    if os.path.lexists(target) and target.is_symlink():
        raise ValueError(f"refusing to overwrite link: {rel}")
    return target


def restore_archive(archive_dir, dest, source_site):
    manifest = verify_archive(archive_dir, source_site)
    dest = Path(dest)
    if not dest.is_dir():
        raise ValueError("restore destination must be an existing directory")
    dest_resolved = dest.resolve()
    archive_path = Path(archive_dir) / ARCHIVE_NAME
    with tarfile.open(archive_path, "r:gz") as tar:
        members = [member for member in tar.getmembers() if member.isfile()]
        if sorted(member.name for member in members) != sorted(manifest["files"]):
            raise ValueError("archive members do not match manifest")
        payloads = {member.name: tar.extractfile(member).read() for member in members}
    conflicts = []
    targets = {}
    for rel in payloads:
        if rel not in manifest["files"]:
            raise ValueError(f"unexpected archived input: {rel}")
        target = safe_target(dest_resolved, rel)
        targets[rel] = target
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != manifest["files"][rel]:
                conflicts.append(rel)
    if conflicts:
        raise ValueError(f"refusing to overwrite conflicting files: {sorted(conflicts)}")
    for rel, data in payloads.items():
        target = targets[rel]
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if hashlib.sha256(target.read_bytes()).hexdigest() != manifest["files"][rel]:
            raise ValueError(f"restored input corrupt: {rel}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export", "verify", "restore"])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--dest", type=Path, default=None)
    parser.add_argument("--source-site", type=Path, default=HERE / "yinyangfit_interactive_v3_source")
    args = parser.parse_args()
    archive_dir = Path(args.archive)
    if args.command == "export":
        # Generated output stays under the ignored input-archives parent.
        # Verify and restore accept a user-carried copy at any location.
        archive_dir = check_archive_dir(archive_dir)
        expected = check_working_tree(args.source_site)
        archive_path, manifest = write_archive(expected, archive_dir)
        print(json.dumps({"archive": str(archive_path), "sha256": manifest["archive"]["sha256"],
                          "members": manifest["archive"]["members"], "bytes": manifest["archive"]["bytes"]}))
    elif args.command == "verify":
        manifest = verify_archive(archive_dir, args.source_site)
        print(json.dumps({"archive": str(archive_dir / ARCHIVE_NAME),
                          "sha256": manifest["archive"]["sha256"], "members": manifest["archive"]["members"]}))
    else:
        if args.dest is None:
            parser.error("restore requires --dest")
        manifest = restore_archive(archive_dir, args.dest, args.source_site)
        print(json.dumps({"dest": str(args.dest), "members": manifest["archive"]["members"]}))


if __name__ == "__main__":
    main()
