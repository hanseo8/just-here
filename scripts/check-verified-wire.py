"""방문 검증 메뉴 연결 ON/OFF와 안전 장치를 검사한다."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import engine  # noqa: E402
from app.verified_menus import (  # noqa: E402
    overlay_visit_cards,
    pick_verified_menu,
    visit_overlay_enabled,
)

root = Path(__file__).resolve().parents[1]
LAT, LNG = 37.39199167575102, 126.64455106033076


def fail(msg: str) -> None:
    print("FAIL", msg)
    sys.exit(1)


tio_place = {
    "place_id": "kakao_282259471",
    "kakao_place_id": "282259471",
    "name": "띠오데산타바바라 본점",
    "menu_id": "kakao_tio",
    "menu_name": "멕시칸",
    "kind": "멕시칸,브라질",
    "category": "western",
    "kakao_category": "음식점 > 양식",
    "open_now": True,
    "source": "kakao",
    "tags": ["#근처_실상호"],
    "delivery_sensitivity": 0.5,
    "address": "인천 연수구 센트럴로 160",
    "lat": LAT,
    "lng": LNG,
}
other = {
    **tio_place,
    "place_id": "kakao_x",
    "kakao_place_id": "999",
    "name": "다른집",
    "menu_id": "kakao_x",
    "menu_name": "한식",
    "kind": "한식",
    "category": "korean",
    "lat": LAT + 0.0004,
    "lng": LNG,
}


def session_with(places, **kwargs):
    s = engine.create_session(LAT, LNG, kwargs.get("intent", "visit"), "clear")
    s.inventory_source = "kakao"
    s.places = places
    s.taste = list(kwargs.get("taste") or [])
    s.meal_context = kwargs.get("meal_context") or "meal"
    s.adjust_filters = dict(kwargs.get("adjust") or {})
    return s


os.environ["VERIFIED_MENUS_VISIT"] = "off"
if visit_overlay_enabled():
    fail("OFF인데 스위치가 켜져 있다")
s_off = session_with([tio_place, other])
off_cards, radius_off, _ = engine.build_visit_cards(s_off)
if radius_off != 700:
    fail(f"OFF 반경 {radius_off}")
if any(c.get("menu_verified") for c in off_cards):
    fail("OFF인데 검증 메뉴가 붙었다")
if any(c.get("menu_source") == "verified" for c in off_cards):
    fail("OFF인데 메뉴 출처가 바뀌었다")

os.environ["VERIFIED_MENUS_VISIT"] = "on"
if not visit_overlay_enabled():
    fail("ON인데 스위치가 꺼져 있다")
s_on = session_with([tio_place, other])
on_cards, radius_on, _ = engine.build_visit_cards(s_on)
if radius_on != 700:
    fail("검증 메뉴 때문에 반경이 넓어졌다")
tio = next(c for c in on_cards if c["place_id"] == "kakao_282259471")
other_card = next(c for c in on_cards if c["place_id"] == "kakao_x")
if tio.get("menu_verified") is not True or not tio.get("verified_menu_id"):
    fail("필터 통과 매장에 검증 메뉴가 안 붙었다")
if tio["menu_name"] == "양식":
    fail("검증 메뉴명이 추정 종류로 남았다")
if other_card.get("menu_verified"):
    fail("매칭 안 된 실상호까지 검증으로 바뀌었다")
if tio.get("distance_m") is None or tio.get("lat") != LAT:
    fail("업어 후 거리·좌표가 바뀌었다")
if tio.get("price_for_delivery") is True:
    fail("방문 연결을 배달 가격으로 확대했다")
if tio["menu_name"] == "파히타플래터":
    fail("신호 없이 플래터를 기본으로 붙였다")

s_share = session_with([tio_place], taste=["share"])
share_cards, _, _ = engine.build_visit_cards(s_share)
if share_cards[0]["menu_name"] != "파히타플래터":
    fail("나눠 먹기 취향인데 플래터가 안 붙었다")
s_taco = session_with([tio_place], taste=["taco"])
if engine.build_visit_cards(s_taco)[0][0]["menu_name"] != "타코 3pcs":
    fail("타코 취향인데 타코가 안 붙었다")
s_bur = session_with([tio_place], taste=["burrito"])
if engine.build_visit_cards(s_bur)[0][0]["menu_name"] != "브리또":
    fail("브리또 취향인데 브리또가 안 붙었다")

s_late = session_with([tio_place], meal_context="late_night")
late = engine.build_visit_cards(s_late)[0][0]
if late.get("hours_verified"):
    fail("야식에서 미확인 영업시간을 확인된 것처럼 썼다")
if "미확인" not in str(late.get("hours") or "") and late.get("hours") != "카카오맵에서 확인":
    fail(f"야식 영업시간 미확인이 숨겨졌다: {late.get('hours')}")

s_del = engine.create_session(LAT, LNG, "delivery", "clear")
brand, _, _ = engine.build_brand_cards(s_del)
if any(c.get("verified_menu_id") for c in brand):
    fail("배달 덱에 검증 메뉴를 붙였다")

pack = engine._pick_diverse_pack(
    [
        {"menu_id": "a", "place_id": "p1", "kind": "타코", "category": "western"},
        {"menu_id": "b", "place_id": "p1", "kind": "브리또", "category": "western"},
        {"menu_id": "c", "place_id": "p2", "kind": "한식", "category": "korean"},
        {"menu_id": "d", "place_id": "p3", "kind": "중식", "category": "chinese"},
    ]
)
if [c["place_id"] for c in pack].count("p1") != 1:
    fail("첫 묶음이 한 매장으로 채워졌다")

empty = overlay_visit_cards(
    [{"place_id": "none", "menu_name": "한식", "source": "kakao"}],
    intent="visit",
)
if empty[0]["menu_name"] != "한식":
    fail("매칭 실패 때 기존 추천이 끊겼다")

defaults = {pick_verified_menu(
    [
        {"menu_id": "1", "menu_name": "파히타플래터", "menu_tags": ["platter"], "price_unit": "menu", "portion_confirmed": False, "menu_verified": True, "branch_sale_confirmed": True, "menu_scope": "branch"},
        {"menu_id": "2", "menu_name": "타코 3pcs", "menu_tags": ["taco"], "menu_verified": True, "branch_sale_confirmed": True, "menu_scope": "branch"},
        {"menu_id": "3", "menu_name": "브리또", "menu_tags": ["burrito"], "menu_verified": True, "branch_sale_confirmed": True, "menu_scope": "branch"},
    ],
    salt=f"x{i}",
)["menu_name"] for i in range(20)}
if "파히타플래터" in defaults:
    fail("기본 규칙이 플래터를 골랐다")

s_on2 = session_with([tio_place])
cards = engine.build_visit_cards(s_on2)[0]
engine.reset_pack(s_on2)
s_on2.pack_cards = cards[:1]
found = engine.find_place(s_on2, "kakao_tio")
if not found or not found.get("verified_menu_id"):
    fail("후보에서 verified_menu_id를 되찾지 못한다")
if engine.LOGIC_VERSION != "meal-context-v2.visit-menu":
    fail(f"로직 버전 {engine.LOGIC_VERSION}")

print("wire 통과")
print(f"ON 메뉴={tio['menu_name']} id={tio.get('verified_menu_id')} OFF 유지={off_cards[0]['menu_name']}")
