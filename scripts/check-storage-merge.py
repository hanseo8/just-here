"""Synthetic recovery checks: no personal data or live writes."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("merge_storage", Path(__file__).with_name("merge-storage.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample(users, devices, events):
    return {"users.json": json.dumps({"users": users, "device_index": devices}).encode(),
            "events.jsonl": ("".join(json.dumps(event) + "\n" for event in events)).encode()}


old = sample({"a": {"uid": "a", "taste": ["rice"]}}, {"device_a": "a"}, [{"id": "1"}, {"id": "1"}])
current = sample({"b": {"uid": "b"}}, {"device_b": "b"}, [{"id": "1"}, {"id": "2"}])
current["verified-menus.json"] = b'[{"current":true}]'
merged, report = module.merge(old, current)
assert report["merged_users"] == 2 and report["merged_events"] == 3
assert merged["verified-menus.json"] == current["verified-menus.json"]
assert module.merge(merged, current)[0] == merged  # Retrying adds no events.
same = sample({"a": {"uid": "a", "taste": ["rice"]}}, {"device_a": "a"}, [])
assert module.merge(old, same)[1]["merged_users"] == 1
for bad in (
    sample({"a": {"uid": "a", "taste": ["pasta"]}}, {"device_a": "a"}, []),
    sample({"b": {"uid": "b"}}, {"device_a": "b"}, []),
    sample({"b": {"uid": "wrong"}}, {}, []),
    sample({"b": {"uid": "b"}}, {"device_b": "missing"}, []),
):
    try:
        module.merge(old, bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe identity merge accepted")
assert module.merge(old, current)[0] == merged
print("PASS: identity conflicts rejected, new users preserved, event multiplicity and retry preserved")
