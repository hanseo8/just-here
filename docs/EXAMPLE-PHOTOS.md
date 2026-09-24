# 대표 음식 사진 기록

추천 카드에 쓰는 이미지는 파일마다 **사용 권한**과 **해당 메뉴 사진 여부**를 따로 적는다.
사용 권한이 있어도 그 메뉴 사진이 아니면 메뉴 사진처럼 쓰지 않는다.

| id | 파일 | 출처 | 사용 권한 | 해당 메뉴 사진 | 대표 | 사용 |
| --- | --- | --- | --- | --- | --- | --- |
| doenjang-jjigae | `web/example-photos/doenjang-jjigae.jpg` | [Wikimedia / Alpha](https://commons.wikimedia.org/wiki/File:Korean_stew-Doenjang_jjigae-01.jpg) | CC BY-SA 2.0 | 예 · 된장찌개 | 예 | 검증 메뉴·로컬 미리보기 |
| chicken | `web/example-photos/chicken.jpg` | [Unsplash](https://unsplash.com/photos/fried-chicken-on-white-ceramic-plate-2s6ORaJNNm0) | Unsplash License | 아니오 | 예 | 배달 브랜드 음식 종류 예시만 |
| stew-tomato | `web/example-photos/stew.jpg` | [Unsplash](https://unsplash.com/photos/cooked-food-on-white-ceramic-plate-2kc8bigeqE0) | Unsplash License | 아니오 | 아니오 | 사용하지 않음 |

기계가 읽는 목록은 `web/example-photos.json`이다.

표시 규칙:

- 검증된 메뉴 사진(`photo_role=menu`, `is_menu_photo=true`) 또는 실제 매장 사진(`store`)만 방문 카드에 올린다.
- 브랜드에 일반 음식 사진을 쓰면 사진 위에 `음식 종류 예시`만 표시한다.
- 사진이 없거나 로드에 실패하면 사진 영역을 접는다.
