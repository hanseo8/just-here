"""배달(브랜드) / 방문(주변) 두 덱과 3장 묶음 계약이 성립하는지 확인.

배달 카드는 거리를 만들어 내지 않아야 하고, 핸드오프는 반드시 브랜드 자사
주문 URL로 나가야 한다. 방문은 가상 식당 폴백 없이 실상호만 쓴다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app import brands, engine, kakao  # noqa: E402
from app.main import app  # noqa: E402

LAT, LNG = 37.3826, 126.6432  # 송도
fails: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


print(f"카탈로그 브랜드 수: {brands.brand_count()}")

print("\n[배달] 브랜드 덱")
s = engine.create_session(LAT, LNG, "delivery", "clear", taste=["chicken"])
pool, radius, gold = engine.build_cards(s)
check(len(pool) > 0, f"후보가 나온다 ({len(pool)}장)")
check(radius == 0, f"반경은 0으로 내려간다 (실제 {radius})")
check(all(c["is_brand"] for c in pool), "모든 카드가 브랜드 카드다")
check(all(c["distance_m"] is None for c in pool), "거리를 만들어 내지 않는다")
check(all(c["address"] == "" for c in pool), "지점 주소를 붙이지 않는다")
check(all(c["order_url"].startswith("https://") for c in pool), "주문 URL이 있다")
check(all(c["kind"] for c in pool), "사용자에게 보여줄 분류(kind)가 있다")
check(gold is False, "골드 카드는 없다")
top = pool[0]
check(bool(top.get("taste_match")), f"취향(chicken)이 맨 앞에 온다 → {top['place_name']}")

print("\n[배달] 피드 묶음 3장")
cards, radius, gold = engine.present_feed(s)
check(len(cards) == 1, f"화면에는 한 장만 내려간다 (실제 {len(cards)})")
check(cards[0]["pack_rank"] == 1 and cards[0]["pack_size"] == 3, "첫 장은 1/3")
check(bool(cards[0].get("why")), f"why가 있다 → {cards[0].get('why')}")
kinds = [c.get("kind") or c.get("category") for c in s.pack_cards]
check(len(kinds) == len(set(kinds)), f"묶음 종류가 겹치지 않는다 → {kinds}")

print("\n[배달] 핸드오프")
place = engine.find_place(s, cards[0]["menu_id"])
check(place is not None, "menu_id로 브랜드를 되찾는다")
handoff = engine.apply_lets_go(s, place)
check(handoff["provider"] == "brand_direct", f"provider={handoff['provider']}")
check(handoff["url"] == cards[0]["order_url"], "핸드오프 URL == 브랜드 주문 URL")
check("배달앱" in handoff.get("note", ""), "배달앱을 안 거친다고 안내한다")
print(f"       cta: {handoff['cta']}")
print(f"       url: {handoff['url']}")

print("\n[배달] 3장 거절 → 조정 → 돌아가기")
s2 = engine.create_session(LAT, LNG, "delivery", "clear")
last = None
for i in range(3):
    deck, _, _ = engine.present_feed(s2)
    check(len(deck) == 1, f"{i + 1}번째 카드가 있다")
    last = deck[0]
    p = engine.find_place(s2, last["menu_id"])
    exhausted = engine.apply_nope(s2, p)
    if i < 2:
        check(exhausted is False, f"{i + 1}장째는 아직 조정이 아니다")
    else:
        check(exhausted is True, "3장 거절 후 조정이 열린다")
meta = engine.pack_meta(s2)
check(meta["adjust_needed"], "adjust_needed")
check(meta["can_undo"], "조정 화면에서도 돌아갈 수 있다")
empty, _, _ = engine.present_feed(s2)
check(empty == [], "조정 중에는 카드를 안 내려준다")
check(engine.apply_undo(s2), "이전 후보로 돌아간다")
restored, _, _ = engine.present_feed(s2)
check(len(restored) == 1, "돌아간 카드가 다시 나온다")
check(restored[0]["menu_id"] == last["menu_id"], "직전 후보와 같다")
check(not engine.pack_meta(s2)["adjust_needed"], "돌아가면 조정이 닫힌다")
engine.apply_nope(s2, engine.find_place(s2, restored[0]["menu_id"]))
engine.apply_adjust(s2, "different")
after, _, _ = engine.present_feed(s2)
check(len(after) == 1, "조정 후 새 묶음이 나온다")
check("다른 종류" in (after[0].get("why") or ""), f"조정 why → {after[0].get('why')}")

print("\n[배달] 패스해도 자동 리필하지 않는다")
s3 = engine.create_session(LAT, LNG, "delivery", "clear")
saw_adjust = False
for i in range(20):
    deck, _, _ = engine.present_feed(s3)
    if engine.pack_meta(s3)["adjust_needed"]:
        saw_adjust = True
        check(i == 3, f"자동 리필 없이 3장 뒤에 조정 (실제 {i}번째)")
        break
    if not deck:
        check(False, f"{i}번째에 조정 없이 덱이 비었다")
        break
    engine.apply_nope(s3, engine.find_place(s3, deck[0]["menu_id"]))
else:
    check(False, "20장까지 조정이 열리지 않았다")
check(saw_adjust, "3장 거절 후 조정이 열렸다")

print("\n[방문] 주변 덱")
s4 = engine.create_session(LAT, LNG, "visit", "clear")
vcards, vradius, _ = engine.build_cards(s4)
check(vradius == 700, f"방문 반경은 700m (실제 {vradius})")
check(s4.inventory_source in ("kakao", "empty"), f"출처={s4.inventory_source}")
check(all(c.get("source") == "kakao" for c in vcards), "방문 카드는 카카오 실상호만")
check(all(not c["is_brand"] for c in vcards), "브랜드 카드가 섞이지 않는다")
if vcards:
    check(all(c["distance_m"] is not None for c in vcards), "거리가 있다")
    check(all("도보" in c["eta_label"] for c in vcards), "ETA는 도보 기준이다")
    check(all(c.get("price_source") == "estimated" for c in vcards), "가격은 예상")
    check(all(c.get("menu_source") == "inferred" for c in vcards), "메뉴는 추정")
    vplace = engine.find_place(s4, vcards[0]["menu_id"])
    vhandoff = engine.apply_lets_go(s4, vplace)
    check(vhandoff["intent"] == "visit", f"방문 핸드오프 intent={vhandoff['intent']}")
    check("order_url" not in vhandoff, "방문에는 주문 URL이 붙지 않는다")
elif kakao.kakao_configured():
    check(True, "이 좌표에서는 카카오 실상호가 비어 빈 결과로 둔다")
else:
    check(True, "카카오 키가 없으면 가상 식당을 만들지 않고 비운다")

print("\n[토글] 배달 → 방문 → 배달")
s5 = engine.create_session(LAT, LNG, "delivery", "clear")
d1, _, _ = engine.present_feed(s5)
engine.apply_intent(s5, "visit")
v1, r1, _ = engine.present_feed(s5)
engine.apply_intent(s5, "delivery")
d2, r2, _ = engine.present_feed(s5)
check(len(d1) == 1 and d1[0]["is_brand"], "처음 배달 피드는 브랜드 한 장")
check(r1 == 700, "방문으로 바꾸면 반경 700m")
check(all(not c["is_brand"] for c in v1), "방문 피드에 브랜드가 없다")
check(len(d2) == 1 and d2[0]["is_brand"] and r2 == 0, "배달로 되돌리면 다시 브랜드")

print("\n[소유권] 게스트 토큰 없이 /v1/me 는 막힌다")
client = TestClient(app)
res = client.get("/v1/me", params={"uid": "u_nobody"})
check(res.status_code == 401, f"토큰 없이 me → {res.status_code}")
guest = client.post("/v1/auth/guest", json={"device_id": "check-brand-flow"})
check(guest.status_code == 200 and guest.json().get("guest_token"), "게스트 토큰을 발급한다")
token = guest.json()["guest_token"]
uid = guest.json()["uid"]
ok = client.get("/v1/me", params={"uid": uid}, headers={"X-Guest-Token": token})
check(ok.status_code == 200, f"토큰 있으면 me → {ok.status_code}")
wrong = client.get("/v1/me", params={"uid": uid}, headers={"X-Guest-Token": "nope"})
check(wrong.status_code == 401, "잘못된 토큰은 401")

print()
if fails:
    print(f"실패 {len(fails)}건")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("전부 통과")
