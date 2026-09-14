"""실날씨 — Open-Meteo (키 불필요)."""
from __future__ import annotations

from typing import Any, Literal

import httpx

Weather = Literal["clear", "rain", "snow", "hot", "cold"]

# WMO Weather interpretation codes → 우리 weather_flag
# https://open-meteo.com/en/docs
_RAIN = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
_SNOW = {71, 73, 75, 77, 85, 86}


def wmo_to_weather(code: int, temp_c: float | None = None) -> Weather:
    if code in _SNOW:
        return "snow"
    if code in _RAIN:
        return "rain"
    if temp_c is not None:
        if temp_c >= 30:
            return "hot"
        if temp_c <= 0:
            return "cold"
    return "clear"


def fetch_weather(lat: float, lng: float, timeout: float = 4.0) -> dict[str, Any]:
    """현재 좌표 날씨. 실패 시 clear 폴백."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "current": "temperature_2m,weather_code",
        "timezone": "Asia/Seoul",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.get(url, params=params)
            res.raise_for_status()
            data = res.json()
        cur = data.get("current") or {}
        code = int(cur.get("weather_code", 0))
        temp = cur.get("temperature_2m")
        temp_f = float(temp) if temp is not None else None
        flag = wmo_to_weather(code, temp_f)
        return {
            "weather": flag,
            "temp_c": temp_f,
            "wmo_code": code,
            "source": "open-meteo",
            "ok": True,
        }
    except Exception as exc:
        return {
            "weather": "clear",
            "temp_c": None,
            "wmo_code": None,
            "source": "fallback",
            "ok": False,
            "error": str(exc)[:120],
        }
