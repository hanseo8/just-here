"""배달 모드 인벤토리 — 자사 주문 채널이 확인된 프랜차이즈.

배민·요기요·쿠팡이츠는 외부에서 검색어를 넘기는 공식 딥링크를 제공하지 않는다.
그래서 배달 모드는 배달앱을 경유하지 않고 브랜드 자사 주문 페이지로 바로 보낸다.

카탈로그 원칙 — `order_url`이 모바일 브라우저에서 실제로 열리고 주문 흐름이
시작되는 브랜드만 넣는다. 앱 설치나 로그인을 먼저 요구하는 브랜드(굽네·맘스터치·
써브웨이)와 웹 주문이 아예 없는 브랜드(bhc)는 "두 번 클릭 안 한다"는 약속을
지킬 수 없으므로 제외했다.

브랜드를 추가할 때는 반드시 `order_url`을 모바일 UA로 열어 200과 주문 화면을
확인한다. `scripts/check-brand-urls.py`가 상태 코드까지 확인해 준다.
"""
from __future__ import annotations

import copy


# category는 기존 취향/랭킹 어휘(korean·western·meat…)를 그대로 쓴다.
# kind는 사용자에게 보여 줄 한글 분류 — category보다 정확하다(치킨 ≠ 고기).
BRANDS: list[dict] = [
    # ── 치킨 ──────────────────────────────────────────────
    {
        "brand_id": "kyochon",
        "name": "교촌치킨",
        "menu_name": "교촌 오리지날",
        "kind": "치킨",
        "category": "meat",
        "taste": ["chicken", "meat"],
        "order_url": "https://www.kyochon.com/order",
        "channel": "교촌 공식 주문",
        "price_krw": 20000,
        "delivery_sensitivity": 0.55,
        "rating": 4.3,
        "tags": ["#간장_치킨"],
        "blurb": "간장 베이스 오리지날. 식어도 짠맛이 무너지지 않는 편.",
    },
    {
        "brand_id": "bbq",
        "name": "BBQ",
        "menu_name": "황금올리브치킨",
        "kind": "치킨",
        "category": "meat",
        "taste": ["chicken", "meat"],
        "order_url": "https://bbq.co.kr/",
        "channel": "BBQ 공식 주문",
        "price_krw": 21000,
        "delivery_sensitivity": 0.6,
        "rating": 4.3,
        "tags": ["#후라이드"],
        "blurb": "올리브유 후라이드. 도착 직후가 제일 바삭하다.",
    },
    {
        "brand_id": "nene",
        "name": "네네치킨",
        "menu_name": "스노윙 치즈",
        "kind": "치킨",
        "category": "meat",
        "taste": ["chicken", "meat"],
        "order_url": "https://nenechicken.com/home_order.asp",
        "channel": "네네치킨 공식 주문",
        "price_krw": 19000,
        "delivery_sensitivity": 0.55,
        "rating": 4.2,
        "tags": ["#치즈_파우더"],
        "blurb": "파우더 계열. 매운 걸 못 먹는 사람과 같이 먹기 좋다.",
    },
    {
        "brand_id": "pelicana",
        "name": "페리카나",
        "menu_name": "양념치킨",
        "kind": "치킨",
        "category": "meat",
        "taste": ["chicken", "meat", "spicy"],
        "order_url": "https://www.pelicana.co.kr/order/order",
        "channel": "페리카나 공식 주문",
        "price_krw": 18000,
        "delivery_sensitivity": 0.5,
        "rating": 4.1,
        "tags": ["#매콤_양념"],
        "blurb": "양념이 두껍다. 소스류라 배달 중 식감 손실이 적다.",
    },
    {
        "brand_id": "kfc_chicken",
        "name": "KFC",
        "menu_name": "핫크리스피 치킨",
        "kind": "치킨",
        "category": "meat",
        "taste": ["chicken", "meat"],
        "order_url": "https://www.kfckorea.com/delivery/chicken",
        "channel": "KFC 딜리버리 · 치킨",
        "price_krw": 13000,
        "delivery_sensitivity": 0.7,
        "rating": 4.2,
        "tags": ["#크리스피"],
        "blurb": "치킨 카테고리로 바로 열린다. 1~2인분 시키기 편하다.",
    },
    # ── 피자 ──────────────────────────────────────────────
    {
        "brand_id": "dominos",
        "name": "도미노피자",
        "menu_name": "포테이토 피자",
        "kind": "피자",
        "category": "western",
        "taste": ["pizza", "western"],
        "order_url": "https://web.dominos.co.kr/order",
        "channel": "도미노 공식 주문",
        "price_krw": 25000,
        "delivery_sensitivity": 0.6,
        "rating": 4.4,
        "tags": ["#포테이토"],
        "blurb": "웹 주문 흐름이 가장 매끄럽다. 혼자면 라지 말고 미디엄.",
    },
    {
        "brand_id": "pizzahut",
        "name": "피자헛",
        "menu_name": "치즈 크러스트 피자",
        "kind": "피자",
        "category": "western",
        "taste": ["pizza", "western"],
        "order_url": "https://www.pizzahut.co.kr/order/step1",
        "channel": "피자헛 공식 주문",
        "price_krw": 24000,
        "delivery_sensitivity": 0.6,
        "rating": 4.2,
        "tags": ["#치즈_크러스트"],
        "blurb": "테두리까지 치즈. 식으면 눌리니 도착하면 바로 열자.",
    },
    {
        "brand_id": "pizzamaru",
        "name": "피자마루",
        "menu_name": "고구마 피자",
        "kind": "피자",
        "category": "western",
        "taste": ["pizza", "western"],
        "order_url": "https://www.pizzamaru.co.kr/orderchoice/?deliv_type=2",
        "channel": "피자마루 배달 주문",
        "price_krw": 14000,
        "delivery_sensitivity": 0.6,
        "rating": 4.0,
        "tags": ["#가성비_피자"],
        "blurb": "가격대가 낮다. 배달 주문 화면으로 바로 들어간다.",
    },
    {
        "brand_id": "banolim",
        "name": "반올림피자",
        "menu_name": "반올림 콤비네이션",
        "kind": "피자",
        "category": "western",
        "taste": ["pizza", "western"],
        "order_url": "https://order.banolimpizza.com/",
        "channel": "반올림 주문 사이트",
        "price_krw": 17000,
        "delivery_sensitivity": 0.6,
        "rating": 4.1,
        "tags": ["#콤비네이션"],
        "blurb": "주문 전용 사이트가 따로 있어서 진입이 빠르다.",
    },
    {
        "brand_id": "mrpizza",
        "name": "미스터피자",
        "menu_name": "골드 크러스트 피자",
        "kind": "피자",
        "category": "western",
        "taste": ["pizza", "western"],
        "order_url": "https://www.mrpizza.co.kr/order",
        "channel": "미스터피자 공식 주문",
        "price_krw": 23000,
        "delivery_sensitivity": 0.6,
        "rating": 4.0,
        "tags": ["#씬_크러스트"],
        "blurb": "도우가 얇다. 두꺼운 피자에 물렸을 때.",
    },
    # ── 버거 ──────────────────────────────────────────────
    {
        "brand_id": "burgerking",
        "name": "버거킹",
        "menu_name": "와퍼 세트",
        "kind": "버거",
        "category": "western",
        "taste": ["burger", "western", "meat"],
        "order_url": "https://www.burgerking.co.kr/delivery",
        "channel": "버거킹 딜리버리",
        "price_krw": 12000,
        "delivery_sensitivity": 0.8,
        "rating": 4.2,
        "tags": ["#직화_패티"],
        "blurb": "패티는 버티지만 프라이는 금방 죽는다. 가까울 때 유리.",
    },
    {
        "brand_id": "kfc_burger",
        "name": "KFC",
        "menu_name": "징거버거 세트",
        "kind": "버거",
        "category": "western",
        "taste": ["burger", "western"],
        "order_url": "https://www.kfckorea.com/delivery/burger",
        "channel": "KFC 딜리버리 · 버거",
        "price_krw": 11000,
        "delivery_sensitivity": 0.8,
        "rating": 4.1,
        "tags": ["#징거"],
        "blurb": "버거 카테고리로 바로 열린다. 혼자 먹기 딱.",
    },
    {
        "brand_id": "lotteria",
        "name": "롯데리아",
        "menu_name": "불고기버거 세트",
        "kind": "버거",
        "category": "western",
        "taste": ["burger", "western"],
        "order_url": "https://www.lotteeatz.com/",
        "channel": "롯데잇츠 주문",
        "price_krw": 10000,
        "delivery_sensitivity": 0.8,
        "rating": 3.9,
        "tags": ["#불고기버거"],
        "blurb": "가격이 가장 낮은 편. 롯데잇츠에서 매장을 고르면 된다.",
    },
    # ── 한식·도시락 ────────────────────────────────────────
    {
        "brand_id": "hansot",
        "name": "한솥도시락",
        "menu_name": "치킨마요 덮밥",
        "kind": "도시락",
        "category": "korean",
        "taste": ["korean", "mild"],
        "order_url": "https://www.hsd.co.kr/menu/menu_order",
        "channel": "한솥 주문",
        "price_krw": 6000,
        "delivery_sensitivity": 0.4,
        "rating": 4.1,
        "tags": ["#한_끼_해결"],
        "blurb": "가장 저렴하게 한 끼. 밥류라 배달에 강하다.",
    },
    # ── 베이커리 ──────────────────────────────────────────
    {
        "brand_id": "paris",
        "name": "파리바게뜨",
        "menu_name": "샌드위치 · 베이커리",
        "kind": "베이커리",
        "category": "cafe",
        "taste": ["mild"],
        "order_url": "https://www.paris.co.kr/order/delivery/",
        "channel": "파리바게뜨 딜리버리",
        "price_krw": 9000,
        "delivery_sensitivity": 0.3,
        "rating": 4.0,
        "tags": ["#가볍게"],
        "blurb": "밥 생각 없을 때. 배달 중 상태 변화가 거의 없다.",
    },
]

