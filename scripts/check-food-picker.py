import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'backend'))
from app import kakao, engine
root=Path(__file__).resolve().parents[1]
groups=json.loads((root/'web/food-categories.json').read_text(encoding='utf-8'))
assert len(groups)==13
assert [x['label'] for x in groups[:5]]==['한식','찜·탕','회','패스트푸드','치킨']
keys=set()
for group in groups:
    for item in [group,*group['items']]:
        key=item['key'];keys.add(key)
        assert key in kakao.TASTE_QUERIES,key
        assert key in kakao.TASTE_CATEGORY,key
        assert 0 <= item['image'] < 36
        assert engine._taste_boost({'category':kakao.TASTE_CATEGORY[key]},[key])>0,key
assert {'dakbal','skewers','gopchang'} <= keys
js=(root/'web/app.js').read_text(encoding='utf-8')
inline=js.split('const FOOD_GROUPS = ',1)[1].split(';',1)[0]
assert json.loads(inline)==groups
print('food picker: all 13 groups, menu search keys and ranking signals passed')
