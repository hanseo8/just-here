# CTO Kickoff — 마스터 문서 분석 & 착수 결정

Date: 2026-09-13  
Input: Cursor용 마스터 문서「그냥이거」(섹션 3.1에서 절단)

---

## 1. 판정 요약

| 항목 | 마스터 문서 | 레포 현황 (`just-here`) | CTO 결정 |
|------|-------------|-------------------------|----------|
| 브랜드 | 그냥이거 | **그냥여기** (PRD locked) | **그냥여기** 유지. 슬로건만 정렬 |
| 클라이언트 | RN / Flutter | **웹 스와이프 MVP** | **웹 유지 → 런칭**. 네이티브는 DAU 검증 후 |
| DB | Firebase Firestore | Postgres(+PostGIS) 설계 + 인메모리 MVP | **런타임 = 인메모리→Postgres**. Firebase는 Auth/푸시용. Firestore 스키마는 호환 JSON으로 문서화만 |
| 시드 | (미기재) | 인천 송도 | 송도 유지 |
| 핵심루프 | 스와이프 → 딥링크 / Nope → rejection_tags | 거의 구현됨 | **갭만 메움** (아래) |

**원칙:** DAU 1,000 전에 스택 갈아엎지 않는다. 마스터 문서의 UX 계약을 웹 MVP에 먼저 완성한다.

---

## 2. 마스터 문서 → 구현 갭 (우선순위)

1. **스마트 토글 자동 모드** — 우천/야간(22시+) → 배달, 맑은 피크 → 방문  
2. **토글 시 덱 flush + 재호출** — 이미 재호출 있음, flush UX 강화  
3. **Swipe Right** — 폭죽 + **즉시** 딥링크 (중간 확인 화면 제거)  
4. **Swipe Left** — rejection_tags 페널티 (인메모리 존재 → 이후 Firebase/PG 동기화)  
5. **배달 ETA 라벨** — “도보 N분” / “배달 약 N분”  
6. **Firestore JSON 스키마** — 문서 완성 (런타임 이전은 보류)

절단된 섹션(딥링크 상세·반경 수식 등)은 기존 [MVP-PRD.md](./MVP-PRD.md) · [DB-SCHEMA.md](./DB-SCHEMA.md)를 정본으로 사용.

---

## 3. 이번 스프린트 산출물

- `/v1/context` — 날씨·시각 → `suggested_intent`
- 피드 ETA 라벨 개선
- 웹: 자동 토글 · Match 폭죽 · Let’s Go 즉시 핸드오프
- [FIRESTORE-SCHEMA.md](./FIRESTORE-SCHEMA.md) — 마스터 3.1 보완

---

## 4. 하지 않는 것 (이번 턴)

- React Native / Flutter 신규 스캐폴드
- Firestore 실제 연동
- 브랜드 리네임 전면 교체