_BY_MENU_ID: dict[str, dict] = {}


def _place(brand: dict, taste: list[str]) -> dict:
    """브랜드를 엔진이 다루는 place 형태로 변환."""
    keys = set(brand.get("taste") or ())
    return {
        "place_id": f"brand:{brand['brand_id']}",
        "menu_id": f"brand:{brand['brand_id']}",
        "brand_id": brand["brand_id"],
        "name": brand["name"],
        "menu_name": brand["menu_name"],
        "kind": brand["kind"],
        "category": brand["category"],
        "tags": list(brand.get("tags") or []),
        "rating": float(brand.get("rating", 4.0)),
        "price_krw": int(brand["price_krw"]),
        "delivery_sensitivity": float(brand["delivery_sensitivity"]),
        "blurb": brand.get("blurb", ""),
        "order_url": brand["order_url"],
        "channel": brand["channel"],
        "hours": "매장별 영업시간 상이",
        "source": "brand",
        "is_brand": True,
        # 프랜차이즈는 전국 배달이 전제 — 반경·영업 여부로 거를 대상이 아니다.
        "open_now": True,
        "delivery_available": True,
        "taste_match": bool(keys & set(taste or ())),
    }


def brand_places(taste: list[str] | None = None) -> list[dict]:
    return [_place(b, list(taste or [])) for b in BRANDS]


def find_brand_place(menu_id: str) -> dict | None:
    if not _BY_MENU_ID:
        for b in BRANDS:
            _BY_MENU_ID[f"brand:{b['brand_id']}"] = b
    brand = _BY_MENU_ID.get(str(menu_id))
    if not brand:
        return None
    return copy.deepcopy(_place(brand, []))


def brand_count() -> int:
    return len(BRANDS)
