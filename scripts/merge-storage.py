"""Prepare an offline recovery candidate from old and current storage backups.

Conflicting identities stop the merge. Never writes to a running DATA_DIR.
"""
import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

spec = importlib.util.spec_from_file_location("restore_storage", Path(__file__).with_name("restore-storage.py"))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def users_document(data):
    document = recovery.strict_json(data.decode("utf-8"))
    if not isinstance(document, dict) or set(document) != {"users", "device_index"}:
        raise ValueError("unsupported users schema")
    users, devices = document["users"], document["device_index"]
    if not isinstance(users, dict) or not isinstance(devices, dict):
        raise ValueError("invalid users inventory")
    for uid, user in users.items():
        if not isinstance(user, dict) or user.get("uid") != uid:
            raise ValueError("invalid user identity")
    if any(not isinstance(uid, str) or uid not in users for uid in devices.values()):
        raise ValueError("unresolved device identity")
    return document


def merge(old_files, current_files):
    if not {"users.json", "events.jsonl"} <= old_files.keys():
        raise ValueError("old backup needs users and events")
    if not {"users.json", "events.jsonl"} <= current_files.keys():
        raise ValueError("current backup needs users and events")
    old = users_document(old_files["users.json"])
    current = users_document(current_files["users.json"])
    for table in ("users", "device_index"):
        for key in old[table].keys() & current[table].keys():
            if old[table][key] != current[table][key]:
                # Never guess which profile, account link, or history should win.
                raise ValueError("identity conflict requires explicit resolution")
    users = {**old["users"], **current["users"]}
    devices = {**old["device_index"], **current["device_index"]}
    # Preserve repeated events within either source. Deduplicate only their overlap.
    old_events = [recovery.strict_json(line) for line in old_files["events.jsonl"].decode("utf-8").splitlines()]
    current_events = [recovery.strict_json(line) for line in current_files["events.jsonl"].decode("utf-8").splitlines()]
    canonical = lambda event: json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    overlap = Counter(canonical(event) for event in old_events)
    added = []
    for event in current_events:
        key = canonical(event)
        if overlap[key]:
            overlap[key] -= 1
        else:
            added.append(event)
    output = dict(current_files)
    output["users.json"] = json.dumps({"users": users, "device_index": devices}, ensure_ascii=False, indent=2).encode("utf-8")
    output["events.jsonl"] = ("".join(canonical(event) + "\n" for event in old_events + added)).encode("utf-8")
    # Menu/deal catalogs retain the current snapshot, including current absence.
    report = {"old_users": len(old["users"]), "current_users": len(current["users"]),
              "merged_users": len(users), "old_events": len(old_events),
              "current_events": len(current_events), "merged_events": len(old_events) + len(added),
              "overlapping_events": len(current_events) - len(added)}
    return output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_backup", type=Path)
    parser.add_argument("current_backup", type=Path)
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    try:
        old = recovery.read_backup(args.old_backup)
        current = recovery.read_backup(args.current_backup)
        files, report = merge(old, current)
        if args.stage:
            recovery.restore(files, args.stage)
        print(json.dumps({**report, "files": recovery.manifest(files),
                          "staged": bool(args.stage), "live_applied": False}, indent=2))
        return 0
    except (ValueError, TypeError, OSError) as exc:
        print("Merge refused: " + (str(exc) if isinstance(exc, ValueError) else "file access failed"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
