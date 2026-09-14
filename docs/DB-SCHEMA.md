# 그냥여기 — 인벤토리 / 이벤트 DB 스키마 초안

Status: Draft (CTO)  
DB: PostgreSQL 16 + PostGIS + (Phase 2) pgvector

---

## 1. ER 개요

```
hubs (직장권) ── markets (오픈 게이트) ── admin_dongs / zones ── places
users ── preferences / taste
sessions ── swipe_events / penalties / matches / nav_starts
```

지리 키: **`hub_id` → `market_id` → `dong_code` (+ optional `zone_id`)**.  
직장권은 여러 개 병행 시드, 유저 피드는 **오픈된 market만**.

---

## 2. 상권 (허브 × 동)

### `hubs`
직장권 포트폴리오. **런칭 허브 = `hub_songdo` (인천 송도).**

| Column | Type | Notes |
|--------|------|--------|
| id | text PK | `hub_songdo` (W0). 이후 확장 허브 추가 |
| name | text | 인천 송도 |
| default_travel_mode | text | `walk` \| `car` |
| default_max_travel_minutes | int | |
| created_at | timestamptz | |

### `markets`
허브 안의 **베타 오픈 단위**.

| Column | Type | Notes |
|--------|------|--------|
| id | text PK | e.g. `songdo_v1` |
| hub_id | text FK → hubs | `hub_songdo` |
| name | text | |
| status | text | `seed` \| `beta` \| `ga` \| `off` |
| created_at | timestamptz | |

### `admin_dongs`
| Column | Type | Notes |
|--------|------|--------|
| dong_code | text PK | slug e.g. `bundang:sampyeong` |
| admin_code | text | 공식 행정동코드 (optional) |
| si_name | text | 서울/경기/인천 |
| gu_name | text | |
| dong_name | text | |
| centroid | geography(Point,4326) | |
| boundary | geography(MultiPolygon,4326) | optional |
| hub_id | text FK | |
| market_id | text FK → markets | null = 미오픈 |
| seed_priority | smallint | 1=코어 |
| target_place_count | int | |
| is_active | bool | |

### `zones`
행정동이 너무 클 때 (여의도·공단·캠퍼스).

| Column | Type | Notes |
|--------|------|--------|
| id | text PK | e.g. `yeongdeungpo:yeouido:ifc_park` |
| dong_code | text FK | |
| name | text | |
| centroid | geography(Point,4326) | |
| market_id | text FK | |
| seed_priority | smallint | |
| target_place_count | int | |
| is_active | bool | |

Index: `GIST(centroid)` on dongs/zones, `(market_id, is_active)`, `(hub_id)`

**피드 규칙:** GPS + `intent`(visit|delivery) + weather + menu sensitivity → **effective_radius_m**  
→ `ST_DWithin(..., effective_radius_m)` ∩ 오픈 market.  
허브/동은 시드 게이트. 반경을 구·동 경계로 대체하지 않음.

---

## 3. 유저

### `users`
| Column | Type | Notes |
|--------|------|--------|
| id | uuid PK | |
| firebase_uid | text UNIQUE NOT NULL | |
| created_at | timestamptz | |
| last_seen_at | timestamptz | |
| status | text | `active` \| `deleted` |

### `user_preferences`
| Column | Type | Notes |
|--------|------|--------|
| user_id | uuid PK FK | |
| default_intent | text | `visit` \| `delivery` |
| budget_max_krw | int | nullable, 추정/숨은설정 |
| forbidden_ingredients | text[] | nullable |
| updated_at | timestamptz | |

### `user_taste_signals`
| Column | Type | Notes |
|--------|------|--------|
| id | uuid PK | |
| user_id | uuid FK | |
| signal_key | text | |
| signal_value | real | |
| source | text | `onboarding` \| `implicit` |
| created_at | timestamptz | |

UNIQUE `(user_id, signal_key, source)`

---

## 4. 인벤토리

