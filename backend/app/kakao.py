"""카카오 로컬 API — 주변 실음식점."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KAKAO_CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
CATEGORY_FOOD = "FD6"

# 카카오 카테고리명 → 내부 category
CATEGORY_MAP = [
    (("중식", "중국", "짜장", "짬뽕"), "chinese"),
    (("일식", "초밥", "라멘", "돈가스", "스시"), "japanese"),
    (("양식", "피자", "파스타", "햄버거"), "western"),
    (("카페", "디저트", "베이커리", "커피"), "cafe"),
    (("면", "국수", "우동", "냉면"), "noodle"),
    (("고기", "삼겹", "갈비", "고기구이", "족발", "보쌈"), "meat"),
    (("치킨", "닭"), "meat"),
    (("분식", "김밥", "떡볶이"), "korean"),
    (("한식", "국밥", "찌개", "백반", "정식"), "korean"),
]

CATEGORY_SENSITIVITY = {
    "chinese": 0.7,
    "japanese": 0.65,
    "western": 0.45,
    "cafe": 0.2,
    "noodle": 0.6,
    "meat": 0.55,
    "korean": 0.55,
}

# 취향 튜토리얼 키 → 키워드 검색어 + 내부 카테고리
TASTE_QUERIES: dict[str, list[str]] = {
    "jjajang": ["짜장면", "중식"],
    "jjamppong": ["짬뽕", "중식"],
    "sundaeguk": ["순대국", "국밥"],
    "gukbap": ["국밥", "한식"],
    "bibimbap": ["비빔밥", "한식"],
    "tteokbokki": ["떡볶이", "분식"],
    "kalguksu": ["칼국수", "국수"],
    "naengmyeon": ["냉면", "국수"],
    "ramen": ["라멘", "일식"],
    "sushi": ["초밥", "스시"],
    "donkatsu": ["돈가스", "일식"],
    "udon": ["우동", "일식"],
    "pork": ["삼겹살", "고기구이"],
    "galbi": ["갈비", "고기구이"],
    "chicken": ["치킨", "닭"],
    "pizza": ["피자", "양식"],
    "pasta": ["파스타", "양식"],
    "burger": ["햄버거", "양식"],
}

TASTE_CATEGORY: dict[str, str] = {
    "jjajang": "chinese",
    "jjamppong": "chinese",
    "sundaeguk": "korean",
    "gukbap": "korean",
    "bibimbap": "korean",
    "tteokbokki": "korean",
    "kalguksu": "noodle",
    "naengmyeon": "noodle",
    "ramen": "japanese",
    "sushi": "japanese",
    "donkatsu": "japanese",
    "udon": "japanese",
    "pork": "meat",
    "galbi": "meat",
    "chicken": "meat",
    "pizza": "western",
    "pasta": "western",
    "burger": "western",
}

# 취향과 별도로 항상 돌려서 카테고리 다양성 확보
DIVERSITY_QUERIES = ["한식", "일식", "중식", "양식", "치킨", "분식", "국밥", "카페"]


def kakao_configured() -> bool:
    return bool(os.getenv("KAKAO_REST_API_KEY", "").strip())


def _map_category(category_name: str) -> str:
    for keys, cat in CATEGORY_MAP:
        if any(k in category_name for k in keys):
            return cat
    return "korean"


def _placeholder_image(seed: str) -> str:
    h = abs(hash(seed)) % 1000
    return f"https://picsum.photos/seed/justhere{h}/800/1200"


def _doc_to_place(doc: dict, i: int = 0, tag: str = "#근처_실상호") -> dict:
    name = doc.get("place_name") or "근처 식당"
    cat_name = doc.get("category_name") or "음식점"
    short = cat_name.split(">")[-1].strip() if ">" in cat_name else cat_name
    internal = _map_category(cat_name)
    pid = doc.get("id") or f"kakao-{i}-{name}"
    return {
        "place_id": f"kakao_{pid}",
        "name": name,
        "lat": float(doc["y"]),
        "lng": float(doc["x"]),
        "menu_id": f"kakao_m_{pid}",
        "menu_name": short or "추천 메뉴",
        "image_url": _placeholder_image(str(pid)),
        "tags": [tag],
        "category": internal,
        "kakao_category": cat_name,
        "delivery_sensitivity": CATEGORY_SENSITIVITY.get(internal, 0.5),
        "temp_hold": 0.5,
        "texture_hold": 0.5,
        "open_now": True,
        "delivery_available": True,
        "rating": 4.0,
        "hours": "영업정보 확인",
        "review": doc.get("road_address_name") or doc.get("address_name") or "",
        "source": "kakao",
        "tier": "national_light",
        "kakao_url": doc.get("place_url") or "",
        "taste_match": False,
    }


def _headers() -> dict[str, str]:
    key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    return {"Authorization": f"KakaoAK {key}"}


def _get_with_client(client: httpx.Client, url: str, params: dict) -> list[dict]:
    res = client.get(url, headers=_headers(), params=params)
    if res.status_code == 403:
        raise RuntimeError("Kakao Local 403: 제품 설정 > 카카오맵 > 활성화 ON 필요")
    res.raise_for_status()
    return res.json().get("documents", [])


def _get(url: str, params: dict) -> list[dict]:
    if not kakao_configured():
        return []
    with httpx.Client(timeout=5.0) as client:
        return _get_with_client(client, url, params)


def fetch_nearby_places(lat: float, lng: float, radius_m: int, limit: int = 30) -> list[dict]:
    """주변 음식점 (카테고리 FD6, 최대 2페이지)."""
    if not kakao_configured():
        return []
    pages = min(2, max(1, (limit + 14) // 15))
    docs: list[dict] = []
    seen: set[str] = set()

    def page(p: int) -> list[dict]:
        try:
            return _get(
                KAKAO_CATEGORY_URL,
                {
                    "category_group_code": CATEGORY_FOOD,
                    "x": str(lng),
                    "y": str(lat),
                    "radius": min(int(radius_m), 20000),
                    "size": 15,
                    "page": p,
                    "sort": "distance",
                },
            )
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=pages) as pool:
        futures = [pool.submit(page, p) for p in range(1, pages + 1)]
        for fut in as_completed(futures):
            for d in fut.result():
                pid = d.get("id") or ""
                if pid and pid in seen:
                    continue
                if pid:
                    seen.add(pid)
                docs.append(d)

    return [_doc_to_place(d, i, "#근처_실상호") for i, d in enumerate(docs[:limit])]


def _keyword_search(
    lat: float, lng: float, radius_m: int, queries: list[str], per_query: int = 8
) -> list[tuple[str, list[dict]]]:
    """키워드 검색 병렬. (query, docs) 목록."""
    if not queries or not kakao_configured():
        return []

    def one(q: str) -> tuple[str, list[dict]]:
        try:
            docs = _get(
                KAKAO_KEYWORD_URL,
                {
                    "query": q,
                    "x": str(lng),
                    "y": str(lat),
                    "radius": min(int(radius_m), 20000),
                    "size": min(per_query, 15),
                    "sort": "distance",
                },
            )
            return q, docs
        except Exception:
            return q, []

    out: list[tuple[str, list[dict]]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(queries))) as pool:
        futures = [pool.submit(one, q) for q in queries]
        for fut in as_completed(futures):
            out.append(fut.result())
    return out


def fetch_by_taste(
    lat: float, lng: float, radius_m: int, taste: list[str], per_query: int = 8
) -> list[dict]:
    """취향 키워드 + 다양성 키워드로 주변 검색."""
    queries: list[str] = []
    for t in taste:
        queries.extend(TASTE_QUERIES.get(t, []))
    uniq_taste = list(dict.fromkeys(queries))[:6]
    # 다양성 쿼리는 취향과 겹치지 않는 것만
    taste_set = set(uniq_taste)
    diversity = [q for q in DIVERSITY_QUERIES if q not in taste_set][:6]
    all_q = uniq_taste + diversity
    if not all_q:
        all_q = list(DIVERSITY_QUERIES)

    taste_q_set = set(uniq_taste)
    seen_ids: set[str] = set()
    out: list[dict] = []

    for q, docs in _keyword_search(lat, lng, radius_m, all_q, per_query):
        is_taste = q in taste_q_set
        for i, d in enumerate(docs):
            pid = d.get("id") or ""
            if not pid or pid in seen_ids:
                continue
            cat = d.get("category_name") or ""
            if "음식점" not in cat and "카페" not in cat:
                continue
            seen_ids.add(pid)
            tag = "#취향맞춤" if is_taste else "#근처_실상호"
            place = _doc_to_place(d, i, tag)
            place["taste_match"] = is_taste
            out.append(place)
    return out


def fetch_inventory_block(
    lat: float, lng: float, radius_m: int, taste: list[str]
) -> tuple[list[dict], list[dict]]:
    """취향·다양성 + 일반 주변을 병렬로 한 번에."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_taste = pool.submit(fetch_by_taste, lat, lng, radius_m, taste)
        f_near = pool.submit(fetch_nearby_places, lat, lng, radius_m, 30)
        return f_taste.result(), f_near.result()
