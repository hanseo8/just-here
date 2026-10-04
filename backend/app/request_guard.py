"""Bounded, single-process API guard. No external service or persistent counters."""
import hashlib
import asyncio
import json
import time
from collections import OrderedDict, deque
from . import guest_token

MAX_UPLOAD_BODY = 9 * 1024 * 1024  # 8MB image plus multipart fields
UPLOAD_TIMEOUT_SECONDS = 20

class WindowLimiter:
    def __init__(self, capacity=4096, clock=time.monotonic):
        self.buckets = OrderedDict()
        self.capacity = capacity
        self.clock = clock

    def allow(self, key, limit):
        now = self.clock()
        bucket = self.buckets.get(key)
        if bucket is None:
            if len(self.buckets) >= self.capacity:
                for old in list(self.buckets):
                    if not self.buckets[old] or self.buckets[old][-1] <= now - 60:
                        del self.buckets[old]
                if len(self.buckets) >= self.capacity:
                    return False
            bucket = self.buckets[key] = deque()
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

class RequestGuard:
    def __init__(self, app):
        self.app = app
        self.limiter = WindowLimiter()
        self.uploads = 0

    async def reject(self, send, status, message):
        headers = [(b'content-type', b'application/json'), (b'cache-control', b'no-store'),
                   (b'x-content-type-options', b'nosniff')]
        if status == 429:
            headers.append((b'retry-after', b'60'))
        await send({'type':'http.response.start', 'status':status, 'headers':headers})
        await send({'type':'http.response.body', 'body':json.dumps({'detail':message}).encode()})

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path, method = scope['path'], scope['method']
        upload = path == '/v1/rewards/receipts' and method == 'POST'
        group = None
        if path.startswith('/v1/auth/') and method == 'POST':
            group, per_client, total = 'auth', 30, 300
        elif path == '/v1/analytics/event' and method == 'POST':
            group, per_client, total = 'events', 120, 1200
        elif path.startswith('/v1/admin/') or path == '/v1/analytics/summary':
            group, per_client, total = 'admin', 180, 600
        elif upload or (path == '/v1/rewards/payouts' and method == 'POST'):
            group, per_client, total = 'rewards', 10, 120
        if not group:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        identity = (scope.get('client') or ('unknown',0))[0]
        if group == 'rewards':
            token = headers.get(b'x-guest-token', b'').decode('latin1')
            verified = guest_token.verify(token)
            if not verified:
                return await self.reject(send, 401, 'guest token required')
            identity = verified['uid']
        key = hashlib.sha256(str(identity).encode()).hexdigest()
        if not self.limiter.allow((group, key), per_client) or not self.limiter.allow((group, 'global'), total):
            return await self.reject(send, 429, '요청이 많아요. 잠시 후 다시 시도해 주세요.')
        if not upload:
            return await self.app(scope, receive, send)
        length = headers.get(b'content-length')
        if length:
            try:
                size = int(length)
            except ValueError:
                return await self.reject(send, 400, 'invalid content length')
            if size < 0 or size > MAX_UPLOAD_BODY:
                return await self.reject(send, 413, 'receipt upload too large')
        if self.uploads >= 2:
            return await self.reject(send, 429, '사진을 처리 중이에요. 잠시 후 다시 올려 주세요.')
        self.uploads += 1
        try:
            # Bound chunked uploads before the multipart parser writes temporary files.
            body = bytearray()
            deadline = time.monotonic() + UPLOAD_TIMEOUT_SECONDS
            while True:
                try:
                    message = await asyncio.wait_for(receive(), timeout=max(0.001, deadline - time.monotonic()))
                except TimeoutError:
                    return await self.reject(send, 408, 'receipt upload timed out')
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body', b'')
                if len(body) + len(chunk) > MAX_UPLOAD_BODY:
                    return await self.reject(send, 413, 'receipt upload too large')
                body.extend(chunk)
                if not message.get('more_body', False):
                    break
            delivered = False
            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type':'http.request', 'body':bytes(body), 'more_body':False}
                return await receive()
            return await self.app(scope, bounded_receive, send)
        finally:
            self.uploads -= 1
