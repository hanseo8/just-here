"""송도 인근 더미 시드 (MVP 테스트용).

좌표는 송도 앵커 기준 상대 오프셋.
세션 시 유저 실시간 GPS로 재배치됨.
"""
from __future__ import annotations

import random

# 송도 센트럴파크·컨벤시아 인근
CENTER_LAT = 37.3925
CENTER_LNG = 126.6450

# 대략적 오프셋: 0.001° ≈ 111m
PLACES: list[dict] = [
    {
        "place_id": "p01",
        "name": "송도 뚝배기집",
        "lat": 37.3930,
        "lng": 126.6455,
        "menu_id": "m01",
        "menu_name": "된장찌개",
        "image_url": "/static/example-photos/doenjang-jjigae.jpg",
        "tags": ["#스트레스_풀리는_국물"],
        "category": "korean",
        "delivery_sensitivity": 0.92,
        "temp_hold": 0.2,
        "texture_hold": 0.5,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.6,
        "hours": "11:00–21:00",
        "review": "뜨끈한 국물이 일품.",
    },
    {
        "place_id": "p02",
        "name": "바삭한하루 돈가스",
        "lat": 37.3918,
        "lng": 126.6440,
        "menu_id": "m02",
        "menu_name": "수제왕돈가스",
        "image_url": "https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=800&q=80",
        "tags": ["#바삭_본능"],
        "category": "japanese",
        "delivery_sensitivity": 0.95,
        "temp_hold": 0.3,
        "texture_hold": 0.1,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.4,
        "hours": "11:30–20:30",
        "review": "배달은 급히 먹어야 맛있음.",
    },
    {
        "place_id": "p03",
        "name": "센트럴 라멘",
        "lat": 37.3935,
        "lng": 126.6465,
        "menu_id": "m03",
        "menu_name": "돈코츠 라멘",
        "image_url": "https://images.unsplash.com/photo-1569718212165-3a8278d5f624?w=800&q=80",
        "tags": ["#면발_본능"],
        "category": "noodle",
        "delivery_sensitivity": 0.75,
        "temp_hold": 0.35,
        "texture_hold": 0.4,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.5,
        "hours": "11:00–22:00",
        "review": "국물 진하고 면 탄력 좋음.",
    },
    {
        "place_id": "p04",
        "name": "그냥김밥 송도",
        "lat": 37.3928,
        "lng": 126.6442,
        "menu_id": "m04",
        "menu_name": "참치김밥",
        "image_url": "https://images.unsplash.com/photo-1496116218417-1a781b1c416c?w=800&q=80",
        "tags": ["#빠른_한끼"],
        "category": "korean",
        "delivery_sensitivity": 0.25,
        "temp_hold": 0.7,
        "texture_hold": 0.8,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.2,
        "hours": "07:00–22:00",
        "review": "빠르게 해결하기 좋음.",
    },
    {
        "place_id": "p05",
        "name": "카페 송도브루",
        "lat": 37.3915,
        "lng": 126.6458,
        "menu_id": "m05",
        "menu_name": "아메리카노",
        "image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800&q=80",
        "tags": ["#각성_한잔"],
        "category": "cafe",
        "delivery_sensitivity": 0.15,
        "temp_hold": 0.5,
        "texture_hold": 0.9,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.3,
        "hours": "09:00–21:00",
        "review": "산미 적당한 원두.",
    },
    {
        "place_id": "p06",
        "name": "불티나 떡볶이",
        "lat": 37.3938,
        "lng": 126.6435,
        "menu_id": "m06",
        "menu_name": "매운떡볶이",
        "image_url": "https://images.unsplash.com/photo-1635363638580-c2809d049eee?w=800&q=80",
        "tags": ["#스트레스_풀리는_매운맛"],
        "category": "korean",
        "delivery_sensitivity": 0.55,
        "temp_hold": 0.45,
        "texture_hold": 0.5,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.7,
        "hours": "11:00–23:00",
        "review": "중독성 있는 매운맛.",
    },
    {
        "place_id": "p07",
        "name": "멀리있는집",
        "lat": 37.4050,
        "lng": 126.6600,
        "menu_id": "m07",
        "menu_name": "멀리있는 파스타",
        "image_url": "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=800&q=80",
        "tags": ["#테스트_원거리"],
        "category": "western",
        "delivery_sensitivity": 0.4,
        "temp_hold": 0.5,
        "texture_hold": 0.5,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.0,
        "hours": "11:00–21:00",
        "review": "반경 테스트용 (송도 앵커에서 멀음).",
    },
    {
        "place_id": "p08",
        "name": "소고기굽는날",
        "lat": 37.3920,
        "lng": 126.6468,
        "menu_id": "m08",
        "menu_name": "국산등심",
        "image_url": "https://images.unsplash.com/photo-1544025162-d76694265947?w=800&q=80",
        "tags": ["#고기_본능"],
        "category": "meat",
        "delivery_sensitivity": 0.7,
        "temp_hold": 0.4,
        "texture_hold": 0.35,
        "open_now": True,
        "delivery_available": False,
        "rating": 4.8,
        "hours": "12:00–22:00",
        "review": "방문 추천. 배달 거의 안 함.",
    },
    {
        "place_id": "p09",
        "name": "짬뽕제국 송도",
        "lat": 37.3940,
        "lng": 126.6448,
        "menu_id": "m09",
        "menu_name": "해물짬뽕",
        "image_url": "https://images.unsplash.com/photo-1582878826629-29b7ad1cdc43?w=800&q=80",
        "tags": ["#칼칼한_한그릇"],
        "category": "chinese",
        "delivery_sensitivity": 0.85,
        "temp_hold": 0.25,
        "texture_hold": 0.45,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.5,
        "hours": "10:30–21:30",
        "review": "국물 간 세고 해물 푸짐.",
    },
    {
        "place_id": "p10",
        "name": "송도 샐러드바",
        "lat": 37.3912,
        "lng": 126.6432,
        "menu_id": "m10",
        "menu_name": "치킨아보카도볼",
        "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80",
        "tags": ["#가벼운_선택"],
        "category": "western",
        "delivery_sensitivity": 0.35,
        "temp_hold": 0.6,
        "texture_hold": 0.55,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.1,
        "hours": "08:00–20:00",
        "review": "직장 점심용으로 무난.",
    },
]

