"""Restore a trusted reward backup into a NEW directory (never a running DATA_DIR).

Usage: python scripts/restore-rewards.py archive.zip new-directory
Account files and signing secrets must be restored separately.
"""
import argparse
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath


def restore(archive: Path, target: Path) -> None:
    if target.exists():
        raise ValueError("target must not exist")
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive entries")
        manifest = json.loads(bundle.read("manifest.json"))
        files = manifest.get("files", {})
        if manifest.get("version") != 1 or "rewards.sqlite3" not in files:
            raise ValueError("unsupported backup")
        if set(names) != set(files) | {"manifest.json"}:
            raise ValueError("unexpected archive entries")
        for name, expected in files.items():
            path = PurePosixPath(name)
            if name != "rewards.sqlite3" and not (
                len(path.parts) == 2 and path.parts[0] == "receipt_uploads"
                and path.parts[1] not in {".", ".."} and "\\" not in name and ":" not in name
            ):
                raise ValueError("unsafe archive path")
            digest = hashlib.sha256()
            with bundle.open(name) as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("backup checksum mismatch")
        target.mkdir(parents=True)
        for name in files:
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(name) as source, path.open("xb") as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    destination.write(chunk)
    db = sqlite3.connect(target / "rewards.sqlite3")
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("restored database integrity failure")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("restored database references invalid")
        for (name,) in db.execute("SELECT image_path FROM receipts"):
            if name != "receipt_uploads/deleted" and name not in files:
                raise ValueError("receipt missing from backup")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    restore(args.archive, args.target)
    print("Backup restored and verified. Live storage has not been changed.")
