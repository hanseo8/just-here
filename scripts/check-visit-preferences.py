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

# Broad cuisine + explicit dish is an OR selection. Japanese matches must not
# disappear just because pasta is also selected.
mixed_places = [
    dict(places[0],id='j',place_id='j',name='스시집',place_name='스시집',matched_tastes=['japanese'],taste_match=True,lat=37.3925,lng=126.645),
    dict(places[0],id='p',place_id='p',name='파스타집',place_name='파스타집',matched_tastes=['pasta'],taste_match=True,lat=37.3926,lng=126.645),
    dict(places[0],id='x',place_id='x',name='무관한 집',place_name='무관한 집',matched_tastes=[],taste_match=False,lat=37.3927,lng=126.645),
]
with patch.object(engine,'_fetch_kakao_block',return_value=(mixed_places,[])), patch.object(engine,'google_place_photo_fields',return_value={}), patch.object(engine,'_attach_verified_visit_menus',side_effect=lambda s,c:c):
    mixed=engine.create_session(37.3925,126.645,'visit','clear',['japanese','pasta'],visit_radius_m=700)
    mixed_cards=engine.build_visit_cards(mixed)[0]
    assert {c['place_name'] for c in mixed_cards} == {'스시집','파스타집'}, mixed_cards

visit_opts=engine.adjust_options(mixed)
assert [o['id'] for o in visit_opts if o['id'] != 'deal'] == ['again','closer','retaste']
delivery=engine.create_session(37.3925,126.645,'delivery','clear',['pasta'])
delivery_opts=engine.adjust_options(delivery)
assert [o['id'] for o in delivery_opts if o['id'] != 'deal'] == ['again','retaste']
assert SessionStartBody(lat=0,lng=0).visit_radius_m==700
for radius in [99,3001]:
    try: SessionStartBody(lat=0,lng=0,visit_radius_m=radius)
    except ValidationError: pass
    else: raise AssertionError(radius)
print('PASS: exact dish evidence, mixed cuisine/dish OR, adjustment choices, 100/700/3000m, reanchor, API bounds')
