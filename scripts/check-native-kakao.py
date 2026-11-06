"""No real Kakao login: prove binding, replay resistance and recovery in temp data."""
import hashlib
import html
import logging
import os
import re
import tempfile
import time
from urllib.parse import urlparse, parse_qs

with tempfile.TemporaryDirectory() as directory:
    os.environ.update(DATA_DIR=directory,GUEST_SIGNING_SECRET='native-test-secret',
                      KAKAO_REST_API_KEY='native-test-public-key',RECEIPT_REWARDS='off')
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app import native_auth, users
    c=TestClient(app)
    a=c.post('/v1/auth/guest',json={'device_id':'native-test-a'}).json()
    b=c.post('/v1/auth/guest',json={'device_id':'native-test-b'}).json()
    ah={'X-Guest-Token':a['guest_token']};bh={'X-Guest-Token':b['guest_token']}
    verifier='a'*64
    payload={'guest_uid':a['uid'],'challenge':hashlib.sha256(verifier.encode()).hexdigest()}
    route='/v1/auth/kakao/native/'
    assert c.post(route+'start',json=payload).status_code==401
    assert c.post(route+'start',json=payload,headers=bh).status_code==401
    assert c.post(route+'start',json={**payload,'challenge':'bad'},headers=ah).status_code==422
    calls=[]
    def exchange(code,redirect):
        assert redirect=='https://justthis.co.kr'
        calls.append(code)
        return {'kakao_id':4242,'nickname':'tester','access_token':'must-never-be-returned'}
    users.exchange_kakao_auth_code=exchange
    def begin(user,headers):
        data=c.post(route+'start',json={**payload,'guest_uid':user['uid']},headers=headers).json()
        state=parse_qs(urlparse(data['authorize_url']).query)['state'][0]
        assert 'guest_token' not in data['authorize_url'] and verifier not in data['authorize_url']
        return data,state
    data,state=begin(a,ah)
    response=c.get('/',params={'state':state,'code':'test-code'})
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.headers['referrer-policy']=='no-referrer'
    assert 'must-never-be-returned' not in response.text and a['guest_token'] not in response.text
    url=html.unescape(re.search(r'href="(justthis:[^"]+)"',response.text)[1])
    values={k:v[0] for k,v in parse_qs(urlparse(url).query).items()}
    assert set(values)=={'attempt_id','ticket'}
    assert c.get('/',params={'state':state,'code':'replay'}).status_code==200 and len(calls)==1
    complete={'guest_uid':a['uid'],'verifier':verifier,**values}
    assert c.post(route+'complete',json=complete).status_code==401
    assert c.post(route+'complete',json={**complete,'guest_uid':b['uid']},headers=bh).status_code==401
    assert c.post(route+'complete',json={**complete,'ticket':'x'*43},headers=ah).status_code==401
    assert c.post(route+'complete',json={**complete,'verifier':'x'*64},headers=ah).status_code==401
    linked=c.post(route+'complete',json=complete,headers=ah)
    assert linked.status_code==200 and linked.json()['uid']=='kakao_4242'
    first=users.STORE.get('kakao_4242')
    retry=c.post(route+'complete',json=complete,headers=ah)
    assert retry.status_code==200 and users.STORE.get('kakao_4242')==first
    data2,state2=begin(b,bh)
    response=c.get('/',params={'state':state2,'code':'new-device'})
    values2={k:v[0] for k,v in parse_qs(urlparse(html.unescape(re.search(r'href="(justthis:[^"]+)"',response.text)[1])).query).items()}
    recovered=c.post(route+'complete',json={'guest_uid':b['uid'],'verifier':verifier,**values2},headers=bh)
    assert recovered.status_code==200 and recovered.json()['uid']=='kakao_4242'
    data3,state3=begin(a,ah)
    with native_auth.database() as db: db.execute('UPDATE attempts SET expires=? WHERE id=?',(time.time()-1,data3['attempt_id']))
    before=len(calls)
    assert 'justthis://auth-complete' not in c.get('/',params={'state':state3,'code':'expired'}).text
    assert len(calls)==before
    _,state4=begin(a,ah)
    assert 'justthis://auth-complete' not in c.get('/',params={'state':state4,'error':'access_denied'}).text
    with native_auth.database() as db:
        raw=' '.join(str(tuple(row)) for row in db.execute('SELECT * FROM attempts'))
    assert 'must-never-be-returned' not in raw and verifier not in raw
    record=logging.LogRecord('uvicorn.access',20,'',1,'%s %s %s %s %s',('client','GET','/?code=secret&state=native_x','1.1',200),None)
    native_auth.OAuthLogFilter().filter(record)
    assert 'secret' not in record.args[2] and 'native_x' not in record.args[2]
    print('PASS: native OAuth guest/device proof, replay/expiry/cancellation, no token URL/storage, idempotent linking and fresh-device recovery')
