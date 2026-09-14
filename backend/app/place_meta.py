"""카드 상세·가격대·배달 민감도 카피."""
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
    if s >= 0.85:
        level = "매우 높음"
        tip = "식으면 맛이 확 떨어져요. 방문하거나 가까운 배달을 추천해요."
    elif s >= 0.65:
        level = "높음"
        tip = "배달 중 온도·식감 변화가 있어요. 도착 후 바로 먹는 게 좋아요."
    elif s >= 0.4:
        level = "보통"
        tip = "일반적인 배달 메뉴예요. 너무 멀지만 않으면 괜찮아요."
    else:
        level = "낮음"
        tip = "배달해도 맛·형태가 잘 유지되는 편이에요."
    return {
        "score": s,
        "percent": pct,
        "level": level,
        "tip": tip,
    }


def enrich_place_fields(place: dict) -> dict:
    """카드용 주소·가격·민감도 필드를 place에서 뽑아 반환."""
    source = place.get("source") or ("kakao" if str(place.get("place_id", "")).startswith("kakao") else "seed")
    if source == "kakao":
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
        "hours": place.get("hours") or "영업시간 확인",
        "rating": float(place.get("rating") or 4.0),
        "review": blurb,
    }
