# Firestore JSON 스키마 (마스터 문서 §3.1 보완)

Status: Design companion  
Runtime MVP는 인메모리 / 이후 Postgres. 이 문서는 **취향·배달 민감도 분리**를 Firebase NoSQL로 옮길 때의 계약.

---

## 설계 원칙

1. **메뉴 배달 민감도**(`menus`)와 **유저 취향/거절**(`users`)을 컬렉션으로 분리  
2. 스와이프 Nope → `rejection_tags`에 push → Cloud Function 또는 클라이언트에서 다음 피드 가중치 반영  
3. 장소 지리 쿼리는 Firestore만으로 한계 → 프로덕션 피드는 **Postgres+PostGIS** 권장. Firestore는 유저 시그널·세션 미러용

---

## Collections

### `users/{uid}`

Guest-First 런타임 계약은 [AUTH-GUEST-FIRST.md](./AUTH-GUEST-FIRST.md) 참고.

```json
{
  "uid": "kakao_987654321",
  "auth_type": "kakao",
  "anonymous_linked_from": "anon_id_12345abc",
  "device_ids": ["web_local_uuid_or_idfv"],
  "nickname": "고민제로",
  "earned_titles": ["운명적 첫사랑", "미식계의 흥선대원군"],
  "title_ids": ["first_love", "picky_king"],
  "preferences": {
    "hate_tags": { "오이": 2, "고수": 1 },
    "hate_categories": { "noodle": 0.8 },
    "taste": ["pork", "jjamppong"],
    "preferred_spice_level": 2
  },
  "swipe_logs": [
    { "action": "nope", "menu_id": "m1", "tags": ["#오이"], "at": "…" }
  ],
  "firebase_uid": "optional_when_firebase_on",
  "created_at": "2026-09-14T12:00:00Z",
  "updated_at": "2026-09-14T12:05:00Z"
}
```

레거시 필드(`taste_vector`, `rejection_tags`)는 `preferences`로 이관.

### `places/{placeId}`

```json
{
  "name": "송도 뚝배기집",
  "geo": { "lat": 37.3930, "lng": 126.6455 },
  "hub_id": "hub_songdo",
  "market_id": "songdo_v1",
  "dong_code": "yeonsu:songdo-1",
  "delivery_available": true,
  "kakao_place_id": null,
  "is_active": true
}
```

### `menus/{menuId}`

```json
{
  "place_id": "p01",
  "name": "차돌된장찌개",
  "category": "korean",
  "tags": ["#스트레스_풀리는_국물"],
  "hero_image_url": "https://...",
  "temp_hold": 0.2,
  "texture_hold": 0.5,
  "spill_risk": 0.9,
  "delivery_sensitivity": 0.92,
  "price_krw": 12000,
  "is_signature": true,
  "is_active": true
}
```

`delivery_sensitivity` = 가중합 예시:

```
0.4 * (1 - temp_hold) + 0.4 * (1 - texture_hold) + 0.2 * spill_risk
```

### `sessions/{sessionId}`

```json
{
  "uid": "abc",
  "intent": "delivery",
  "weather_flag": "rain",
  "effective_radius_m": 1000,
  "start_lat": 37.3925,
  "start_lng": 126.6450,
  "perfect_slots_left": 5,
  "started_at": "2026-09-13T12:00:00Z"
}
```

### `swipe_events/{eventId}`

```json
{
  "session_id": "...",
  "uid": "abc",
  "menu_id": "m01",
  "place_id": "p01",
  "action": "nope",
  "intent": "visit",
  "distance_m": 420,
  "delivery_sensitivity": 0.92,
  "tags_snapshot": ["#스트레스_풀리는_국물"],
  "created_at": "2026-09-13T12:01:00Z"
}
```

---

## Nope → 실시간 페널티

```
on swipe left:
  for tag in menu.tags:
    users.rejection_tags[tag] = (users.rejection_tags[tag] || 0) + 1.0
  users.rejection_categories[menu.category] += 0.8
  → feed rescore: score -= rejection_tags[tag]
```

MVP 엔진(`backend/app/engine.py`)이 동일 규칙을 인메모리로 구현 중.

---

## 동적 반경 (세션 + 카드)

| intent | weather | session max | per-menu |
|--------|---------|-------------|----------|
| visit | clear | 700m | = session |
| visit | rain/snow | 500m | = session |
| delivery | clear | 1500m | `base * (1 - 0.4*sens)`, sens≥0.8 → ≤1000 |
| delivery | rain/snow | 1000m | 동일 + hard cap 1000 |

정본 수식: [MVP-PRD.md §4](./MVP-PRD.md) · 코드: `backend/app/radius.py`
