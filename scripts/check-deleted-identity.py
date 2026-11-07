"""Revocation primitives in a disposable UserStore only. No live deletions."""
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw,GUEST_SIGNING_SECRET='isolated-deletion-test',KAKAO_REST_API_KEY=' ',GOOGLE_PLACES_PHOTOS='off')
    from backend.app import users,guest_token
    store=users.UserStore(Path(raw)/'users.json')
    with patch.object(users,'STORE',store):
        old=store.ensure_guest('test-device')['uid'];other=store.ensure_guest('other-device')['uid']
        token=guest_token.issue(old,'test-device');other_token=guest_token.issue(other,'other-device')
        assert guest_token.verify(token)
        original=store.get(old)
        with patch.object(store,'_save',side_effect=OSError('isolated-write-failure')):
            try:store.delete_profile(old);raise AssertionError('write failure ignored')
            except OSError:pass
        assert store.get(old)==original and guest_token.verify(token)
        assert store.delete_profile(old)=={'profiles_removed':1,'device_links_removed':1}
        assert store.get(old) is None and guest_token.verify(token) is None
        assert guest_token.verify(other_token) and store.get(other)
        assert store.delete_profile(old)['profiles_removed']==0
        try:store.ensure_uid(old);raise AssertionError('deleted UID resurrected')
        except ValueError as e:assert str(e)=='identity_deleted'
        for source,target in [(old,other),(other,old)]:
            try:store.merge_guest_into(source,target,auth_type='phone');raise AssertionError('deleted UID linked')
            except ValueError as e:assert str(e)=='identity_deleted'
        new=store.ensure_guest('test-device')['uid'];assert new!=old
        assert store.ensure_guest('test-device')['uid']==new and not store.get(new)['earned_titles']
        assert guest_token.verify(token) is None
        fresh_token=guest_token.issue(new,'test-device');assert guest_token.verify(fresh_token)
        restored=users.UserStore(store.path)
        with patch.object(users,'STORE',restored):
            assert guest_token.verify(token) is None and guest_token.verify(other_token) and guest_token.verify(fresh_token)
        linked=store.ensure_uid('linked-user',auth_type='kakao')
        try:store.delete_profile(linked['uid']);raise AssertionError('external identity deleted without resolution')
        except ValueError as e:assert str(e)=='external_identity_resolution_required'
        contents=json.loads(store.path.read_text(encoding='utf-8'));assert old not in contents['users']
        assert all(len(v)==64 for v in contents['deleted_uid_hashes'])
        damaged=Path(raw)/'damaged.json';damaged.write_text('{"users":{},"device_index":{},"deleted_uid_hashes":{}}')
        bad=users.UserStore(damaged)
        with patch.object(users,'STORE',bad):
            assert guest_token.verify(other_token) is None
            try:bad.ensure_guest('must-not-overwrite');raise AssertionError('damaged registry overwritten')
            except ValueError:pass
        assert damaged.read_text()=='{"users":{},"device_index":{},"deleted_uid_hashes":{}}'
    print('PASS deleted identity primitive: old-token revocation, same-device new UID, restart, unaffected users, no resurrection/merge, write rollback, external identity guard, damaged-registry fail-closed; no deletion endpoint enabled')
