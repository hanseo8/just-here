"""Image abuse and bounded ASGI request checks. No production traffic."""
import asyncio
import io
import os
import struct
import zlib
from PIL import Image
from scripts.receipt_image_fixture import receipt_image
os.environ['GUEST_SIGNING_SECRET'] = 'upload-security-test-secret'
from backend.app import guest_token, rewards
from backend.app.request_guard import RequestGuard, WindowLimiter, MAX_UPLOAD_BODY
from backend.app import request_guard

for mime, fmt in [('image/jpeg','JPEG'), ('image/png','PNG'), ('image/webp','WEBP')]:
    assert rewards._valid_image_signature(mime, receipt_image('valid', fmt))
assert not rewards._valid_image_signature('image/jpeg', b'\xff\xd8\xfffake')
assert not rewards._valid_image_signature('image/jpeg', receipt_image('png','PNG'))
assert not rewards._valid_image_signature('image/jpeg', receipt_image('truncated')[:100])
def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
large = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',5000,4000,8,2,0,0,0))
assert not rewards._valid_image_signature('image/png',large)
animated = io.BytesIO()
Image.new('RGB',(16,16),'red').save(animated,format='WEBP',save_all=True,
    append_images=[Image.new('RGB',(16,16),'blue')],duration=100,loop=0)
assert not rewards._valid_image_signature('image/webp',animated.getvalue())
clock = [0.0]
limiter = WindowLimiter(capacity=2, clock=lambda: clock[0])
assert limiter.allow('a',2) and limiter.allow('a',2) and not limiter.allow('a',2)
assert limiter.allow('b',2) and not limiter.allow('c',2)
clock[0]=60.1
assert limiter.allow('c',2) and limiter.allow('a',2)

async def checks():
    invoked=[]
    async def downstream(scope,receive,send):
        invoked.append((await receive()).get('body'))
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
    async def request(headers, parts, guard=None):
        guard=guard or RequestGuard(downstream)
        sent=[]
        async def receive():
            return parts.pop(0)
        async def send(message): sent.append(message)
        await guard({'type':'http','path':'/v1/rewards/receipts','method':'POST',
                     'headers':headers,'client':('127.0.0.1',1)},receive,send)
        return sent[0]['status'],guard
    token=guest_token.issue('upload_test').encode()
    auth=[(b'x-guest-token',token)]
    assert (await request([],[]))[0]==401  # unauthenticated body is not read
    assert (await request(auth+[(b'content-length',str(MAX_UPLOAD_BODY+1).encode())],[]))[0]==413
    assert (await request(auth,[{'type':'http.request','body':b'x'*MAX_UPLOAD_BODY,'more_body':True},
                                {'type':'http.request','body':b'x','more_body':False}]))[0]==413
    assert not invoked
    assert (await request(auth,[{'type':'http.request','body':b'normal','more_body':False}]))[0]==200
    assert invoked==[b'normal']
    guard=RequestGuard(downstream)
    for _ in range(10):
        assert (await request(auth,[{'type':'http.request','body':b'normal','more_body':False}],guard))[0]==200
    status,guard=await request(auth,[],guard)
    assert status==429 and guard.uploads==0
    # A disconnected client releases the concurrency slot.
    statusGuard=RequestGuard(downstream)
    await statusGuard({'type':'http','path':'/v1/rewards/receipts','method':'POST',
        'headers':auth,'client':('127.0.0.1',1)},
        lambda: asyncio.sleep(0,result={'type':'http.disconnect'}),lambda _: asyncio.sleep(0))
    assert statusGuard.uploads==0
    gate = asyncio.Event()
    started = asyncio.Event()
    count = [0]
    async def slow_app(scope,receive,send):
        await receive()
        count[0]+=1
        if count[0]==2: started.set()
        await gate.wait()
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
    busy=RequestGuard(slow_app)
    first=asyncio.create_task(request(auth,[{'type':'http.request','body':b'a'}],busy))
    second=asyncio.create_task(request(auth,[{'type':'http.request','body':b'b'}],busy))
    await asyncio.wait_for(started.wait(),1)
    assert (await request(auth,[],busy))[0]==429
    gate.set()
    assert all(r[0]==200 for r in await asyncio.gather(first,second))
    assert busy.uploads==0
    request_guard.UPLOAD_TIMEOUT_SECONDS=0.02
    slow=RequestGuard(downstream)
    responses=[]
    async def slow_receive():
        await asyncio.sleep(1)
    async def capture(message): responses.append(message)
    await slow({'type':'http','path':'/v1/rewards/receipts','method':'POST',
        'headers':auth,'client':('127.0.0.1',1)},slow_receive,capture)
    assert responses[0]['status']==408 and slow.uploads==0
    request_guard.UPLOAD_TIMEOUT_SECONDS=20
asyncio.run(checks())
print('PASS: real image decoding, forged/truncated/oversized/animated images, auth before body, chunked size, bounded rate windows, disconnect cleanup')
