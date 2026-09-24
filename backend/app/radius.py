"""거리·스마트 반경·의도 제안 (MVP 룰베이스)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Literal

Intent = Literal["visit", "delivery"]
Weather = Literal["clear", "rain", "snow", "hot", "cold"]

KST = timezone(timedelta(hours=9))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def session_radius_m(intent: Intent, weather: Weather) -> int:
    """세션 후보 풀 상한 반경."""
    if intent == "visit":
        return 700  # 방문은 항상 700m 이내
    # delivery: 2–3km
    if weather in ("rain", "snow"):
        return 2000
    return 3000


def card_radius_m(
    intent: Intent,
    weather: Weather,
    delivery_sensitivity: float,
) -> int:
    """개별 메뉴 노출 허용 반경."""
    base = session_radius_m(intent, weather)
    if intent == "visit":
        return base
    # 배달: 민감도 높을수록 2km 쪽으로 축소 (하한 2km)
    sens = max(0.0, min(1.0, delivery_sensitivity))
    radius = int(base * (1.0 - 0.25 * sens))
    return max(2000, min(radius, base))


def walk_minutes(distance_m: float) -> int:
    # ≈ 80m/분
    return max(1, int(round(distance_m / 80.0)))


def delivery_eta_minutes(distance_m: float) -> int:
    """조리~도착 러프 ETA. 기본 15분 + 거리(≈250m/분 이륜)."""
    return max(20, 15 + int(round(distance_m / 250.0)))


def suggest_intent(weather: Weather, hour: int | None = None) -> Intent:
    """스마트 토글 초기값.

    - 우천/눈 또는 야간(22시~05시) → 배달
    - 맑은 점심(11–14) / 저녁 피크(17–21) → 방문
    - 그 외 주간 맑음 → 방문
    """
    if hour is None:
        hour = datetime.now(KST).hour
    hour = int(hour) % 24

    if weather in ("rain", "snow") or hour >= 22 or hour < 6:
        return "delivery"
    if weather == "clear" and (11 <= hour <= 14 or 17 <= hour <= 21):
        return "visit"
    if weather in ("hot", "cold") and (hour >= 22 or hour < 6):
        return "delivery"
    return "visit"


MealContext = Literal["meal", "late_night", "anju"]


def suggest_meal_context(hour: int | None = None) -> MealContext:
    """시간 힌트. 사용자 선택을 바꾸지 않는다."""
    if hour is None:
        hour = datetime.now(KST).hour
    hour = int(hour) % 24
    if hour >= 22 or hour < 6:
        return "late_night"
    return "meal"


def suggest_meal_reason(hour: int, suggested: MealContext) -> str:
    if suggested == "late_night":
        return "늦은 시간이면 야식도 있어요. 고르지 않으면 한 끼로 시작해요."
    return ""


def suggest_intent_reason(weather: Weather, hour: int, intent: Intent) -> str:
    if weather in ("rain", "snow") and intent == "delivery":
        return "날씨 때문에 배달로 맞춰 뒀어요"
    if (hour >= 22 or hour < 6) and intent == "delivery":
        return "늦은 시간이라 배달로 맞춰 뒀어요"
    if intent == "visit" and (11 <= hour <= 14 or 17 <= hour <= 21):
        return "피크 타임, 근처 방문으로 맞춰 뒀어요"
    return "지금 상황에 맞춰 골랐어요"
