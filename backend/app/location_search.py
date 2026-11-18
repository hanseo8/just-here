"""Short-lived location lookup. No query persistence or client-visible API key.

Official API: https://developers.kakao.com/docs/ko/local/dev-guide
"""
import math
import os
import httpx


def search(query: str) -> list[dict]:
    key = (os.getenv('KAKAO_REST_API_KEY') or '').strip()
    if not key:
        raise RuntimeError('location_unavailable')
    results, seen, succeeded = [], set(), False
    # Addresses include neighbourhoods; keywords cover stations and landmarks.
    with httpx.Client(timeout=4.0, follow_redirects=False, trust_env=False) as client:
        for kind in ('address', 'keyword'):
            try:
                response = client.get('https://dapi.kakao.com/v2/local/search/' + kind + '.json',
                    headers={'Authorization': 'KakaoAK ' + key}, params={'query': query, 'size': 5})
                response.raise_for_status()
                docs = response.json().get('documents', [])
                if not isinstance(docs, list):
                    continue
                succeeded = True
                for doc in docs[:5]:
                    if not isinstance(doc, dict):
                        continue
                    try:
                        lat, lng = float(doc.get('y')), float(doc.get('x'))
                    except (ValueError, TypeError):
                        continue
                    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
                        continue
                    address = doc.get('road_address_name') or doc.get('address_name') or ''
                    name = doc.get('place_name') or doc.get('address_name') or address
                    if not isinstance(name, str) or not name.strip():
                        continue
                    marker = (round(lat, 5), round(lng, 5), name)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    results.append({'name': name[:100], 'address': str(address)[:180], 'lat': lat, 'lng': lng})
            except (httpx.HTTPError, ValueError, AttributeError):
                continue
    if not succeeded:
        raise RuntimeError('location_unavailable')
    return results[:8]
