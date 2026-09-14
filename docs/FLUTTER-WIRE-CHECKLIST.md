# Flutter 와이어 / 구현 체크리스트

Status: Phase 1 · PRD v3 (방문/배달 · 스마트 반경)  
톤: Warm Orange · 「오늘 점심은 그냥여기 어때?」 · Tab 없음

---

## 0. 부트
- [ ] Flutter `just_here` + 카카오/구글 로그인 + 딥링크
- [ ] 라우트: splash → login → location → taste×3 → feed
- [ ] 테마: warm orange / chili red

---

## 1. 온보딩
- [ ] 소셜만 · 위치 1팝업 · 취향 스와이프 3장
- [ ] 설문/예산/알레르기 입력 없음

---

## 2. Feed (원스크린)
- [ ] 상단 브랜드 카피: 「오늘 점심은 그냥여기 어때?」
- [ ] **방문 | 배달** 토글 (유일한 주요 크롬)
- [ ] 토글 변경 시 `/feed` 재요청 (반경·CTA·딥링크 타입 변경)
- [ ] 사진 ≥80% · 상호 · 거리 · #태그1
- [ ] 하단 CTA: 방문「그냥여기로 가기」/ 배달「그냥여기로 시켜」
- [ ] Right = 수락 → 폭죽 → 딥링크 직행
- [ ] Left = 거절 → 재학습
- [ ] Long-press 상세
- [ ] 앱 오픈마다 GPS 갱신 · Perfect 5
- [ ] 연속 Nope 5 → 골드 카드

---

## 3. 스마트 반경 (클라 표시)
- [ ] 서버 `effective_radius_m` 디버그 표시(dev)
- [ ] 방문 거리 표기 도보 n분 (500–700m 대역)
- [ ] 배달 거리 표기 (1–1.5km / 축약 시 ≤1km)
- [ ] 빈 피드 시 반경 임의 확대 금지

---

## 4. Handoff
- [ ] 방문 → 네이버 지도 길안내 URL
- [ ] 배달 → 배민 검색 딥링크
- [ ] `handoff` 로그 (provider, intent)

---

## 5. Growth · 설정 · 관측
- [ ] 식탐 영수증 · Duo
- [ ] 숨은 설정
- [ ] intent / weather / radius / swipe / handoff 이벤트

---

## 6. 디자인
- [ ] Figma: 토글 포함 원스크린 · 방문/배달 각각 1플로우
- [ ] 폭죽 + 배민/지도 전환 모션
- [ ] 웜오렌지 Full-bleed 압도감 검증
