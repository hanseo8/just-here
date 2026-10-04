"""Offline recovery regression checks; never touches live storage."""
import importlib.util
import json
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("restore_storage", Path(__file__).with_name("restore-storage.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def rejected(payload, source):
    source.write_text(json.dumps(payload), encoding="utf-8")
    try:
        module.read_backup(source)
    except ValueError:
        return
    raise AssertionError("invalid backup accepted")


with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    source = root / "backup.json"
    payload = {"files": {"users.json": '{"guest_test":{"name":"테스트"}}',
                         "events.jsonl": '{"event":"persist_probe"}\n'},
               "missing": ["verified-menus.json", "deals.json"], "errors": {}}
    source.write_text(json.dumps(payload), encoding="utf-8-sig")
    files = module.read_backup(source)
    target = root / "restored"
    module.restore(files, target)
    assert all(module.compare(files, target).values())
    for existing in (target, root):
        try:
            module.restore(files, existing)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing directory accepted")
    (target / "events.jsonl").write_bytes(b'{"event":"new"}\n')
    assert module.compare(files, target) == {"users.json": True, "events.jsonl": False}
    for name, content in (("users.json", '{"uid":1,"uid":2}'),
                          ("users.json", '[]'), ("events.jsonl", '{}\nbroken'),
                          ("events.jsonl", '{"amount":NaN}')):
        bad = {**payload, "files": {**payload["files"], name: content}}
        rejected(bad, source)
    rejected({**payload, "errors": {"users.json": "read failed"}}, source)
    rejected({**payload, "files": {**payload["files"], "../escape": "{}"}}, source)
    rejected({**payload, "missing": []}, source)
    assert not (root.parent / "escape").exists()
print("PASS: UTF-8 recovery, no overwrite, corruption and path rejection, exact comparison")
