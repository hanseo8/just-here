"""검증 메뉴 카탈로그 형식 검사. 랭킹 연결 여부는 보지 않는다."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import data_dir  # noqa: E402
from app.verified_menus import (  # noqa: E402
    REQUIRED,
    WIRED_TO_RANKING,
    apply_verified,
    catalog_path,
    load_catalog,
    match_place,
    overlay_inventory,
    quality_report,
)

root = Path(__file__).resolve().parents[1]
example = root / "data" / "verified-menus.songdo.example.json"
live = catalog_path()

ex = load_catalog(example)
print(f"양식: {ex['count']}행 통과 (example 행은 제외) example_file={ex.get('example_file')}")
if ex["count"] != 0:
    print("FAIL 양식 파일의 예시 행이 검증 메뉴로 들어갔다")
    sys.exit(1)

official = load_catalog(root / "data" / "verified-menus.songdo.official.json")
print(f"공식 확인: {official['count']}행 브랜드 전용={official.get('brand_only')} 지점확인={official.get('branch_confirmed')}")
if official["count"] < 6:
    print("FAIL 공식 확인 행이 빠졌다")
    sys.exit(1)
if official.get("branch_confirmed"):
    print("FAIL 브랜드 공식 6행을 지점 판매 확인으로 올렸다")
    sys.exit(1)
if any(m.get("menu_verified") for m in official["menus"]):
    print("FAIL 브랜드 메뉴를 menu_verified로 처리했다")
    sys.exit(1)
if any(m.get("price_krw") for m in official["menus"]):
    print("FAIL 매장 미확인 가격을 공식 파일에 넣었다")
    sys.exit(1)
if official.get("branch_confirmed"):
    print("FAIL 브랜드 공식 파일을 지점 판매 확인으로 올렸다")
    sys.exit(1)

cat = load_catalog(live if live.exists() else example)
print(f"실제 입력 경로: {live}")
print(f"DATA_DIR: {data_dir()}")
print(f"영구 디스크 여부(DATA_DIR 설정): {cat.get('persistent')}")
print(f"입력: {cat['count']}행 검증됨 ready={cat['ready']} wired={cat.get('wired_to_ranking')}")
print("필수:", ", ".join(REQUIRED), "+ source_url|source_note")
print("20~30개는 실험 규모이지 품질 보장이 아니다.")
if cat["ready"]:
    print("FAIL 실험 규모를 품질 완료로 올리면 안 된다")
    sys.exit(1)
if live.name.endswith(".example.json"):
    print("FAIL 예시 파일을 운영 입력 경로로 쓰면 안 된다")
    sys.exit(1)

row = {
    "menu_name": "차돌된장찌개",
    "place_name": "송도국밥",
    "address": "인천 연수구 컨벤시아대로 100",
    "source": "official",
    "source_url": "https://example.com/menu",
    "confirmed_at": "2026-09-24",
    "kakao_place_id": "12345",
    "price_krw": 12000,
    "price_verified_at": "2026-09-24",
    "price_channel": "dine_in",
    "photo_url": "https://cdn.example/menu.jpg",
    "photo_rights": True,
    "photo_is_store_menu": True,
    "menu_scope": "branch",
    "branch_sale_confirmed": True,
    "meal_contexts": ["meal"],
}
from app.verified_menus import _clean  # noqa: E402

cleaned = _clean(row)
place = {
    "place_id": "kakao_12345",
    "name": "송도국밥",
    "address": "인천 연수구 컨벤시아대로 100",
    "menu_name": "한식",
    "price_krw": 9000,
    "price_source": "estimated",
    "image_url": "",
    "has_photo": False,
    "source": "kakao",
}
other = {**place, "place_id": "kakao_999", "name": "다른집"}
if match_place(cleaned, [other]) is not None:
    print("FAIL 다른 가게에 붙이면 안 된다")
    sys.exit(1)
if match_place(cleaned, [place]) is None:
    print("FAIL 같은 카카오 가게를 못 찾았다")
    sys.exit(1)
over = apply_verified(place, cleaned)
if over["menu_name"] != "차돌된장찌개" or over.get("price_source") != "listed":
    print("FAIL 검증 메뉴·가격이 카드에 안 들어갔다")
    sys.exit(1)
if over.get("photo_role") != "menu" or over.get("photo_is_example"):
    print("FAIL 메뉴 사진이 예시로 남았다")
    sys.exit(1)
no_price = apply_verified(place, {**cleaned, "price_krw": None, "price_verified_at": ""})
if no_price.get("price_source") == "listed":
    print("FAIL 가격 없는 행을 확인가로 쓰면 안 된다")
    sys.exit(1)
brand_only = apply_verified(place, {**cleaned, "menu_scope": "brand", "branch_sale_confirmed": False, "menu_verified": False})
if brand_only.get("menu_verified") or brand_only.get("menu_name") == "차돌된장찌개":
    print("FAIL 브랜드만 확인된 행을 지점 판매로 붙였다")
    sys.exit(1)
inv, stats = overlay_inventory([place, other], [cleaned])
if stats["matched_places"] != 1 or stats["unmatched_menus"] != 0:
    print(f"FAIL 매칭 통계 {stats}")
    sys.exit(1)
if inv[0]["menu_verified"] is not True or inv[1].get("menu_verified"):
    print("FAIL 매칭 안 된 가게까지 검증으로 바뀌었다")
    sys.exit(1)
q = quality_report({"menus": [cleaned], "reason": "not_wired_to_ranking"})
if q["ready"] or q["with_price"] != 1:
    print(f"FAIL 품질 보고 {q}")
    sys.exit(1)
print(f"품질: {q['count']}행 / 가격 {q['with_price']} / 사진 {q['with_photo']} / 연결 {q['wired_to_ranking']}")
print("통과")
