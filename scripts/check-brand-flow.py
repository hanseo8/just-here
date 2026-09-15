"""배달(브랜드) / 방문(주변) 두 덱이 각각 성립하는지 확인.

배달 카드는 거리를 만들어 내지 않아야 하고, 핸드오프는 반드시 브랜드 자사
주문 URL로 나가야 한다. 이 두 가지가 깨지면 배달 모드의 존재 이유가 없다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import brands, engine  # noqa: E402

LAT, LNG = 37.3826, 126.6432  # 송도
fails: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


print(f"카탈로그 브랜드 수: {brands.brand_count()}")

print("\n[배달] 브랜드 덱")
s = engine.create_session(LAT, LNG, "delivery", "clear", taste=["chicken"])
cards, radius, gold = engine.build_cards(s)
check(len(cards) > 0, f"카드가 나온다 ({len(cards)}장)")
check(radius == 0, f"반경은 0으로 내려간다 (실제 {radius})")
check(all(c["is_brand"] for c in cards), "모든 카드가 브랜드 카드다")
check(all(c["distance_m"] is None for c in cards), "거리를 만들어 내지 않는다")
check(all(c["address"] == "" for c in cards), "지점 주소를 붙이지 않는다")
check(all(c["order_url"].startswith("https://") for c in cards), "주문 URL이 있다")
check(all(c["kind"] for c in cards), "사용자에게 보여줄 분류(kind)가 있다")
top = cards[0]
check(bool(top.get("taste_match")), f"취향(chicken)이 맨 앞에 온다 → {top['place_name']}")

print("\n[배달] 핸드오프")
place = engine.find_place(s, top["menu_id"])
check(place is not None, "menu_id로 브랜드를 되찾는다")
handoff = engine.apply_lets_go(s, place)
check(handoff["provider"] == "brand_direct", f"provider={handoff['provider']}")
check(handoff["url"] == top["order_url"], "핸드오프 URL == 브랜드 주문 URL")
check("배달앱" in handoff.get("note", ""), "배달앱을 안 거친다고 안내한다")
print(f"       cta: {handoff['cta']}")
print(f"       url: {handoff['url']}")

print("\n[배달] 전부 패스해도 덱이 마르지 않는다")
s2 = engine.create_session(LAT, LNG, "delivery", "clear")
for i in range(brands.brand_count() + 4):
    deck, _, _ = engine.build_cards(s2)
    if not deck:
        check(False, f"{i}번째 패스에서 덱이 비었다")
        break
    p = engine.find_place(s2, deck[0]["menu_id"])
    engine.apply_nope(s2, p)
else:
    check(True, f"{brands.brand_count() + 4}회 연속 패스에도 카드가 계속 나온다")

print("\n[방문] 주변 덱")
s3 = engine.create_session(LAT, LNG, "visit", "clear")
vcards, vradius, _ = engine.build_cards(s3)
check(len(vcards) > 0, f"카드가 나온다 ({len(vcards)}장)")
check(vradius == 700, f"방문 반경은 700m (실제 {vradius})")
check(all(not c["is_brand"] for c in vcards), "브랜드 카드가 섞이지 않는다")
check(all(c["distance_m"] is not None for c in vcards), "거리가 있다")
check(all("도보" in c["eta_label"] for c in vcards), "ETA는 도보 기준이다")
vplace = engine.find_place(s3, vcards[0]["menu_id"])
vhandoff = engine.apply_lets_go(s3, vplace)
check(vhandoff["intent"] == "visit", f"방문 핸드오프 intent={vhandoff['intent']}")
check("order_url" not in vhandoff, "방문에는 주문 URL이 붙지 않는다")

print("\n[토글] 배달 → 방문 → 배달")
s4 = engine.create_session(LAT, LNG, "delivery", "clear")
d1, _, _ = engine.build_cards(s4)
engine.apply_intent(s4, "visit")
v1, r1, _ = engine.build_cards(s4)
engine.apply_intent(s4, "delivery")
d2, r2, _ = engine.build_cards(s4)
check(all(c["is_brand"] for c in d1), "처음 배달 덱은 브랜드")
check(all(not c["is_brand"] for c in v1) and r1 == 700, "방문으로 바꾸면 주변 덱")
check(all(c["is_brand"] for c in d2) and r2 == 0, "배달로 되돌리면 다시 브랜드")

print()
if fails:
    print(f"실패 {len(fails)}건")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("전부 통과")
