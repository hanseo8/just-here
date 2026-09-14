"""경험 티어: 송도 허브(풀) vs 전국 라이트."""
from __future__ import annotations

from typing import Literal

from .radius import haversine_m
from .seed import CENTER_LAT, CENTER_LNG

Tier = Literal["hub_full", "national_light"]

# 송도 국제도시 대략 커버 (센터에서 반경)
HUB_ID = "hub_songdo"
HUB_RADIUS_M = 4500


def resolve_tier(lat: float, lng: float) -> Tier:
    d = haversine_m(lat, lng, CENTER_LAT, CENTER_LNG)
    if d <= HUB_RADIUS_M:
        return "hub_full"
    return "national_light"


def tier_copy(tier: Tier) -> str:
    if tier == "hub_full":
        return "오늘 점심은 그냥여기 어때?"
    return "여기도 그냥여기 — 근처로 골라볼까?"


def tier_label(tier: Tier) -> str:
    if tier == "hub_full":
        return "송도 · 풀경험"
    return "전국 · 라이트"
