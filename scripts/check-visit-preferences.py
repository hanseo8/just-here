"""Regression: explicit dish searches and user-selected visit radius."""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app import kakao,engine
from app.main import SessionStartBody
from pydantic import ValidationError

def doc(pid,name,delta=0):
    return dict(id=pid,place_name=name,category_name='음식점 > 한식',x='126.645',y=str(37.3925+delta),address_name='test')

def search(lat,lng,radius,queries,per_query):
    assert '비빔밥' in queries
    # Broad query finishes first: a duplicate must retain later exact evidence.
    return [('한식',[doc('a','밥집'),doc('b','다른 한식집')]),('비빔밥',[doc('a','밥집')])]
with patch.object(kakao,'_keyword_search',side_effect=search):
    places=kakao.fetch_by_taste(37.3925,126.645,3000,['bibimbap'])
assert places[0]['matched_tastes']==['bibimbap']
assert places[1]['matched_tastes']==[]
assert kakao.DISH_QUERIES['bibimbap']==['비빔밥']
assert kakao.DISH_QUERIES['gukbap']==['국밥']
far=dict(places[0],place_id='far',menu_id='far',lat=37.4105)
with patch.object(engine,'_fetch_kakao_block',return_value=(places+[far],[])) as fetch, patch.object(engine,'google_place_photo_fields',return_value={}), patch.object(engine,'_attach_verified_visit_menus',side_effect=lambda s,c:c):
    for radius,expected in [(100,1),(700,1),(3000,2)]:
        session=engine.create_session(37.3925,126.645,'visit','rain',['bibimbap'],visit_radius_m=radius)
        cards,r,_=engine.build_visit_cards(session)
        assert len(cards)==expected,(radius,cards)
        assert r==radius and all(c['distance_m']<=radius for c in cards)
        assert all('bibimbap' in c['matched_tastes'] for c in cards)
        engine.reanchor_session(session,37.3935,126.645)
        assert fetch.call_args.args[2]==radius
    session.taste=['gukbap']
    assert engine.build_visit_cards(session)[0]==[]
assert SessionStartBody(lat=0,lng=0).visit_radius_m==700
for radius in [99,3001]:
    try: SessionStartBody(lat=0,lng=0,visit_radius_m=radius)
    except ValidationError: pass
    else: raise AssertionError(radius)
print('PASS: exact dish evidence, duplicate query ordering, no unrelated fallback, 100/700/3000m, reanchor, API bounds')
