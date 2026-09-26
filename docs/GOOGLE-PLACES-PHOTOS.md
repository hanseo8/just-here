# Google 장소 사진 파일럿

방문 추천 카드에 음식점의 실제 분위기 사진을 보여주기 위한 선택 기능이다.

## 동작

- 카카오에서 받은 실상호의 이름·주소·좌표로 Google Places API (New) Text Search를 수행한다.
- 이름이 맞고 좌표가 250m 이내인 장소만 연결한다.
- 사진은 `/v1/google/place-photo`에서 요청할 때 가져오며 파일이나 사진 이름을 저장하지 않는다.
- 사진이 없거나 매칭이 실패하면 기존 사진 없는 카드로 돌아간다.
- 실제 메뉴 사진이라고 표시하지 않고 `Google 지도 사진`으로 출처를 표시한다.
- 상세정보에는 Google 지도에서 가게를 확인할 수 있는 링크를 둔다.

## 환경변수

```dotenv
GOOGLE_PLACES_PHOTOS=on
GOOGLE_MAPS_API_KEY=서버 전용 키
```

Google Places API (New)를 활성화하고 결제 계정과 API 제한을 설정한 뒤에 켠다. 브라우저 코드에는 키를 넣지 않는다.

## 정책 메모

Google Places 사진을 보여줄 때는 사진 저작자 표기와 Google 지도 연결을 함께 제공해야 한다. 사진 이름과 콘텐츠를 영구 저장하거나 자체 이미지 저장소로 복사하지 않는다.

- https://developers.google.com/maps/documentation/places/web-service/place-photos
- https://developers.google.com/maps/documentation/places/web-service/policies
