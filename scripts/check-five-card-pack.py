import copy,os,tempfile
from unittest.mock import patch
with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw,KAKAO_REST_API_KEY=' ',GOOGLE_PLACES_PHOTOS='off')
    from backend.app import engine as e,analytics
    assert e.PACK_SIZE==5
    def cards(n):
        return [dict(card_id=f'c{i}',menu_id=f'm{i}',place_id=f'p{i}',place_name=f'가게{i}',category='korean',kind='korean',tags=[]) for i in range(n)]
    for n in (0,1,3,5,8):
        s=e.Session('fixture',37.5,127,'visit','clear')
        pool=cards(n)
        with patch.object(e,'build_cards',return_value=(copy.deepcopy(pool),700,False)):
            e.start_pack(s)
        assert len(s.pack_cards)==min(n,5)
        if not n:continue
        assert [c['pack_rank'] for c in s.pack_cards]==list(range(1,min(n,5)+1))
        assert all(c['pack_size']==min(n,5) for c in s.pack_cards)
        ids=[c['menu_id'] for c in s.pack_cards]
        assert not e.apply_undo(s)
        for i,ident in enumerate(ids):
            top=s.pack_cards[0];assert top['menu_id']==ident
            exhausted=e.apply_nope(s,top)
            assert exhausted==(i==len(ids)-1)
        assert s.adjust_needed and len(s.undo_stack)==min(n,5)
        for ident in reversed(ids):
            assert e.apply_undo(s);assert s.pack_cards[0]['menu_id']==ident
        assert not e.apply_undo(s)
        assert [c['menu_id'] for c in s.pack_cards]==ids
    for rank in (1,3,4,5):
        r=[{'event':'recommend_shown','ts':'2026-11-21T00:00:00Z','props':{'session_id':'s','pack_id':'p'}},
           {'event':'swipe_go','ts':'2026-11-21T00:00:01Z','props':{'session_id':'s','pack_id':'p','rank':rank}}]
        assert analytics.product_metrics(r)['first_pack_choose_rate']==100
    print('PASS five-card pack: 0/1/3/5/8 candidate bounds, true ranks/counts, next/previous round trip, exhausted pack undo, and fourth/fifth choice analytics')
