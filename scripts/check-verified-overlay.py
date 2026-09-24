"""검증 메뉴 업어·묶음·가격을 로컬에서만 검사한다. 엔진에는 연결하지 않는다."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.place_meta import estimated_price_krw, per_person_budget_krw  # noqa: E402
from app.titles import _price, resolve_persona  # noqa: E402
from app.verified_menus import (  # noqa: E402
    apply_verified,
    expand_cards,
    load_catalog,
    match_place,
    overlay_inventory,
    pick_first_pack,
    pick_verified_menu,
    review_payload,
    usable_listed_price,
    visit_overlay_enabled,
)

root = Path(__file__).resolve().parents[1]
priority = load_catalog(root / "data" / "verified-menus.songdo.priority.json")
official = load_catalog(root / "data" / "verified-menus.songdo.official.json")


def fail(msg: str) -> None:
    print("FAIL", msg)
    sys.exit(1)


if visit_overlay_enabled() not in (True, False):
    fail("연결 스위치가 없다")

if any(m.get("menu_verified") for m in official["menus"]):
    fail("브랜드 공식 6행을 menu_verified로 올리면 안 된다")
if official.get("brand_only") != 6:
    fail(f"브랜드 전용 수가 6이 아니다: {official}")

branch = [m for m in priority["menus"] if m.get("menu_verified")]
brand = [m for m in priority["menus"] if not m.get("menu_verified")]
if len(branch) != 3:
    fail(f"지점 확인 행 {len(branch)}")
if any(m["place_name"] != "띠오데산타바바라 본점" for m in branch):
    fail("지점 확인이 띠오 외 매장에 붙었다")
if not brand:
    fail("브랜드만 확인된 행이 없다")

tio = next(m for m in branch if m["menu_name"] == "타코 3pcs")
place = {
    "place_id": "kakao_282259471",
    "kakao_place_id": "282259471",
    "name": "띠오데산타바바라 본점",
    "address": "인천 연수구 센트럴로 160",
    "menu_name": "멕시칸,브라질",
    "price_krw": 18000,
    "price_source": "estimated",
    "lat": 37.39199167575102,
    "lng": 126.64455106033076,
    "source": "kakao",
}
other_branch = {
    **place,
    "place_id": "kakao_999",
    "kakao_place_id": "999",
    "name": "띠오데산타바바라 다른점",
    "address": "인천 연수구 송도동 1",
    "lat": 37.4,
    "lng": 126.7,
}
hanam = {
    "place_id": "kakao_437344292",
    "kakao_place_id": "437344292",
    "name": "하남돼지집 송도센트럴파크점",
    "address": "인천 연수구 센트럴로 160",
    "menu_name": "삼겹살",
    "price_krw": 22000,
    "price_source": "estimated",
    "lat": 37.39225,
    "lng": 126.64508,
    "source": "kakao",
}
hanam_other = {
    **hanam,
    "place_id": "kakao_111",
    "kakao_place_id": "111",
    "name": "하남돼지집 송도랜드마크점",
    "address": "인천 연수구 랜드마크로 100",
}

if match_place(tio, [other_branch]) is not None:
    fail("같은 상호 다른 지점에 붙었다")
if match_place(tio, [place]) is None:
    fail("같은 카카오 지점을 못 찾았다")

over = apply_verified(place, tio)
if over.get("lat") != place["lat"] or over.get("lng") != place["lng"]:
    fail("검증 메뉴를 붙이며 좌표가 바뀌었다")
if over["menu_name"] != "타코 3pcs" or over.get("price_source") != "catchtable_listed":
    fail("지점 페이지 게시 가격이 캐치테이블 표시가로 안 들어갔다")
if over.get("price_label") != "캐치테이블 표시 가격":
    fail("캐치테이블 표시 가격 라벨이 없다")
if over.get("price_for_delivery") is True or over.get("price_channel") != "unspecified":
    fail("이용 채널 미확인 가격을 배달 가격으로 썼다")
if over.get("price_krw") == 13500 or over.get("price_unit") != "menu":
    fail("메뉴 전체 가격을 1인 가격 칸에 넣었다")

brand_row = next(m for m in brand if m["place_name"].startswith("바르다김선생"))
teacher = {
    "place_id": "kakao_313092230",
    "kakao_place_id": "313092230",
    "name": "바르다김선생 인천송도센트럴파크점",
    "address": "인천 연수구 센트럴로 160",
    "menu_name": "분식",
    "price_krw": 12000,
    "price_source": "estimated",
    "lat": 37.39258,
    "lng": 126.64455,
    "source": "kakao",
}
brand_over = apply_verified(teacher, brand_row)
if brand_over.get("menu_verified") or brand_over.get("menu_name") == brand_row["menu_name"]:
    fail("브랜드만 확인된 행을 지점 판매처럼 붙였다")
if brand_over.get("sale_status") != "need_branch_check":
    fail("브랜드 행 상태가 지점 확인 필요로 안 남았다")

inv, stats = overlay_inventory([place, teacher, hanam], priority["menus"])
if stats["recommendable"] != 3:
    fail(f"추천 가능 행 {stats}")
if inv[0].get("menu_verified") is not True:
    fail("띠오에 지점 확인 메뉴가 안 붙었다")
if inv[1].get("menu_verified") or inv[1]["menu_name"] != "분식":
    fail("검증 없을 때 기존 실상호 추천이 바뀌었다")
if inv[2].get("menu_verified"):
    fail("메뉴 없는 하남돼지집이 검증으로 바뀌었다")

cards = expand_cards([place, teacher, hanam, other_branch], priority["menus"])
tio_cards = [c for c in cards if c.get("place_id") == "kakao_282259471" and c.get("menu_verified")]
if len(tio_cards) != 3:
    fail(f"띠오 메뉴 카드 {len(tio_cards)}")
if any(c.get("lat") != place["lat"] for c in tio_cards):
    fail("여러 메뉴 카드에서 좌표가  ev어졌다")
pack = pick_first_pack(cards, 3)
place_ids = [c.get("place_id") for c in pack]
if len(set(place_ids)) != 3:
    fail(f"첫 묶음이 한 매장으로 채워졌다: {place_ids}")

if usable_listed_price(inv[1]) is not None:
    fail("가격 미확인을 저렴한 것으로 처리했다")
if usable_listed_price({**teacher, "price_source": "estimated", "menu_verified": False}) is not None:
    fail("예상 가격을 확인가로 썼다")
if usable_listed_price(over) is not None:
    fail("인분 미확인 메뉴가를 1인 확인가로 썼다")

platter_row = next(m for m in branch if m["menu_name"] == "파히타플래터")
platter = apply_verified(place, platter_row)
if platter.get("price_krw") == 58000 or per_person_budget_krw(platter) is not None:
    fail("플래터 58,000원을 1인 예산에 썼다")
if _price(platter) is not None:
    fail("플래터 전체가를 칭호 가격으로 읽었다")
if estimated_price_krw(platter) == 58000:
    fail("플래터 전체가를 추정 1인 가격으로 썼다")
persona = resolve_persona(
    intent="visit",
    weather="clear",
    left_swipe_count=0,
    right_swipe_count=0,
    decision_time_seconds=30,
    distance_m=80,
    place=platter,
    hour=13,
    weekday=2,
)
if persona["id"] == "flexer":
    fail("플래터 58,000원으로 고가 칭호를 붙였다")
if pick_verified_menu(branch, prefer="share")["menu_name"] != "파히타플래터":
    fail("나눠 먹기 조건에서 플래터가 안 골라졌다")
if pick_verified_menu(branch, prefer="taco")["menu_name"] != "타코 3pcs":
    fail("타코 조건에서 타코가 안 골라졌다")
if pick_verified_menu(branch, prefer="burrito")["menu_name"] != "브리또":
    fail("브리또 조건에서 브리또가 안 골라졌다")
defaults = {pick_verified_menu(branch, salt=f"s{i}")["menu_name"] for i in range(24)}
if "파히타플래터" in defaults:
    fail("신호 없이 인분 미확인 플래터를 기본으로 골랐다")
if defaults != {"타코 3pcs", "브리또"}:
    fail(f"기본 규칙이 타코·브리또를 순환하지 않는다: {defaults}")
taco_over, _ = overlay_inventory([place], priority["menus"], prefer="taco")
if taco_over[0]["menu_name"] != "타코 3pcs":
    fail("overlay가 extras[0] 고정이다")
burrito_over, _ = overlay_inventory([place], priority["menus"], prefer="burrito")
if burrito_over[0]["menu_name"] != "브리또":
    fail("브리또 overlay 선택이 안 된다")
share_over, _ = overlay_inventory([place], priority["menus"], prefer="share")
if share_over[0]["menu_name"] != "파히타플래터":
    fail("플래터 overlay 선택이 안 된다")

review = review_payload()
if review.get("branch_confirmed") != 3:
    fail("검수 페이로드의 지점 확인 수가 다르다")
if review["anchor"]["lat"] != 37.3925 or review["anchor"]["lng"] != 126.6450:
    fail("검수 도보 기준 좌표가 없다")
if len(review["user_cards"]) != 1:
    fail(f"구매 후보가 매장당 1장이 아니다: {review['user_cards']}")
if any(not c.get("menu_verified") for c in review["user_cards"] + review["pack"] + review["branch_menus"]):
    fail("지점 판매 미확인 메뉴를 구매 후보로 내렸다")
if any(n.get("place_name", "").startswith("띠오") for n in review["investigation_notes"]):
    fail("띠오를 조사 메모로 내렸다")
if review["pick_examples"]["platter"]["menu_name"] != "파히타플래터":
    fail("검수 예시에서 플래터가 안 나온다")
if review["pick_examples"]["taco"]["menu_name"] != "타코 3pcs":
    fail("검수 예시에서 타코가 안 나온다")
if review["pick_examples"]["burrito"]["menu_name"] != "브리또":
    fail("검수 예시에서 브리또가 안 나온다")
if not review["user_cards"][0].get("eta_label", "").startswith("도보 약"):
    fail("검수 도보 시간이 계산되지 않았다")

empty, empty_stats = overlay_inventory([hanam, hanam_other], [])
if empty[0]["menu_name"] != "삼겹살" or empty_stats["matched_places"] != 0:
    fail("검증 데이터가 없을 때 기존 실상호가 유지되지 않는다")

print("overlay 통과")
print(f"공식 6행 브랜드 전용, 우선 작업 지점확인 {len(branch)} / 브랜드 {len(brand)}")
