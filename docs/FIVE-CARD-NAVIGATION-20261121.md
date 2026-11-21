# 5개 후보와 3버튼 선택 — 2026-11-21

상태: 2026-11-22 운영 배포 준비. 43개 검사 재실행 통과 및 배포 전 백업 확보. 앞선 추가 점검의 전환/지연 응답 보호 수정도 포함. 배포 결과는 docs/DEPLOY-20261122-NAV5.md에 기록.

## 동작
- 왼쪽 이전 가게 / 가운데 그냥여기 / 오른쪽 다른 가게. 작은 중복 방향 안내 제거.
- 왼쪽 스와이프는 undo, 오른쪽 스와이프는 다음(nope), 가운데 버튼만 확정(lets_go).
- 첫 가게의 이전 버튼 비활성. 첫 카드 왼쪽 제스처는 원위치 및 안내.
- 요청/애니메이션 중 중복 입력 차단, 오래된 응답 보호. undo 후 버튼 문구/위치 복구.
- 첫 묶음 최대5개. 후보가 0/1/3개면 실제 개수 사용, 가짜 후보로 채우지 않음. 한 번에 화면에는 한 카드만 표시.
- 네 번째/다섯 번째 선택도 첫 묶음 선택 집계에 포함. 관리자 문구는 고정 3장에서 첫 묶음으로 변경.
- SW v83 및 nav5 자산 버전 준비.

## 사진 범위
Google 장소 사진, 기존 승인 사진·매칭 보호 유지. 카카오 로컬/네이버 지역 공개 API 응답에는 가게 사진 필드가 없어 카드 내 모든 사진 자동 확보를 구현했다고 주장하지 않음.
상세 정보에 카카오맵 사진·후기 및 네이버지도 검색 링크 추가. 카카오 place_id가 있으면 정확한 장소 상세로 연결하고, 없으면 상호+주소 검색. 네이버는 상호+주소 검색이며 같은 지점인지 확인 안내. 외부 사이트 사진을 크롤링/복사하지 않음.
공식 자료:
- https://developers.kakao.com/docs/ko/local/dev-guide
- https://developers.naver.com/docs/serviceapi/search/local/local.md
- https://developers.naver.com/docs/serviceapi/search/image/image.md

## 검증
check-five-card-pack: 0/1/3/5/8 후보 → 최대5개, 순서·실제 개수·이전/다음 전체 왕복, 모두 넘긴 뒤 이전 복귀, 4·5번째 선택 집계.
check-brand-flow: 5개 계약으로 갱신, 임시 DATA_DIR/외부 API off 상태에서 전체 통과.
check-swipe-directions, swipe-races, photo-state, location-ui, my-ui, repeat-ui, release-cache, matching-quality, repeat-use, acquisition, google-photos 및 app.js 구문 검사 통과.
모바일390px에서 가로 넘침 없음, 버튼 x순서 및 하단 표시 확인.
실제 로컬 화면: 배달1/5 → 다른 가게2/5 → 이전1/5, 오른쪽 제스처 다음/왼쪽 이전, 가운데 클릭 후 완료 화면 확인. 실제 주문 링크는 열지 않음. 운영 고객 신청/선정/지급 변경 없음.
로컬 방문 검증 API는 5개 후보 반환 확인. UI 방문 경로의 첫 fixture 검색은 빈 결과를 표시했으며, 이를 실제 운영 위치나 식당 검증 성공으로 간주하지 않음.
시안 스크린샷: output/five-card-navigation-preview.jpg (기존 예시 사진·가게명 사용, 실제 추천 아님).
검증 서버: output/run-five-card-preview.py, 127.0.0.1:8028, 임시 데이터 전용.
