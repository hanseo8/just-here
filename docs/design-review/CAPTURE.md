# 추천 화면 캡처 기록

캡처 스크립트: `scripts/capture-design-review.js`

방식:

1. Chrome headless + CDP `Emulation.setDeviceMetricsOverride`
2. `Page.captureScreenshot` — 브라우저 창이 아니라 **지정 viewport만** 저장
3. 결과 파일명: `{state}-{width}x{height}.png`

| 화면 | URL | viewport |
| --- | --- | --- |
| 사진 카드 | `/?design=photo` | 390×844, 360×640 |
| 브랜드 예시 사진 | `/?design=brand` | 390×844, 360×640 |
| 사진 없음 | `/?design=nophoto` | 390×844, 360×640 |
| 긴 이름·가격 미확인 | `/?design=longname` | 390×844, 360×640 |
| 세 후보 거절 | `/?design=adjust` | 390×844, 360×640 |
| 선택 완료 | `/?design=done` | 390×844, 360×640 |

이전 `design-*-390.png` 중 일부는 넓은 캔버스에 앱 컬럼만 들어가 있어 폐기한다.
