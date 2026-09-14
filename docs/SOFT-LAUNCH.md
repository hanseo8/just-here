# 소프트런칭 배포 · 사람들이 받는 방법

**지금 배포 형태 = 웹앱(PWA).**  
앱스토어(Play/App Store) 심사는 DAU 검증 후. 지금은 링크로 즉시 배포합니다.

공개 주소: **https://justthis.co.kr** (또는 https://www.justthis.co.kr)

---

## 0. 마지막 점검 결과 (2026-09-14)

| 항목 | 결과 |
|------|------|
| `/health` | OK (`kakao_enabled: true`) |
| `/v1/meta` | OK |
| 루트/www 도메인 | OK |
| 출시 컷라인 (LAUNCH.md) | 충족 |
| 홈 화면 설치(PWA) | 이번 배포에 포함 |

---

## 1. 서버 배포 (이미 연결됨)

1. GitHub `main` 푸시 → Render 자동 배포  
2. 배포 후 확인:
   - https://justthis.co.kr/health
   - https://justthis.co.kr/manifest.webmanifest
3. Render Environment:
   - `PUBLIC_BASE_URL=https://www.justthis.co.kr`
   - `KAKAO_REST_API_KEY` (카카오 근처검색용)

---

## 2. 사람들이 “받는” 방법 (다운로드 대체)

### A) 카톡으로 링크 뿌리기 (가장 빠름)

```text
오늘 점심 고민 끝.
그냥여기 → https://justthis.co.kr
위치 허용 → 카드 고르기 → 지도로 바로 이동
홈 화면에 추가하면 앱처럼 뜹니다.
```

### B) 폰에 앱처럼 설치 (PWA)

**Android Chrome**
1. https://justthis.co.kr 접속  
2. 「홈 화면에 추가」 또는 앱 내 버튼  
3. 홈 화면 아이콘으로 실행  

**iPhone Safari**
1. Safari로 접속 (Chrome 아님)  
2. 공유 → **홈 화면에 추가**  
3. 홈 화면에서 실행  

### C) 영수증/Duo 공유

- 선택 완료 → **영수증 자랑하기** / 링크 복사  
- Duo → **둘이서 고르기** 초대 링크  

공유 링크가 `justthis.co.kr` / `www` 로 나가는지 한 번 확인.

---

## 3. 오늘 바로 할 일 (소프트런칭)

1. [ ] Render 최신 배포 Live 확인  
2. [ ] 본인 폰에서 시작→선택→지도→공유 1회  
3. [ ] 홈 화면 추가 1회  
4. [ ] 지인 **5~10명** 카톡 발송  
5. [ ] (선택) 카카오 개발자 콘솔에 `www.justthis.co.kr` 도메인 등록  

---

## 4. 아직 안 하는 것

- Play Store / App Store 업로드  
- Flutter/RN 네이티브 앱  
- 유료 광고 (DAU 200 전)

---

## 5. 장애 시

| 증상 | 조치 |
|------|------|
| 첫 접속 느림 | Render Free 슬립 — 30~60초 대기 후 새로고침 |
| 위치 거부 | 송도 폴백으로도 시작 가능 |
| 공유 링크가 onrender | Render에 `PUBLIC_BASE_URL` 확인 후 재배포 |
