"""Google 장소 사진 파일럿의 네트워크 없는 계약 검사."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch
import httpx
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
    assert google_places._query_variants(place) == ["테스트 식당 인천 연수구 송도동", "테스트 식당"]

    search_calls = []
    def search_handler(request):
        search_calls.append(request)
        query = request.read().decode("utf-8")
        if "송도동" in query:
            return httpx.Response(200, json={"places": []})
        return httpx.Response(200, json={"places": [{
            "id": "google_test",
            "displayName": {"text": "테스트식당"},
            "location": {"latitude": 37.3926, "longitude": 126.6451},
            "photos": [{"name": "places/test/photos/one"}],
        }]})
    factory = httpx.Client
    with patch.object(
        google_places.httpx,
        "Client",
        side_effect=lambda **kw: factory(transport=httpx.MockTransport(search_handler), **kw),
    ):
        found = google_places._search(place)
    assert found and found["id"] == "google_test"
    assert len(search_calls) == 2

    calls = []
    def handler(request):
        calls.append(request)
        if request.url.host == "places.googleapis.com":
            return httpx.Response(302, headers={"location": "https://lh3.googleusercontent.com/photo"})
        assert "x-goog-api-key" not in request.headers
        return httpx.Response(200, content=b"photo", headers={"content-type": "image/jpeg"})
    def client(**kwargs):
        return factory(transport=httpx.MockTransport(handler), **kwargs)
    matched = {"photos": [{"name": "places/test/photos/one"}]}
    with patch.object(google_places, "_search", return_value=matched), patch.object(google_places.httpx, "Client", side_effect=client):
        assert google_places.fetch_photo(token) == (b"photo", "image/jpeg")
    assert len(calls) == 2
    assert calls[0].headers["x-goog-api-key"] == "test-only"
    def rejected(request):
        return httpx.Response(302, headers={"location": "https://untrusted.example/photo"})
    with patch.object(google_places, "_search", return_value=matched), patch.object(google_places.httpx, "Client", side_effect=lambda **kw: factory(transport=httpx.MockTransport(rejected), **kw)):
        assert google_places.fetch_photo(token) is None
    print("google places photo contract: ok (redirect key isolation included)")


if __name__ == "__main__":
    main()
