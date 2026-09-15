"""배달(브랜드) / 방문(주변) 두 덱과 3장 묶음 계약이 성립하는지 확인.

배달 카드는 거리를 만들어 내지 않아야 하고, 핸드오프는 반드시 브랜드 자사
주문 URL로 나가야 한다. 방문은 가상 식당 폴백 없이 실상호만 쓴다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from datetime import datetime, timezone  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import analytics, brands, deals, engine, kakao  # noqa: E402
from app.main import app  # noqa: E402
from app.users import compute_taste_signals  # noqa: E402

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
    check(all(c.get("menu_verified") is False for c in vcards), "방문 메뉴는 미검증")
    labels = set(engine.KIND_KO.values())
    check(
        all(c.get("menu_name") in labels for c in vcards),
        "표시 메뉴는 종류 한글이지 카카오 말단이 아니다",
    )
    check(
        all(c.get("menu_name") != c.get("place_name") for c in vcards),
        "상호를 판매 메뉴처럼 쓰지 않는다",
    )
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

print("\n[개인화] 장기 신호는 여러 날에만 붙는다")
now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
same_day = [
    {"action": "nope", "category": "meat", "kind": "치킨", "at": "2026-09-15T01:00:00Z"},
    {"action": "nope", "category": "meat", "kind": "치킨", "at": "2026-09-15T03:00:00Z"},
]
sig_day = compute_taste_signals(same_day, now=now)
check("치킨" not in sig_day["hate_categories"], "하루 거절은 장기 hate가 아니다")

two_days = same_day + [
    {"action": "nope", "category": "meat", "kind": "치킨", "at": "2026-09-14T01:00:00Z"}
]
sig_hate = compute_taste_signals(two_days, now=now)
check(sig_hate["hate_categories"].get("치킨", 0) > 0, "이틀 거절은 장기 hate")

goes = [
    {"action": "lets_go", "category": "meat", "kind": "치킨", "at": "2026-09-08T01:00:00Z"},
    {"action": "lets_go", "category": "meat", "kind": "치킨", "at": "2026-09-13T01:00:00Z"},
    {"action": "ate", "category": "meat", "kind": "치킨", "at": "2026-09-13T12:00:00Z"},
]
sig_pref = compute_taste_signals(goes, now=now)
check("치킨" in sig_pref["frequent_categories"], "이틀 선택은 자주 고른 종류")
check(sig_pref["prefer_categories"].get("치킨", 0) > sig_hate["hate_categories"].get("치킨", 0), "식사 확인이 거절보다 세다")

plain = engine.create_session(LAT, LNG, "delivery", "clear")
hated = engine.create_session(LAT, LNG, "delivery", "clear")
engine.apply_profile(hated, sig_hate)
loved = engine.create_session(LAT, LNG, "delivery", "clear")
engine.apply_profile(loved, sig_pref)


def _chicken_score(sess):
    cards, _, _ = engine.build_cards(sess)
    hit = next((c for c in cards if c.get("kind") == "치킨"), None)
    return hit["_score"] if hit else None


plain_sc = _chicken_score(plain)
hate_sc = _chicken_score(hated)
love_sc = _chicken_score(loved)
check(plain_sc is not None and hate_sc is not None, "치킨 카드 점수를 계산한다")
check(hate_sc < plain_sc, f"반복 거절은 점수가 낮다 ({hate_sc} < {plain_sc})")
check(love_sc > plain_sc, f"반복 선택·식사는 점수가 높다 ({love_sc} > {plain_sc})")

engine.reset_pack(loved)
feed, _, _ = engine.present_feed(loved)
why = next((c.get("why") or "" for c in loved.pack_cards if c.get("kind") == "치킨"), "")
check("자주 고른" in why, f"기록 있는 why → {why or (feed[0].get('why') if feed else '')}")
check("평소 좋아하는" not in why, "근거 없는 개인화 문구를 쓰지 않는다")

print("\n[혜택] 확인된 할인만 붙는다")
try:
    s_empty = engine.create_session(LAT, LNG, "delivery", "clear")
    empty_cards, _, _ = engine.build_cards(s_empty)
    check(all(not c.get("deal") for c in empty_cards), "카탈로그가 비면 혜택을 만들지 않는다")
    check(
        all(o["id"] != "deal" for o in engine.adjust_options(s_empty)),
        "혜택이 부족하면 확인된 혜택 버튼을 숨긴다",
    )

    live_now = "2026-09-15T12:00:00+09:00"
    expired = {
        "id": "old",
        "brand_id": "kyochon",
        "source": "brand_notice",
        "title": "지난 혜택",
        "condition": "종료",
        "starts_at": "2026-08-01T00:00:00+09:00",
        "ends_at": "2026-08-31T23:59:59+09:00",
        "verified_at": live_now,
    }
    one = {
        "id": "kyo-1",
        "brand_id": "kyochon",
        "source": "brand_notice",
        "title": "세트 1천원 할인",
        "condition": "공식 주문",
        "starts_at": "2026-09-01T00:00:00+09:00",
        "ends_at": "2026-09-30T23:59:59+09:00",
        "min_order_krw": 15000,
        "delivery_fee_included": False,
        "verified_at": live_now,
    }
    deals.set_catalog([expired])
    s_exp = engine.create_session(LAT, LNG, "delivery", "clear")
    exp_cards, _, _ = engine.build_cards(s_exp)
    kyo = next(c for c in exp_cards if c.get("brand_id") == "kyochon")
    check(not kyo.get("deal"), "만료된 혜택은 카드에 안 붙는다")

    deals.set_catalog([one])
    s_one = engine.create_session(LAT, LNG, "delivery", "clear")
    one_cards, _, _ = engine.build_cards(s_one)
    kyo1 = next(c for c in one_cards if c.get("brand_id") == "kyochon")
    deal = kyo1.get("deal") or {}
    check(deal.get("title") == "세트 1천원 할인", "확인된 혜택은 카드에 붙는다")
    dumped = str(deal)
    check("final_price" not in deal and "최종" not in dumped, "최종 결제금액을 만들지 않는다")
    check(deal.get("audience") == "everyone", "공통 혜택만 카드에 붙는다")
    check(
        all(o["id"] != "deal" for o in engine.adjust_options(s_one)),
        "혜택 1건이면 확인된 혜택 버튼을 열지 않는다",
    )
    plain_kyo = next(c for c in empty_cards if c.get("brand_id") == "kyochon")["_score"]
    check(kyo1["_score"] > plain_kyo, "확인된 혜택은 점수에 가산된다")

    three = [
        one,
        {**one, "id": "bbq-1", "brand_id": "bbq", "title": "올라이브 할인"},
        {**one, "id": "pel-1", "brand_id": "pelicana", "title": "양념 할인"},
    ]
    deals.set_catalog(three)
    s_pub = engine.create_session(LAT, LNG, "delivery", "clear")
    check(
        any(o["id"] == "deal" for o in engine.adjust_options(s_pub)),
        "확인된 혜택 3건부터 조정 선택지를 연다",
    )
    engine.apply_adjust(s_pub, "deal")
    deal_feed, _, _ = engine.present_feed(s_pub)
    check(all(c.get("deal") for c in s_pub.pack_cards), "확인된 혜택 조정은 혜택 카드만 남긴다")
    check(deal_feed and deal_feed[0].get("deal"), "피드에도 혜택이 보인다")

    s_vis = engine.create_session(LAT, LNG, "visit", "clear")
    check(
        all(o["id"] != "deal" for o in engine.adjust_options(s_vis)),
        "브랜드 혜택만으로는 방문 할인 버튼을 안 연다",
    )

    high = {**one, "min_order_krw": 50000}
    deals.set_catalog([high])
    s_hi = engine.create_session(LAT, LNG, "delivery", "clear")
    kyo_hi = next(c for c in engine.build_cards(s_hi)[0] if c.get("brand_id") == "kyochon")
    check(not kyo_hi.get("deal"), "최소주문보다 싼 카드에는 혜택을 안 붙인다")

    member = {**one, "audience": "membership"}
    deals.set_catalog(
        [
            member,
            {**member, "id": "m2", "brand_id": "bbq"},
            {**member, "id": "m3", "brand_id": "pelicana"},
        ]
    )
    s_mem = engine.create_session(LAT, LNG, "delivery", "clear")
    mem_cards, _, _ = engine.build_cards(s_mem)
    check(all(not c.get("deal") for c in mem_cards), "멤버십 혜택은 공통처럼 안 붙인다")
    check(
        all(o["id"] != "deal" for o in engine.adjust_options(s_mem)),
        "멤버십만 있으면 확인된 혜택을 열지 않는다",
    )

    other_hub = [
        {**one, "id": "h1", "hub_id": "hub_busan"},
        {**one, "id": "h2", "brand_id": "bbq", "hub_id": "hub_busan"},
        {**one, "id": "h3", "brand_id": "pelicana", "hub_id": "hub_busan"},
    ]
    deals.set_catalog(other_hub)
    s_away = engine.create_session(LAT, LNG, "delivery", "clear")
    check(
        all(o["id"] != "deal" for o in engine.adjust_options(s_away)),
        "다른 지역 혜택은 이 시장에 안 연다",
    )
finally:
    deals.set_catalog(None)

print("\n[제외] 안 먹어요는 강한 제외다")
s_ex = engine.create_session(LAT, LNG, "delivery", "clear")
engine.apply_profile(s_ex, {"exclude_categories": ["치킨"]})
ex_cards, _, _ = engine.build_cards(s_ex)
check(ex_cards and all(c.get("kind") != "치킨" for c in ex_cards), "안 먹어요 종류는 후보에서 빠진다")
s_pack = engine.create_session(LAT, LNG, "delivery", "clear")
engine.present_feed(s_pack)
first_kind = s_pack.pack_cards[0]["kind"]
engine.apply_exclude(s_pack, [first_kind], exclude=True)
check(all(c.get("kind") != first_kind for c in s_pack.pack_cards), "지금 묶음에서도 바로 뺀다")
no_tok = client.post("/v1/me/exclude", json={"uid": uid, "kind": "치킨"})
check(no_tok.status_code == 401, f"토큰 없이 안 먹어요 → {no_tok.status_code}")
saved = client.post(
    "/v1/me/exclude",
    json={"uid": uid, "kind": "치킨"},
    headers={"X-Guest-Token": token},
)
check(saved.status_code == 200, f"토큰 있으면 안 먹어요 → {saved.status_code}")
me_ex = client.get("/v1/me", params={"uid": uid}, headers={"X-Guest-Token": token})
excl = (me_ex.json().get("user") or {}).get("preferences", {}).get("exclude_categories") or []
check("치킨" in excl, "안 먹어요는 다음 방문용으로 저장된다")
client.post(
    "/v1/me/exclude",
    json={"uid": uid, "kind": "치킨", "exclude": False},
    headers={"X-Guest-Token": token},
)

print("\n[방문] 카카오 말단은 메뉴가 아니다")
s_menu = engine.create_session(LAT, LNG, "visit", "clear")
s_menu.inventory_source = "kakao"
s_menu.places = [
    {
        "place_id": "kakao_x",
        "name": "탕화쿵푸마라탕 송도5공구점",
        "lat": LAT,
        "lng": LNG,
        "menu_id": "kakao_m_x",
        "menu_name": "탕화쿵푸마라탕",
        "kind": "탕화쿵푸마라탕",
        "category": "chinese",
        "kakao_category": "음식점 > 중식 > 탕화쿵푸마라탕",
        "open_now": True,
        "source": "kakao",
        "tags": ["#근처_실상호"],
        "delivery_sensitivity": 0.5,
        "address": "인천 연수구",
    }
]
v_fake, _, _ = engine.build_visit_cards(s_menu)
check(bool(v_fake), "가짜 실상호로 방문 카드가 나온다")
if v_fake:
    check(v_fake[0]["menu_name"] == "중식", f"표시 메뉴={v_fake[0]['menu_name']}")
    check(v_fake[0]["kind"] == "탕화쿵푸마라탕", "kind는 다양성·제외용 말단")
    check(v_fake[0]["inferred_kind"] == "탕화쿵푸마라탕", "카카오 분류는 추정으로만")
    check(v_fake[0]["menu_verified"] is False, "방문 메뉴 미검증")
    check(v_fake[0]["menu_name"] != v_fake[0]["place_name"], "상호 ≠ 메뉴")
check(engine.card_menu_name(s_menu.places[0]) == "중식", "영수증도 추정 종류")

print("\n[지표] 세션 성공 지표")
rows = [
    {
        "ts": "2026-09-14T00:00:00Z",
        "event": "app_open",
        "device_id": "d1",
        "uid": "",
        "props": {},
    },
    {
        "ts": "2026-09-15T00:00:00Z",
        "event": "app_open",
        "device_id": "d1",
        "uid": "",
        "props": {},
    },
    {
        "ts": "2026-09-15T00:00:12Z",
        "event": "recommend_shown",
        "device_id": "d1",
        "uid": "",
        "props": {"session_id": "s1", "pack_id": "p1"},
    },
    {
        "ts": "2026-09-15T00:00:20Z",
        "event": "swipe_go",
        "device_id": "d1",
        "uid": "",
        "props": {"session_id": "s1", "pack_id": "p1", "rank": 2},
    },
    {
        "ts": "2026-09-15T00:00:20Z",
        "event": "match_done",
        "device_id": "d1",
        "uid": "",
        "props": {"session_id": "s1", "pack_id": "p1"},
    },
    {
        "ts": "2026-09-15T00:00:22Z",
        "event": "handoff_open",
        "device_id": "d1",
        "uid": "",
        "props": {"session_id": "s1"},
    },
    {
        "ts": "2026-09-15T00:59:48Z",
        "event": "app_open",
        "device_id": "d2",
        "uid": "",
        "props": {},
    },
    {
        "ts": "2026-09-15T01:00:00Z",
        "event": "recommend_shown",
        "device_id": "d2",
        "uid": "",
        "props": {"session_id": "s2", "pack_id": "p2"},
    },
    {
        "ts": "2026-09-15T01:00:05Z",
        "event": "pack_exhausted",
        "device_id": "d2",
        "uid": "",
        "props": {"session_id": "s2", "pack_id": "p2"},
    },
    {
        "ts": "2026-09-15T01:00:06Z",
        "event": "adjust",
        "device_id": "d2",
        "uid": "",
        "props": {"session_id": "s2"},
    },
    {
        "ts": "2026-09-15T01:00:10Z",
        "event": "match_done",
        "device_id": "d2",
        "uid": "",
        "props": {"session_id": "s2", "pack_id": "p3"},
    },
]
pm = analytics.product_metrics(rows)
check(pm["median_open_to_first_recommend_s"] == 12.0, f"진입→추천 {pm['median_open_to_first_recommend_s']}")
check(pm["median_first_recommend_to_choice_s"] == 9.0, f"추천→선택 {pm['median_first_recommend_to_choice_s']}")
check(pm["first_pack_choose_rate"] == 50.0, f"첫 묶음 선택 {pm['first_pack_choose_rate']}")
check(pm["first_pack_no_choice_rate"] == 50.0, "첫 3장 안 선택 50%")
check(pm["first_pack_exhaust_rate"] == 50.0, "3장 모두 거절 50%")
check(pm["choose_after_adjust_rate"] == 100.0, "조정 후 선택 100%")
check(pm["match_to_handoff_rate"] == 50.0, "선택→클릭 50% (주문 완료 아님)")
check(pm["revisit_rate"] == 50.0, "재방문 1/2 기기")
check("handoff_open" in analytics.ALLOWED_EVENTS, "handoff_open 수집")

print()
if fails:
    print(f"실패 {len(fails)}건")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("전부 통과")
