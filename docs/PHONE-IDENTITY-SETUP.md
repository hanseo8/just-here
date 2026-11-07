# 보상 참여 휴대폰 본인인증 · 포트원 V2 준비

상태: 코드·모의 인증 검증 완료. 준비 화면과 서버 차단을 웹에 반영하며, 실제 계약/운영 인증/네이티브 복귀 구현·모의 검증은 완료했으며 실기기 검수는 미완료다.

## 사용자 흐름
추천은 비로그인 → MY → 인증 안내/동의 → 통신사 본인인증 → 서버 재조회 → MY 복귀 → 베타 참여 신청.
인증만으로 선정·포인트 적립·송금되지 않는다. 기존 지급 한도/선정/관리자 승인은 유지한다.
같은 DI로 재인증하면 기존 UID를 복구한다. 기존 지갑/영수증/베타 기록 병합 충돌 시 자동 지급 없이 중단한다.

## 계약 및 설정
1. 포트원에서 V2 상점과 휴대폰 본인인증 채널(다날 또는 KCP)을 준비한다. DI 제공이 필요하다. CI만 있는 채널은 접수하지 않는다.
2. 승인 도메인 justthis.co.kr, 웹 복귀 URL https://justthis.co.kr/my 와 앱 브라우저 복귀 URL https://justthis.co.kr/static/identity-native.html 을 등록하고 모바일 리디렉션 설정을 확인한다.
3. Render 환경 변수: PORTONE_STORE_ID, PORTONE_CHANNEL_KEY, PORTONE_API_SECRET, REWARD_IDENTITY_HMAC_KEY(무작위 32바이트 이상).
4. 비밀키를 채팅/깃/브라우저 코드에 넣지 않는다. HMAC 키는 동일인 중복 방지·계정 복구의 기준이므로 안전하게 백업하고 임의 교체하지 않는다.
5. REWARD_IDENTITY_REQUIRED=on(새 코드 기본값), REWARD_IDENTITY_ENABLED=on(계약·실제 채널 및 개인정보 안내 검토 후에만).
6. LIVE 채널만 서버에서 인정한다. TEST 채널·DI 미제공·인증 미완료·다른 채널·다른 계정의 인증 시도는 거절한다.

## 운영 전 남은 검증
- 실제 계약 정보가 없으므로 인증창/통신사 결과 검증을 실제로 실행하지 않았다. 자동 테스트는 모의 provider 결과이다.
- 웹: 인증 취소/실패/모바일 리디렉션/뒤로가기/같은 사람 재인증·다른 기기 복구/연결 중 인터넷 끊김 검수.
- 네이티브: 외부 브라우저의 인증 전용 페이지 → justthis://identity-complete → MY 복귀 브리지를 구현했다. 요청 ID·설치에 저장한 무작위 state·원래 UID·만료 시간을 대조하고 서버 complete 결과만 인증으로 인정한다. 앱 재시작 후 준비된 결과를 재개하며 통신 실패 시 결과 확인만 재시도한다. 구버전 브리지는 인증을 시작하지 않는다. 실제 운영 채널·실기기 검수 및 새 APK/AAB 빌드는 미완료이며 심사 준비 완료가 아니다.
- 개인정보처리방침·동의문·사업자 계약의 수탁/제공 구분, 보존·파기 기간을 운영 기준으로 확정하고 게시한다. UI 안내만으로 법적 준비 완료 처리하지 않는다.
- 기존 계정 삭제 요청 preflight에 인증 레코드/시도 건수를 포함했다. 실제 계정 삭제 실행기는 별도 미완료 작업이다.
- 원문 이름/생년월일/전화번호/CI/DI는 우리 DB에 저장하지 않는다. 서버에는 DI의 전용키 HMAC, UID, 검증 시각/요청 ID만 보관한다. 인증 시도는 계정당 시간당3회로 제한하고, 만료된 시도도 빈도 판정을 위해24시간 유지한 뒤 다음 시작 요청에서 정리한다.
- REWARD_IDENTITY_REQUIRED=off는 이전 카카오 호환 회귀 테스트용이다. 신규 보상 운영을 이 모드로 활성화하지 않는다.

## 테스트
python -m scripts.check-reward-identity
기존 호환 모드: check-rewards-api, check-beta-campaign, check-payouts, check-pilot-limits.
공식 문서: https://developers.portone.io/opi/ko/extra/identity-verification/readme-v2

## 2026-11-07 네이티브 복귀 구현 검증
- 외부 브라우저에는 UID·게스트 토큰·원문 개인정보를 전달하지 않는다. 웹의 성공/취소 쿼리나 딥링크는 복귀 신호일 뿐이다.
- 앱 scheme/host/path, 중복 파라미터, 요청 ID, 32바이트 난수 state, UID, 10분 만료를 검사한다.
- 인증창 종료 뒤 늦게 도착하는 정상 복귀, cold launch, 취소·브라우저 열기 실패, 계정 변경, 서버 결과 확인 재시도를 모의 검사했다.
- 전용 정적 페이지(identity-native.html/js/css)는 웹 배포가 먼저 필요하다. 네이티브 정적 번들은 새로 생성했지만 기존 APK/AAB는 여전히 이전 버전이다.
- 실제 계약·LIVE 채널·DI 제공 및 리디렉션 허용 설정 확인 전 REWARD_IDENTITY_ENABLED를 켜지 않는다. 운영 데이터나 보상 지급 조건을 변경하지 않았다.

검사 명령:
- node scripts/check-reward-identity-ui.cjs
- node scripts/check-reward-identity-native-ui.cjs
- node scripts/check-identity-native-page.cjs
- npm run bundle --prefix mobile
- npm run check --prefix mobile
- python -m scripts.check-reward-identity

SDK 리디렉션 형식: https://developers.portone.io/sdk/ko/v2-sdk/identity-verification-request?v=v2
