"""Offline provider fixtures and isolated API tests; no production requests."""
import os
import tempfile
from unittest.mock import patch
import httpx

with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw, ADMIN_TOKEN='fixture', ADMIN_REQUIRE_2FA='off', ADMIN_TOTP_SECRET='',
                      KAKAO_REST_API_KEY='fixture-only', GOOGLE_PLACES_PHOTOS='off')
    from backend.app import location_search as search
    from backend.app.main import app
    from fastapi.testclient import TestClient

    calls=[]
    def respond(request):
        calls.append(request)
        assert request.headers['Authorization']=='KakaoAK fixture-only'
        assert request.url.host=='dapi.kakao.com' and request.url.params['size']=='5'
        return httpx.Response(200,json={'documents':[
            {'place_name':'강남역','address_name':'서울 강남구','y':'37.498','x':'127.028'},
            {'place_name':'강남역','address_name':'서울 강남구','y':'37.498','x':'127.028'},
            {'place_name':'bad','y':'nan','x':'127'}, {'place_name':'bad','y':'100','x':'127'},
            {'place_name':'bad','y':None,'x':'127'}]})
    real_client=httpx.Client
    with patch.object(search.httpx,'Client',side_effect=lambda **kw:real_client(transport=httpx.MockTransport(respond),**kw)):
        found=search.search('강남역')
    assert len(calls)==2 and len(found)==1 and found[0]['lat']==37.498
    with patch.dict(os.environ,KAKAO_REST_API_KEY=' '):
        try:search.search('강남역');raise AssertionError('missing key accepted')
        except RuntimeError:pass
    with patch.object(search.httpx,'Client',side_effect=lambda **kw:real_client(transport=httpx.MockTransport(lambda r:httpx.Response(503)),**kw)):
        try:search.search('강남역');raise AssertionError('upstream failure accepted')
        except RuntimeError:pass

    client=TestClient(app)
    with patch.object(search,'search',return_value=found) as provider:
        r=client.post('/v1/location/search',json={'query':' 강남역 '})
        assert r.status_code==200 and 'no-store' in r.headers['cache-control']
        assert r.json()['results'][0]['name']=='강남역' and 'fixture-only' not in r.text
        provider.assert_called_once_with('강남역')
        for query in ('a',' '*3,'x'*81,'ab\ncd'):
            assert client.post('/v1/location/search',json={'query':query}).status_code in (400,422)
    with patch.object(search,'search',return_value=[]):
        assert client.post('/v1/location/search',json={'query':'없는동네'}).json()['results']==[]
    with patch.object(search,'search',side_effect=RuntimeError('private provider detail')):
        r=client.post('/v1/location/search',json={'query':'강남역'})
        assert r.status_code==503 and 'private provider detail' not in r.text and 'no-store' in r.headers['cache-control']
    with patch.object(search,'search',return_value=[]):
        statuses=[client.post('/v1/location/search',json={'query':'강남역'}).status_code for _ in range(16)]
        assert 429 in statuses
print('PASS location search: address/landmark provider, duplicate/invalid coordinate filtering, isolated API, validation, no-store, no key disclosure, empty/error states and rate limit')
