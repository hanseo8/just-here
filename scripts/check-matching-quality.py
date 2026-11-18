"""Deterministic matching regression fixtures. No external search or real user data."""
import os
import tempfile
from unittest.mock import patch
import httpx

with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw,KAKAO_REST_API_KEY=' ',GOOGLE_MAPS_API_KEY='fixture-only',GOOGLE_PLACES_PHOTOS='off')
    from backend.app import google_places as g,kakao as k

    place={'name':'테스트식당 송도점','address':'인천 연수구 송도과학로 16','lat':37.39,'lng':126.64}
    def candidate(name=None,offset=0,address=None,photos=True,id='one'):
        return {'id':id,'displayName':{'text':name or place['name']},'formattedAddress':address or place['address'],
                'location':{'latitude':place['lat']+offset/111000,'longitude':place['lng']},
                'photos':[{'name':'places/test/photos/one'}] if photos else []}
    assert g._matches(place,candidate(offset=20))
    assert not g._matches(place,candidate(offset=180))
    assert not g._matches(place,candidate(offset=20,address='인천 연수구 송도과학로 18'))
    assert not g._matches(place,candidate(name='테스트식당 송도점2호점',offset=10))
    assert not g._matches({**place,'name':'테스트'},candidate(offset=10))
    assert not g._matches(place,{**candidate(),'location':{'latitude':float('nan'),'longitude':126.64}})
    # A missing branch suffix needs both a close coordinate and matching building address.
    assert g._matches(place,candidate(name='테스트식당',offset=20))
    assert not g._matches(place,candidate(name='테스트식당',offset=80))
    assert not g._matches(place,candidate(name='테스트식당',address='주소 없음'))
    factory=httpx.Client
    def run(items):
        def respond(request):
            assert request.headers['X-Goog-Api-Key']=='fixture-only'
            return httpx.Response(200,json={'places':items})
        with patch.object(g.httpx,'Client',side_effect=lambda **kw:factory(transport=httpx.MockTransport(respond),**kw)):
            return g._search(place)
    closest=candidate(offset=5,photos=False,id='closest-no-photo')
    wrong_photo=candidate(offset=100,photos=True,id='farther-with-photo')
    assert run([wrong_photo,closest])['id']=='closest-no-photo'
    assert run([candidate(offset=10,id='duplicate-a'),candidate(offset=15,id='duplicate-b')]) is None
    assert run([candidate(offset=250)]) is None

    from backend.app.verified_menus import apply_verified
    google_card={**place,'photo_source':'google_places','photo_meta_url':'/old-google-meta','photo_attribution':'old author'}
    row={'menu_id':'fixture-menu','menu_name':'확인 메뉴','menu_scope':'branch','branch_sale_confirmed':True,'menu_verified':True,
         'photo_url':'https://example.invalid/approved.jpg','photo_rights':True,'photo_is_store_menu':True}
    overlaid=apply_verified(google_card,row)
    assert overlaid['image_url']==row['photo_url'] and overlaid['photo_source']=='verified_menu'
    assert 'photo_meta_url' not in overlaid and 'photo_attribution' not in overlaid

    choices=['japanese','western','late_night']
    queries=k._taste_search_queries(choices)
    assert len(queries)<=6 and len(queries)==len(set(queries))
    assert all(set(queries)&set(k.TASTE_QUERIES[t]) for t in choices),queries
    assert set(k._taste_search_queries(['japanese','pasta']))&{'초밥'}
    assert '파스타' in k._taste_search_queries(['japanese','pasta'])
    assert k._taste_search_queries(['bibimbap'])==['비빔밥']
    assert k._taste_search_queries(['gukbap'])==['국밥']
    def keyword(lat,lng,radius,all_queries,per_query):
        return [(q,[{'id':str(i),'place_name':q+' 검증 식당','category_name':'음식점 > 한식','x':'126.64','y':'37.39'}]) for i,q in enumerate(all_queries)]
    with patch.object(k,'_keyword_search',side_effect=keyword):
        results=k.fetch_by_taste(37.39,126.64,700,choices)
    assert set(choices)<=set(t for row in results for t in row['matched_tastes'])
    print('PASS matching quality: branch/address/finite coordinates, distance bounds, ambiguous results rejected, nearest identity before photos, fair bounded multi-taste queries and dish-only queries')
