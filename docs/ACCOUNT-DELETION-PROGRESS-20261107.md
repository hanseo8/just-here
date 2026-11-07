# 계정 삭제 준비 · 2026-11-07

이 문서는 이전 준비 단계 기록이다. 최신 구현 범위는 ACCOUNT-DELETION-EXECUTOR.md를 참고한다. 전체 개인정보 삭제 완료를 표방하지 않는다.

## 이번 구현
- 사용자 삭제 요청 상태에 본인 영수증/포인트/지급/쿠폰/본인인증/테스트 참여의 확인 사항을 표시. 운영자 화면도 거래기록·인증 기록 보존 검토를 구분.
- 삭제 요청·철회·상태 새로고침, 중복 클릭 차단, 계정 전환 시 이전 계정 정보 숨김. 로컬 인증을 임의 제거하거나 재발급하지 않는다.
- 내부 UserStore.delete_profile 원시 연산: 익명 프로필 및 기기 연결 제거, UID 해시 폐기 목록 보존. 저장 실패 시 메모리 롤백. 외부 인증·연결 계정은 별도 해결 전 거절.
- guest token 확인에서 폐기 UID 차단. 같은 기기로 새 게스트를 만들더라도 새 UID이며 이전 토큰은 계속 무효. 콜백 ensure_uid/계정 병합으로 폐기 UID 부활 불가. 손상된 폐기 목록은 실패로 차단하고 파일을 덮지 않는다.
- delete_profile은 HTTP 경로에서 호출하지 않는다. 이벤트·거래·인증·쿠폰·메모리·백업 정리까지 끝내는 실행기가 아니다.

## 검사
임시 UserStore에서 삭제/재가입/재시작/다른 계정/저장 실패/외부 연동 차단/손상 파일 거절 검증. 운영 데이터 삭제 없음.
- python -m scripts.check-deleted-identity
- python -m scripts.check-account-deletion
- node scripts/check-account-deletion-ui.cjs
- python -m scripts.check-receipt-settlement-flow
- python -m scripts.check-reward-identity
- npm run bundle --prefix mobile; npm run check --prefix mobile

## 다음 구현에서 남은 항목
- 거래·인증·부정 방지 기록별 삭제/별도 보존/기간/근거 정책 확정. 기록이 있다는 이유만으로 계정 삭제를 무기한 거부하지 않도록 설계.
- UID 연결 관계 전체, 원장·계좌·영수증 사진·쿠폰·개별 이벤트·메모리 세션·외부 로그인 연결 정리 범위.
- 다중 저장소 처리 실패/중단 후 재개와 진행 중 요청과의 충돌 차단.
- 백업 보존 기한 및 복구 시 삭제 기록 재적용.
- 실제 삭제가 확인된 뒤에만 완료 상태와 인증정보 해제, 처리 결과 안내.
- 이 단계에서 단독 프로필 삭제 또는 삭제 완료 API를 열지 않는다.

참고:
https://support.google.com/googleplay/android-developer/answer/13327111
https://law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1029334977
