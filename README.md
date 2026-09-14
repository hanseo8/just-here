# 그냥여기 (Just Here)

고민 끝. **오늘 점심은 그냥여기 어때?**

## 북극성

**런칭 → DAU 1,000.**  
허브 시드 **인천 송도(풀)** · 이용 **전국(라이트)**.

## MVP v0.2 실행

```bat
cd backend
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

`KAKAO_REST_API_KEY` 넣으면 전국에서 실상호. 없으면 라이트 폴백.

→ http://127.0.0.1:8010

## Docs

| | |
|--|--|
| [도메인·가비아](docs/DOMAIN-GABIA.md) | **justthis.co.kr** DNS |
| [경험 티어](docs/EXPERIENCE-TIERS.md) | 송도 풀 / 전국 라이트 |
| [런칭](docs/LAUNCH.md) | DAU 1000 |
| [시드](docs/SEED-MARKETS.md) | 송도 동 세분화 |
| [PRD](docs/MVP-PRD.md) | 제품 명세 |
