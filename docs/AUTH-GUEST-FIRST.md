# Guest-First 인증 (IP 무관 동일 유저 식별)

Status: 웹 MVP 구현됨 (2026-09-14)  
목표: 와이파이/IP가 바뀌어도 **같은 사람**의 취향·스와이프·칭호 도감을 누적.

---

## CTO 판정

| 요청 | 웹 MVP | 네이티브(이후) |
|------|--------|----------------|
| IP 트래킹 | **배제** | 배제 |
| 기기 식별 | `localStorage` device_id | ANDROID_ID / IDFV |
| 익명 로그인 | `/v1/auth/guest` (+ 선택 Firebase Anonymous) | Firebase `signInAnonymously` |
| 카카오 병합 | `/v1/auth/kakao/link` | Firebase link / Custom Token |
| 유저 JSON | `data/users.json` (Firestore 호환) | Firestore `users/{uid}` |

**지금 가능한 것:** Guest-First + 기기 바인딩 + 카카오 계정 병합 API/UI.  
**키 필요:** `KAKAO_JS_KEY`(웹 로그인), 선택 `FIREBASE_*`.

---

## 플로우

### 1) 앱 최초 실행 (회원가입 없음)
1. 클라이언트가 `jh_device_id` 생성·저장 (IP와 무관)
2. `POST /v1/auth/guest` → `anon_…` uid 발급
3. 취향·스와이프·칭호가 이 uid에 적재

### 2) 칭호 공유 / 도감 영구 저장
1. 완료 화면 「카카오로 3초 만에 도감 저장」
2. Kakao Login → access_token
3. `POST /v1/auth/kakao/link` → `kakao_{id}` 로 **계정 병합**
4. `anonymous_linked_from`에 익명 uid 기록

---

## API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/v1/auth/guest` | `{device_id, firebase_uid?}` |
| POST | `/v1/auth/kakao/link` | `{guest_uid, access_token}` |
| GET | `/v1/me?uid=` | 프로필·도감·preferences |
| POST | `/v1/me/taste` | 취향 동기화 |
| (내장) | `/v1/session`, `/v1/swipe` | `uid` 전달 시 누적 |

---

## users 문서 예시 (Firestore 호환)

```json
{
  "uid": "kakao_987654321",
  "auth_type": "kakao",
  "anonymous_linked_from": "anon_id_12345abc",
  "nickname": "고민제로",
  "earned_titles": ["운명적 첫사랑", "미식계의 흥선대원군"],
  "preferences": {
    "hate_tags": {"#오이": 2},
    "preferred_spice_level": 2,
    "taste": ["pork", "jjamppong"]
  },
  "swipe_logs": [],
  "device_ids": ["…"]
}
```

런타임 파일: `data/users.json` (재배포 시 휘발 가능 → 다음 단계 Firestore/Postgres)

---

## Render 환경변수

```
KAKAO_REST_API_KEY=…
KAKAO_JS_KEY=…          # 카카오 개발자 콘솔 JavaScript 키
PUBLIC_BASE_URL=https://www.justthis.co.kr
# 선택 Firebase Web config
FIREBASE_API_KEY=
FIREBASE_AUTH_DOMAIN=
FIREBASE_PROJECT_ID=
```

카카오 콘솔: 플랫폼 Web 도메인에 `https://www.justthis.co.kr`, `https://justthis.co.kr` 등록.

---

## 네이티브 전환 시

1. Firebase Anonymous Auth SDK 필수화  
2. ANDROID_ID / IDFV → `device_ids[]`에 추가 바인딩  
3. `UserStore`를 Firestore 어댑터로 교체 (`docs/FIRESTORE-SCHEMA.md` users)  
4. 카카오 → Firebase Custom Token 또는 OIDC 링크
