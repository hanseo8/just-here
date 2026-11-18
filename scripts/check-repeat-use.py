"""Recent selections reuse existing profile data; only isolated fixture accounts are touched."""
import json
import os
import tempfile
from datetime import datetime,timedelta,timezone

with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw,KAKAO_REST_API_KEY=' ',GOOGLE_PLACES_PHOTOS='off',GUEST_SIGNING_SECRET='repeat-fixture-only')
    from backend.app import users
    from backend.app.main import app
    from fastapi.testclient import TestClient
    now=datetime.now(timezone.utc)
    def entry(i,days=0,**more):
        return {'action':'lets_go','place_id':'kakao_'+str(i),'place_name':'fixture-A-'+str(i),'intent':'visit',
                'at':(now-timedelta(days=days,seconds=60)).strftime('%Y-%m-%dT%H:%M:%SZ'),**more}
    rows=[entry(1,3),entry(1,1),entry(2,2),entry(3,31),entry(4,-1),entry(5,action='nope'),
          entry(6,place_id='javascript:bad'),entry(7,at='invalid'),None,entry(8,at=12)]
    result=users.recent_choices(rows,now=now)
    assert len(result)==3 and result[0]['place_name']=='fixture-A-6'
    assert result[0]['map_url']==''
    assert result[1]['place_name']=='fixture-A-1'
    assert result[1]['map_url']=='https://map.kakao.com/link/map/1'
    assert len(users.recent_choices([entry(i) for i in range(20)],now=now))==5
    assert users.recent_choices([entry(9,intent='delivery')],now=now)[0]['map_url']==''
    assert users.recent_choices([entry(1,place_name='old'),entry(1,place_name='new')],now=now)[0]['place_name']=='new'

    client=TestClient(app)
    a=client.post('/v1/auth/guest',json={'device_id':'repeat-fixture-device-a'}).json()
    b=client.post('/v1/auth/guest',json={'device_id':'repeat-fixture-device-b'}).json()
    users.STORE.append_swipe(a['uid'],entry(123))
    users.STORE.set_taste(a['uid'],['bibimbap','pasta'])
    before=users.STORE.path.read_bytes()
    headers={'X-Guest-Token':a['guest_token']}
    response=client.get('/v1/me',params={'uid':a['uid']},headers=headers)
    assert response.status_code==200 and 'no-store' in response.headers['cache-control']
    profile=response.json()['user']
    assert profile['recent_choices'][0]['place_name']=='fixture-A-123'
    assert profile['preferences']['taste']==['bibimbap','pasta']
    assert 'swipe_logs' not in profile and users.STORE.path.read_bytes()==before
    assert client.get('/v1/me',params={'uid':a['uid']}).status_code==401
    assert client.get('/v1/me',params={'uid':b['uid']},headers=headers).status_code in (401,403)
    assert users.STORE.public_profile(b['uid'])['recent_choices']==[]
    reloaded=users.UserStore(users.STORE.path)
    assert reloaded.public_profile(a['uid'])['recent_choices'][0]['place_name']=='fixture-A-123'
    users.STORE.delete_profile(a['uid'])
    assert users.STORE.public_profile(a['uid']) is None
    assert 'fixture-A-123' not in users.STORE.path.read_text(encoding='utf-8')
print('PASS repeat use: bounded recent choices, newest deduplication, 30-day filter, valid map links only, private API/no-store, existing taste persistence, no extra writes, reload and isolated deletion')
