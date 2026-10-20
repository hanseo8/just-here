# 그냥여기 Android·iOS

Capacitor 네이티브 프로젝트. 현재는 개발·검증용이며 스토어 제출 가능한 릴리스가 아니다.

## 빌드
Node 22+ 환경에서 mobile 폴더에서 `npm ci`, `npm run sync`, `npm run check`를 실행한다.
Android: SDK 36과 JDK 21 환경에서 `android/gradlew -p android assembleDebug`.
iOS: Mac/Xcode 26+에서 `npm run sync` 후 `npm run ios`. Windows에서는 iOS 프로젝트 생성만 가능하고 컴파일 검증은 하지 못했다.
macOS 빌드 환경이 없다면 사용자 소유 계정으로 클라우드 macOS 빌드를 마련해야 한다. 이번에 유료 서비스 등록·결제는 하지 않았다.

## 구조
- `www/`는 web/에서 만든 고객 전용 번들. 생성물은 커밋하지 않는다.
- 관리자·점주 운영 도구·영수증 원본·운영 데이터는 앱에 넣지 않는다.
- `src/native.js`: API 목적지 지정, 네이티브 위치·사진 선택, 외부 HTTPS 브라우저, Android 뒤로 가기.
- `scripts/normalize-ios.cjs`: Windows CLI가 생성한 Swift 패키지 경로를 macOS에서도 읽도록 정규화한다. `npm run sync`에서 수행한다.
- `kr.co.justthis.app`은 개발용 후보 ID. 실제 게시자 계정의 앱 ID·서명 설정을 확인하기 전 확정하지 않는다.
- 기본 생성 아이콘·런치 화면은 출시용 브랜딩 검수 전이다.

## 릴리스 보류 항목
- 네이티브 카카오 로그인 및 앱 복귀/계정 복구는 아직 미검증이다. 웹 OAuth 콜백을 그대로 사용하면 네이티브 앱에서 연결된다고 판단하지 않는다.
- 실제 계정 삭제 실행·토큰 철회·외부 인증 해지·결과 통지는 미구현이다. 접수·검토 화면만으로 심사 요건 충족을 주장하지 않는다.
- 디바이스 위치 거절·재허용, 촬영/사진 선택, 키보드/스크롤, 외부 지도, 재시작 후 인증을 실제 Android/iPhone에서 검수해야 한다.
- 개인정보 처리방침의 실제 운영자·문의처와 삭제/지급/쿠폰/백업 보존 범위를 확정해야 한다. 스토어 개인정보 공개·Google Data safety 역시 실제 데이터 처리와 대조한다.
- 앱 내 포인트는 디지털 콘텐츠 구매 수단으로 확장하지 않았다. 제휴·보상 활성화는 실제 계약·예산 검토 뒤 별도 결정한다.
- Android AAB 업로드 키·Play Console과 Apple Developer·App Store Connect 계정, iOS 인증서·프로비저닝이 필요하다. 비밀키는 레포에 저장하지 않는다.

`npm run release:check`는 미확인 증거가 있으면 실패한다. 항목을 사실 확인 없이 true로 바꾸지 않는다. 테스트 통과나 디버그 APK 생성은 심사 승인·보안 보장과 다르다.

## 공식 참고
- https://capacitorjs.com/docs/getting-started/environment-setup
- https://developer.apple.com/app-store/review/guidelines/
- https://developer.apple.com/support/offering-account-deletion-in-your-app/
- https://support.google.com/googleplay/android-developer/answer/13327111
