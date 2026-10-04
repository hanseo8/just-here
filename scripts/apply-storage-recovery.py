"""Apply a reviewed backup on a drained single-worker server; leave maintenance ON.

Run from the backend directory. Restart and verify before removing the marker.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

def main():
    if len(sys.argv) != 2:
        raise ValueError("one old backup path required")
    root = Path(os.environ.get("DATA_DIR", "")).resolve()
    if root != Path("/data") or not os.environ.get("ADMIN_TOKEN"):
        raise ValueError("operational storage and admin token required")
    if os.environ.get("RECEIPT_REWARDS", "off").lower() == "on":
        raise ValueError("rewards must remain off")
    sys.path.insert(0, str(Path.cwd()))
    from app import storage
    if not storage.is_persistent_dir(root):
        raise ValueError("real persistent mount required")
    spec = importlib.util.spec_from_file_location("recovery_merge", Path(__file__).with_name("merge-storage.py"))
    merge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(merge)
    old = merge.recovery.read_backup(Path(sys.argv[1]))
    marker = root / ".storage-maintenance"
    marker.touch(exist_ok=True)
    def status():
        req = urllib.request.Request("http://127.0.0.1:" + os.environ.get("PORT", "10000") + "/v1/admin/storage",
            headers={"X-Admin-Token": os.environ["ADMIN_TOKEN"]})
        return json.load(urllib.request.urlopen(req, timeout=5))["maintenance"]
    for _ in range(30):
        state = status()
        if not state["enabled"]:
            raise ValueError("maintenance not supported by running server")
        if state["active_requests"] == 0:
            break
        time.sleep(2)
    else:
        raise ValueError("requests did not drain")
    folder = root / ("recovery-apply-" + str(time.time_ns()))
    folder.mkdir(mode=0o700)
    before = folder / "before.json"
    before.write_text(json.dumps(storage.backup_payload()), encoding="utf-8")
    before.chmod(0o600)
    current = merge.recovery.read_backup(before)
    output, report = merge.merge(old, current)
    if not all(merge.recovery.compare(current, root).values()) or status()["active_requests"]:
        raise ValueError("live storage changed during preparation")
    stage = folder / "merged"
    merge.recovery.restore(output, stage)
    # Only users/events change; current catalogs remain untouched.
    for name in ("users.json", "events.jsonl"):
        os.replace(stage / name, root / name)
    if not all(merge.recovery.compare(output, root).values()):
        raise ValueError("applied bytes mismatch; keep maintenance and recover from before.json")
    (folder / "expected.json").write_text(json.dumps(merge.recovery.manifest(output)), encoding="utf-8")
    print(json.dumps({**report, "recovery_folder": str(folder), "maintenance": True,
                      "restart_required": True}))

if __name__ == "__main__":
    main()
