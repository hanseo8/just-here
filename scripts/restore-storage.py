"""Validate an admin storage backup, stage it offline, or compare restored bytes.

This does not merge users, overwrite live files, or prove disk persistence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

ALLOWED = {"users.json", "events.jsonl", "verified-menus.json", "deals.json"}


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("non-finite JSON number")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def read_backup(source):
    payload = strict_json(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("errors") != {}:
        raise ValueError("backup reports errors or has no error status")
    files, missing = payload.get("files"), payload.get("missing")
    if not isinstance(files, dict) or not files or not isinstance(missing, list):
        raise ValueError("invalid backup inventory")
    if any(not isinstance(name, str) for name in missing):
        raise ValueError("invalid missing file name")
    if set(files) & set(missing) or set(files) | set(missing) != ALLOWED:
        raise ValueError("unsafe or incomplete file inventory")
    result = {}
    for name, content in files.items():
        if not isinstance(content, str):
            raise ValueError("backup file content must be text")
        try:
            if name == "events.jsonl":
                if any(not isinstance(strict_json(line), dict) for line in content.splitlines()):
                    raise ValueError("event must be an object")
            else:
                value = strict_json(content)
                if not isinstance(value, (dict, list)):
                    raise ValueError("JSON document must be an object or array")
                if name == "users.json" and not isinstance(value, dict):
                    raise ValueError("users must be an object")
        except (ValueError, TypeError) as exc:
            # Never echo document contents or identifiers in console output.
            raise ValueError(f"invalid JSON in {name}") from exc
        result[name] = content.encode("utf-8")
    return result


def manifest(files):
    return {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(files.items())}


def restore(files, target):
    # mkdir(exist_ok=False) also rejects existing empty dirs and symlinks.
    target.mkdir(parents=False, exist_ok=False)
    if os.name != "nt":
        target.chmod(0o700)
    for name, data in files.items():
        with (target / name).open("xb") as output:
            output.write(data)
        if os.name != "nt":
            (target / name).chmod(0o600)
    # On I/O failure, preserve the partial directory and fail. Never retry over it.
    if not all(compare(files, target).values()):
        raise ValueError("restored bytes differ")


def compare(files, target):
    result = {}
    for name, data in files.items():
        path = target / name
        result[name] = not path.is_symlink() and path.is_file() and path.read_bytes() == data
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stage", type=Path, help="create a NEW offline directory; parent must exist")
    mode.add_argument("--compare", type=Path, help="read-only exact comparison with a directory")
    args = parser.parse_args()
    try:
        files = read_backup(args.backup)
        if args.stage:
            restore(files, args.stage)
        matches = compare(files, args.compare) if args.compare else None
        print(json.dumps({"files": manifest(files), "matches": matches,
                          "staged": bool(args.stage), "persistence_verified": False}, indent=2))
        return 1 if matches is not None and not all(matches.values()) else 0
    except (ValueError, OSError, TypeError):
        print("Backup validation/restore failed; no existing directory was overwritten.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