### `places`
| Column | Type | Notes |
|--------|------|--------|
| id | uuid PK | |
| name | text NOT NULL | |
| name_normalized | text | |
| geo | geography(Point,4326) NOT NULL | |
| address | text | |
| phone | text | |
| dong_code | text FK → admin_dongs | **필수** |
| zone_id | text FK → zones | nullable (여의도·판교·공단) |
| hub_id | text | denormalized |
| market_id | text | denormalized for query speed |
| kakao_place_id | text | 카카오 로컬 연동 |
| naver_place_id | text | 네이버 enrich |
| delivery_available | bool | 배민 등 힌트 |
| is_active | bool | |
| data_quality_score | real | 0..1 |
| created_at / updated_at | timestamptz | |

Index: `GIST(geo)`, `(dong_code, is_active)`, `(market_id, is_active)`

### `place_hours` / `place_breaks` / `place_attributes`
영업·브레이크·solo_friendly 등.

### `menus`
| Column | Type | Notes |
|--------|------|--------|
| id | uuid PK | |
| place_id | uuid FK | |
| name | text | |
| price_krw | int | |
| category | text | |
| is_signature | bool | |
| is_active | bool | |
| ingredients | text[] | |
| spice_level | smallint | |
| **temp_hold** | real | 0–1, 높을수록 온도 잘 유지 |
| **texture_hold** | real | 0–1, 높을수록 식감 유지 |
| **spill_risk** | real | 0–1, 높을수록 위험 |
| **delivery_sensitivity** | real | 0–1, **높을수록 배달 민감** (반경 축약) |
| description | text | |

민감도 예: 뚝배기 국물·바삭 돈가스 → `delivery_sensitivity` ≈ 0.9

### `menu_tags` / `menu_media`
기존과 동일. hero 필수.

### `place_media_cache` (네이버 enrich)
| Column | Type | Notes |
|--------|------|--------|
| place_id | uuid | |
| image_url | text | |
| review_snippet | text | |
| rating | real | |
| fetched_at | timestamptz | |
| source | text | `naver` |

---

## 5. 세션 / 이벤트

### `sessions`
| Column | Type | Notes |
|--------|------|--------|
| id | uuid PK | |
| user_id | uuid FK | |
| intent | text | `visit` \| `delivery` |
| start_lat / start_lng | double | |
| weather_flag | text | |
| effective_radius_m | int | 세션 상한 반경 |
| dong_code / zone_id / hub_id / market_id | text | |
| perfect_slots_left | smallint | default 5 |
| started_at / ended_at | timestamptz | |

### `swipe_events`
기존 + `intent`, `distance_m`, `delivery_sensitivity` 스냅샷.

### `matches` / `handoffs` (구 nav_starts)
| Column | Type | Notes |
|--------|------|--------|
| id | uuid PK | |
| match_id | uuid FK | |
| intent | text | |
| provider | text | `naver_map` \| `baemin` |
| deep_link | text | |
| created_at | timestamptz | |

---

## 6. 후보 쿼리 스케치

```sql
-- :radius_m = 엔진이 준 effective_radius_m
-- visit: 500–700 / delivery: 최대 1500, 축약 시 <=1000
SELECT m.id AS menu_id, p.id AS place_id,
       ST_Distance(p.geo, ST_MakePoint(:lng,:lat)::geography) AS distance_m,
       m.delivery_sensitivity
FROM menus m
JOIN places p ON p.id = m.place_id
JOIN menu_media media ON media.menu_id = m.id AND media.is_hero
WHERE p.is_active AND m.is_active
  AND ST_DWithin(p.geo, ST_MakePoint(:lng,:lat)::geography, :radius_m)
  AND (
    :intent = 'visit' AND is_open_now(p.id, now())
    OR :intent = 'delivery' AND COALESCE(p.delivery_available, true)
  );
```

카드 노출 직전 (배달):  
`distance_m <= f(base_radius, weather, m.delivery_sensitivity)`

---

## 7. 시드 규칙

1. hub 시드 병행, 노출은 market 게이트.  
2. 메뉴 등록 시 **delivery_sensitivity 필수** (룰베이스 초기값 OK).  
3. 카카오 place 매핑 · 네이버 enrich 캐시 TTL.  
4. 허브 간 학습 격리.