# 인기 메뉴 풀 — 매 시작마다 카테고리가 다른 쌍으로 랜덤 샘플
TASTE_MENU_POOL = [
    {"key": "jjajang", "label": "짜장면", "category": "chinese", "image": "https://images.unsplash.com/photo-1582878826629-29b7ad1cdc43?w=600&q=80"},
    {"key": "jjamppong", "label": "짬뽕", "category": "chinese", "image": "https://images.unsplash.com/photo-1569718212165-3a8278d5f624?w=600&q=80"},
    {"key": "sundaeguk", "label": "순대국", "category": "korean", "image": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600&q=80"},
    {"key": "gukbap", "label": "국밥", "category": "korean", "image": "https://images.unsplash.com/photo-1476224203421-9ac39bcb3327?w=600&q=80"},
    {"key": "bibimbap", "label": "비빔밥", "category": "korean", "image": "https://images.unsplash.com/photo-1553163147-622ab57be1c7?w=600&q=80"},
    {"key": "tteokbokki", "label": "떡볶이", "category": "korean", "image": "https://images.unsplash.com/photo-1635363638580-c2809d049eee?w=600&q=80"},
    {"key": "kalguksu", "label": "칼국수", "category": "noodle", "image": "https://images.unsplash.com/photo-1569718212165-3a8278d5f624?w=600&q=80"},
    {"key": "naengmyeon", "label": "냉면", "category": "noodle", "image": "https://images.unsplash.com/photo-1455619452474-d2be8b1e70cd?w=600&q=80"},
    {"key": "ramen", "label": "라멘", "category": "japanese", "image": "https://images.unsplash.com/photo-1617093727343-374698b1b08d?w=600&q=80"},
    {"key": "sushi", "label": "초밥", "category": "japanese", "image": "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=600&q=80"},
    {"key": "donkatsu", "label": "돈가스", "category": "japanese", "image": "https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=600&q=80"},
    {"key": "udon", "label": "우동", "category": "japanese", "image": "https://images.unsplash.com/photo-1569718212165-3a8278d5f624?w=600&q=80"},
    {"key": "pork", "label": "삼겹살", "category": "meat", "image": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600&q=80"},
    {"key": "galbi", "label": "갈비", "category": "meat", "image": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600&q=80"},
    {"key": "chicken", "label": "치킨", "category": "meat", "image": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=600&q=80"},
    {"key": "pizza", "label": "피자", "category": "western", "image": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=600&q=80"},
    {"key": "pasta", "label": "파스타", "category": "western", "image": "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=600&q=80"},
    {"key": "burger", "label": "햄버거", "category": "western", "image": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=600&q=80"},
]


def sample_taste_pairs(n: int = 4) -> list[dict]:
    """인기 메뉴 풀에서 카테고리가 다른 A vs B 쌍을 n개 랜덤 추출."""
    pool = [dict(m) for m in TASTE_MENU_POOL]
    random.shuffle(pool)
    pairs: list[dict] = []
    used: set[str] = set()

    def pick_side(prefer_cat: str | None = None) -> dict | None:
        for m in pool:
            if m["key"] in used:
                continue
            if prefer_cat and m["category"] == prefer_cat:
                continue
            return m
        for m in pool:
            if m["key"] not in used:
                return m
        return None

    for i in range(n):
        left = pick_side()
        if not left:
            break
        used.add(left["key"])
        right = pick_side(prefer_cat=left["category"])
        if not right:
            used.discard(left["key"])
            break
        used.add(right["key"])
        # 좌우도 랜덤 스왑
        if random.random() < 0.5:
            left, right = right, left
        pairs.append(
            {
                "id": f"t{i + 1}",
                "prompt": "지금 더 끌리는 음식은?",
                "left": {"key": left["key"], "label": left["label"], "image": left["image"]},
                "right": {"key": right["key"], "label": right["label"], "image": right["image"]},
            }
        )
    return pairs


# 하위 호환: 고정 목록이 필요할 때 샘플 1회
TASTE_PAIRS = sample_taste_pairs(4)
