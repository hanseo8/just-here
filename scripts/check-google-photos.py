"""Google 장소 사진 파일럿의 네트워크 없는 계약 검사."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import google_places  # noqa: E402


def main() -> None:
    os.environ.pop("GOOGLE_PLACES_PHOTOS", None)
    os.environ.pop("GOOGLE_MAPS_API_KEY", None)
    place = {
        "source": "kakao",
        "place_id": "kakao_test",
        "name": "테스트 식당",
        "address": "인천 연수구 송도동",
        "lat": 37.3925,
        "lng": 126.6450,
    }
    assert google_places.photo_urls(place) == {}

    os.environ["GOOGLE_PLACES_PHOTOS"] = "on"
    os.environ["GOOGLE_MAPS_API_KEY"] = "test-only"
    fields = google_places.photo_urls(place)
    assert fields["photo_source"] == "google_places"
    assert fields["photo_role"] == "store"
    assert fields["image_url"].startswith("/v1/google/place-photo?token=")
    token = fields["image_url"].split("token=", 1)[1]
    decoded = google_places.verify_token(token)
    assert decoded and decoded["place_id"] == "kakao_test"
    assert google_places._matches(
        place,
        {
            "displayName": {"text": "테스트 식당"},
            "location": {"latitude": 37.3926, "longitude": 126.6451},
        },
    )
    assert not google_places._matches(
        place,
        {
            "displayName": {"text": "다른 식당"},
            "location": {"latitude": 37.3926, "longitude": 126.6451},
        },
    )
    print("google places photo contract: ok")


if __name__ == "__main__":
    main()
