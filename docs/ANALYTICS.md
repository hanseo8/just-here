# Analytics (소프트런치)

앱 퍼널을 서버에 쌓고, 토큰으로 보호된 대시보드에서 봅니다.

## 쓰는 법

1. Render Environment에 `ADMIN_TOKEN`을 임의 긴 문자열로 설정 (로컬은 `backend/.env`).
2. 배포 후 사용자가 앱을 쓰면 이벤트가 `data/events.jsonl`에 쌓입니다.
3. 대시보드: `https://www.justthis.co.kr/analytics`  
   - 토큰 입력 후 「불러오기」  
   - 또는 `?token=YOUR_TOKEN` (브라우저에 저장됨)

## 수집 이벤트

| 이벤트 | 시점 |
|--------|------|
| `app_open` | 앱 로드 |
| `locate_ok` / `locate_fallback` | 위치 성공 / 송도 폴백 (세션당 1회) |
| `taste_done` | 취향 온보딩 완료 |
| `session_start` | 스와이프 세션 시작 |
| `recommend_shown` | 후보를 화면에 처음 보여줄 때. 집계 키는 **세션 + pack_id + menu_id(후보)** |
| `undo` | 같은 묶음 직전 후보 재열람. `recommend_shown`으로 중복 집계하지 않음 |
| `swipe_nope` / `swipe_go` | 스와이프 |
| `match_done` | 매칭 완료 |
| `share` | 링크/네이티브/카톡 공유 |
| `kakao_link` / `kakao_share` | 카카오 연동 · 카톡 공유 |
| `duo_create` | Duo 초대 |
| `install_click` | PWA 설치 버튼 |

API:

- `POST /v1/analytics/event` — 공개 (허용 이벤트만)
- `GET /v1/analytics/summary?token=&days=7` — 관리자

## 저장 위치

`DATA_DIR/events.jsonl`에 쌓입니다. `DATA_DIR`이 비어 있으면 레포의 `data/`를 씁니다.

Render는 기본이 휘발성 파일시스템이라, **영구 디스크를 붙이고 `DATA_DIR`을 마운트 경로로 지정해야** 데이터가 남습니다. 무료 플랜은 디스크를 붙일 수 없고 15분 유휴 시 스핀다운하면서 파일이 초기화되므로, 사실상 접속이 끊길 때마다 지표가 사라집니다.

- Render Dashboard → 서비스 → Settings → Instance Type을 **Starter 이상**으로
- 같은 화면에서 **Disk 추가** (mount path `/data`, 1GB)
- Environment에 **`DATA_DIR=/data`**

## 한계와 다음 단계

- 디스크를 붙이면 무중단 배포가 꺼져 배포 때마다 몇 초 끊깁니다.
- **GA4** (또는 Mixpanel): 페이지·유입 채널·리텐션에 강함. 태그 한 줄로 병행 가능.
- **Postgres / Firestore**: 이벤트 영구 저장 + 지역·시간대 리포트 (B2B용).

GA4만 쓰면 카카오 연동·취향·매칭 같은 제품 퍼널을 대시보드에 맞게 묶기 어렵습니다.  
지금은 **자체 퍼널 로그 + `/analytics`** 가 가장 빠르고, 트래픽이 늘면 GA4 + DB를 붙이면 됩니다.
