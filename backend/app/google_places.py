"""Google Places 사진 파일럿.

카카오에서 확인한 지점을 Google Places의 현재 사진과 느슨하게 연결한다.
사진 이름·바이트는 저장하지 않고 요청 시 다시 조회한다. API 키는 서버에서만
사용하며, 이름/주소/좌표가 맞지 않으면 사진을 붙이지 않는다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
from urllib.parse import quote

import httpx

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PHOTO_URL = "https://places.googleapis.com/v1/{photo_name}/media"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.photos,places.googleMapsUri"
)


def enabled() -> bool:
    return (
        (os.getenv("GOOGLE_PLACES_PHOTOS") or "").strip().lower() in {"1", "on", "true", "yes"}
        and bool((os.getenv("GOOGLE_MAPS_API_KEY") or "").strip())
    )


def _key() -> str:
    return (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()


def _signing_key() -> bytes:
    raw = (os.getenv("GUEST_SIGNING_SECRET") or _key() or "just-here-google-photo").encode()
    return raw


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _token(place: dict) -> str:
    payload = {
        "place_id": str(place.get("place_id") or "")[:120],
        "name": str(place.get("name") or "")[:160],
        "address": str(place.get("address") or "")[:240],
        "lat": round(float(place.get("lat")), 6),
        "lng": round(float(place.get("lng")), 6),
    }
    encoded = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    signature = hmac.new(_signing_key(), encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_b64(signature)}"


def _verify_token(token: str) -> dict | None:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(_signing_key(), encoded.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        value = json.loads(_unb64(encoded).decode())
        if not isinstance(value, dict) or not value.get("name"):
            return None
        float(value["lat"])
        float(value["lng"])
        return value
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def photo_urls(place: dict) -> dict:
    """카드에 넣을 지연 조회 URL. API가 꺼져 있으면 빈 값이다."""
    if not enabled() or place.get("source") != "kakao":
        return {}
    if str(place.get("image_url") or "").strip():
        return {}
    if not place.get("name") or place.get("lat") is None or place.get("lng") is None:
        return {}
    token = _token(place)
    encoded = quote(token, safe="")
    maps_query = quote(
        " ".join(part for part in [str(place.get("name") or ""), str(place.get("address") or "")] if part),
        safe="",
    )
    return {
        "image_url": f"/v1/google/place-photo?token={encoded}",
        "photo_meta_url": f"/v1/google/place-photo/meta?token={encoded}",
        "photo_role": "store",
        "photo_source": "google_places",
        "photo_attribution": "Google 지도 사진",
        "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={maps_query}",
        "photo_is_example": False,
        "has_photo": True,
    }


def verify_token(token: str) -> dict | None:
    return _verify_token(token)


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _distance_m(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, h)))


def _display_name(item: dict) -> str:
    return str((item.get("displayName") or {}).get("text") or "")


def _matches(place: dict, item: dict) -> bool:
    name = _norm(place.get("name") or "")
    candidate = _norm(_display_name(item))
    if not name or not candidate or (name not in candidate and candidate not in name):
        return False
    loc = item.get("location") or {}
    try:
        distance = _distance_m(
            float(place["lat"]),
            float(place["lng"]),
            float(loc["latitude"]),
            float(loc["longitude"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return distance <= 250


def _search(place: dict) -> dict | None:
    address = str(place.get("address") or "").strip()
    query = " ".join(part for part in [str(place.get("name") or "").strip(), address] if part)
    body = {
        "textQuery": query,
        "languageCode": "ko",
        "regionCode": "KR",
        "pageSize": 5,
        "locationBias": {
            "circle": {
                "center": {"latitude": float(place["lat"]), "longitude": float(place["lng"])},
                "radius": 250,
            }
        },
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(
                SEARCH_URL,
                headers={"X-Goog-Api-Key": _key(), "X-Goog-FieldMask": FIELD_MASK},
                json=body,
            )
            response.raise_for_status()
            for item in response.json().get("places", []):
                if _matches(place, item):
                    return item
    except (httpx.HTTPError, ValueError, TypeError):
        return None
    return None


def fetch_photo(token: str) -> tuple[bytes, str] | None:
    place = verify_token(token)
    if not place or not enabled():
        return None
    matched = _search(place)
    photos = (matched or {}).get("photos") or []
    photo_name = str((photos[0] if photos else {}).get("name") or "")
    if not photo_name.startswith("places/"):
        return None
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(
                PHOTO_URL.format(photo_name=photo_name),
                params={"maxWidthPx": 1200},
                headers={"X-Goog-Api-Key": _key()},
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
            if not content_type.startswith("image/"):
                return None
            return response.content, content_type
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def metadata(token: str) -> dict | None:
    place = verify_token(token)
    if not place or not enabled():
        return None
    matched = _search(place)
    if not matched:
        return None
    photos = (matched.get("photos") or [])
    if not photos:
        return None
    attributions = []
    for item in photos[0].get("authorAttributions") or []:
        name = str(item.get("displayName") or "").strip()
        uri = str(item.get("uri") or "").strip()
        if name:
            attributions.append({"name": name, "uri": uri})
    return {
        "ok": True,
        "source": "Google Places",
        "attributions": attributions,
        "google_maps_url": matched.get("googleMapsUri") or "",
        "place_name": _display_name(matched),
    }
