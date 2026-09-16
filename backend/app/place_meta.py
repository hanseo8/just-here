"""카드 상세·가격대·배달 시 맛 변화 카피."""
from __future__ import annotations


CATEGORY_PRICE_KRW = {
    "korean": 12000,
    "chinese": 11000,
    "japanese": 14000,
    "noodle": 10000,
    "meat": 22000,
    "western": 18000,
    "cafe": 7000,
}


def estimated_price_krw(place: dict) -> int:
    if isinstance(place.get("estimated_price_per_person"), (int, float)):
        return int(place["estimated_price_per_person"])
    if isinstance(place.get("price_krw"), (int, float)):
        return int(place["price_krw"])
    cat = place.get("category") or "korean"
    return CATEGORY_PRICE_KRW.get(cat, 12000)


def price_band_label(price: int) -> str:
    if price < 8000:
        return "1만원 미만"
    if price < 15000:
        return "1~1.5만원"
    if price < 25000:
        return "1.5~2.5만원"
    if price < 40000:
        return "2.5~4만원"
    return "4만원+"


def sensitivity_meta(score: float) -> dict:
    s = max(0.0, min(1.0, float(score or 0)))
    pct = int(round(s * 100))
    # 배달 거리를 우리가 알 수 없으므로 "가까우면 괜찮다" 같은 말은 쓰지 않는다
    if s >= 0.85:
        level = "많이 변해요"
        tip = "식으면 맛이 확 떨어져요. 도착하면 바로 드세요."
    elif s >= 0.65:
        level = "조금 변해요"
        tip = "온도나 식감이 달라질 수 있어요. 도착하면 바로 드세요."
    elif s >= 0.4:
        level = "무난해요"
        tip = "배달해도 크게 무리는 없는 편이에요."
    else:
        level = "잘 유지돼요"
        tip = "식어도 맛·형태가 잘 남는 편이에요."
    return {
        "score": s,
        "percent": pct,
        "level": level,
        "tip": tip,
    }


def enrich_place_fields(place: dict) -> dict:
    """카드용 주소·가격·민감도 필드를 place에서 뽑아 반환."""
    source = place.get("source") or ("kakao" if str(place.get("place_id", "")).startswith("kakao") else "seed")
    if source == "brand":
        # 프랜차이즈는 특정 지점이 아니다 — 주소를 만들어 붙이면 거짓말이 된다
        address = ""
        blurb = place.get("blurb") or ""
    elif source == "kakao":
        address = (
            place.get("address")
            or place.get("road_address")
            or place.get("review")
            or "주소 확인 중"
        )
        blurb = place.get("blurb") or place.get("menu_name") or "근처 실상호"
    else:
        address = place.get("address") or "인천 연수구 송도 인근"
        blurb = place.get("blurb") or place.get("review") or ""

    price = estimated_price_krw(place)
    sens = sensitivity_meta(place.get("delivery_sensitivity", 0.5))
    return {
        "address": address,
        "price_krw": price,
        "price_band": place.get("price_band") or price_band_label(price),
        "delivery_sensitivity": sens["score"],
        "sensitivity_level": sens["level"],
        "sensitivity_percent": sens["percent"],
        "sensitivity_tip": sens["tip"],
        "hours": place.get("hours") or "카카오맵에서 확인",
        "rating": float(place.get("rating") or 4.0),
        "review": blurb,
    }
