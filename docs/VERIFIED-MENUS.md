# 검증 메뉴 소규모 실험

목적: **한 지역에서 실제 판매 중인 메뉴 20~30개**를 확인한다.  
이 숫자는 초기 실험 규모이지, 추천 품질을 보장하는 수치가 아니다.

메뉴 선택 → 판매 가게 최대 3곳 흐름은 **이 카탈로그가 채워지고 로더가 검증한 뒤에만** 시험한다. 카테고리로 추정한 이름을 판매 메뉴처럼 쓰지 않는다.

---

## 범위

| | |
|--|--|
| 허브 | `hub_songdo` |
| 1차 동 | 송도1동 (`yeonsu:songdo-1`) |
| 목표 | 확인된 행 20~30개 |
| 관리자 화면 | 없음. 기존 JSON 등록을 재사용 |

파일:

1. 양식: `data/verified-menus.songdo.example.json`
2. 실제 입력: **`DATA_DIR/verified-menus.json`**
   - 로컬 기본: 레포 `data/verified-menus.json` (gitignore, 추정 시드 금지)
   - 운영: Render 영구 디스크 **`/data/verified-menus.json`** (`DATA_DIR=/data`)
   - 예시 파일(`*.example.json`)은 이 경로가 아니며 추천에 넣지 않는다
3. 로더: `backend/app/verified_menus.py` — 필수 필드가 있는 행만 `menu_verified=True`. **랭킹 미연결**
4. 검사: `python scripts/check-verified-menus.py`

랭킹·피드에는 **아직 연결하지 않는다.**

---

## 필드

확인되지 않은 값은 비운다. 추정값과 검증값을 한 칸에 섞지 않는다.

| 필드 | 검증으로 쓰는 조건 | 비고 |
|------|-------------------|------|
| `menu_name` | 필수 | 가게에서 확인한 판매명 |
| `place_name` | 필수 | 상호 |
| `address` | 필수 | 도로명 또는 지번 |
| `source` | 필수 | `visit` / `receipt` / `official` / `owner` |
| `source_url` 또는 `source_note` | 둘 중 하나 필수 | 메뉴판 URL, 영수증 메모, 방문 기록 등 추적 가능한 근거 |
| `confirmed_by` | 선택 | 확인한 사람/역할 |
| `confirmed_at` | 필수 | 확인 날짜 `YYYY-MM-DD` |
| `price_krw` | 숫자이고 `price_verified_at`이 있을 때만 | 없으면 저렴한 것으로 치지 않음 |
| `meal_contexts` | 현장에서 맞다고 확인한 태그만 | `meal` / `late_night` / `anju` |
| `photo_url` + `photo_rights` | 둘 다 확인될 때만 사용 | `true`가 아니면 사진 비움 |
| `hours` + `hours_verified` | `hours_verified=true`일 때만 영업시간 표시 | |
| `order_url` + `order_verified` | `order_verified=true`일 때만 주문 연결 | |
| `open_now` / `delivery_available` / `portion` | 확인된 boolean/문구만 | 모르면 `null` / `""` |

`example: true` 행은 로더가 버린다.

---

## 수집 절차

1. 송도1동에서 방문 또는 공식 메뉴판·영수증으로 확인한다.
2. 양식을 복사해 한 행씩 채운다. 모르는 칸은 비운다.
3. `python scripts/check-verified-menus.py`로 통과 행 수를 본다.
4. 20개가 넘어도 피드에 자동 연결하지 않는다. 연결은 별도 결정이다.
