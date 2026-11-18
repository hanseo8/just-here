"""Isolated attribution/funnel regression; never read or write production events."""
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from backend.app import analytics as a


def row(event, visit="visit-alpha-00001", second=0, **props):
    return {"ts": f"2026-11-18T01:00:{second:02d}Z", "event": event, "device_id": "fixture-device",
            "props": {"visit_id": visit, "session_id": "s", "pack_id": "p", **props}}


rows = [row("app_open", utm_source="threads", utm_campaign="launch", utm_content="hook"),
        row("app_open", second=1), row("recommend_shown", second=2), row("recommend_shown", second=3),
        row("match_done", second=4), row("match_done", second=5), row("handoff_open", second=6),
        row("handoff_open", second=7), row("app_open", "visit-bravo-00002", utm_source="threads", utm_content="other"),
        row("recommend_shown", "visit-bravo-00002", second=2),
        row("app_open", "visit-direct-0003"),
        row("match_done", "visit-direct-0003", second=2),  # no recommendation: must not count as choice
        row("handoff_open", "visit-direct-0003", second=3),
        row("recommend_shown", "visit-missing-004"),
        row("app_open", "visit-test-000005", traffic_type="test"),
        row("app_open", "visit-preview-06", session_id="design-preview"),
        {"ts": "2026-11-18T01:00:00Z", "event": "app_open", "props": {}},
        {"ts": "invalid", "event": "app_open", "props": {"visit_id": "visit-invalid-001"}}]
result = a.acquisition_metrics(list(reversed(rows)))
assert [result[k] for k in ("visits", "recommended", "chosen", "handoff")] == [3, 2, 1, 1], result
assert result["choice_rate"] == 50 and result["handoff_rate"] == 100
assert result["visits_missing_open"] == 1 and result["legacy_events_without_visit"] == 1
assert len(result["by_campaign"]) == 3
assert "fixture-device" not in json.dumps(result) and "visit-alpha" not in json.dumps(result)
hook = next(x for x in result["by_campaign"] if x["utm_content"] == "hook")
assert hook["visits"] == hook["chosen"] == hook["handoff"] == 1
assert a.acquisition_metrics([])["choice_rate"] is None
assert a._day_key("2026-11-17T15:30:00Z") == "2026-11-18"
assert a._day_key("2026-11-17T15:30:00") == "2026-11-18"
assert a._day_key(123) == ""
# Reversed event arrival cannot turn an earlier handoff into a later conversion.
reversed_stage = [row("app_open"), row("handoff_open", second=1), row("match_done", second=2), row("recommend_shown", second=3)]
assert a.acquisition_metrics(reversed_stage)["chosen"] == 0
# Unequal choose/no-choice rates catch the old dashboard inversion.
sample = [row("recommend_shown", f"visit-sample-{n:04}", session_id=f"s{n}") for n in range(3)]
sample.append(row("swipe_go", "visit-sample-0000", second=1, session_id="s0", rank=1))
p = a.product_metrics(sample)
assert p["first_pack_choose_rate"] == 33.3 and p["first_pack_no_choice_rate"] == 66.7

with tempfile.TemporaryDirectory() as raw:
    previous = a.EVENTS_PATH
    a.EVENTS_PATH = Path(raw) / "events.jsonl"
    try:
        for props in ({"traffic_type": "test"}, {"session_id": "design-preview"}):
            assert a.append_event("app_open", props=props)["ignored"]
        assert not a.EVENTS_PATH.exists()
        event = a.append_event("app_open", props={"visit_id": "visit-safe-000001", "utm_source": "threads", "utm_content": "email@example.com", "utm_campaign": "https://private.example"})
        assert event["props"]["utm_source"] == "threads"
        assert "utm_content" not in event["props"] and "utm_campaign" not in event["props"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with a.EVENTS_PATH.open("a", encoding="utf-8") as f:
            for bad in ([1, 2], {"ts": 123, "props": {}}, {"ts": now, "event": "app_open", "props": {"traffic_type": "test"}}):
                f.write(json.dumps(bad) + "\n")
        summary = a.summarize(1)
        assert summary["totals"]["app_open"] == 1
        assert "first_pack_choose_rate" in summary["conversion"]
    finally:
        a.EVENTS_PATH = previous

print("PASS acquisition: campaign separation, deduped visits, ordered funnel, legacy/preview/test exclusion, KST dates, safe labels, missing stages and correct choose rate")
