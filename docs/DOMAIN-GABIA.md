# justthis.co.kr 도메인 연결 (가비아)

도메인은 가비아에 두고, **앱 서버(호스팅)** 에 DNS로 연결합니다.  
가비아 로그인·DNS 수정은 본인 계정에서만 가능합니다. 아래 레코드를 그대로 넣으면 됩니다.

---

## 0. 한 줄 요약

1. 앱을 Render(또는 Railway)에 배포 → `xxxx.onrender.com` 주소 받기  
2. 가비아 DNS에 `www` CNAME 추가  
3. 루트(`justthis.co.kr`)는 `www`로 포워딩  
4. 환경변수 `PUBLIC_BASE_URL=https://www.justthis.co.kr`

---

## 1. 앱 배포 (Render 추천)

1. https://render.com 가입 (GitHub 연동)  
2. 이 레포 `just-here` Push  
3. **New → Blueprint** 또는 **Web Service** → Docker  
4. 루트 `Dockerfile` 사용  
5. 배포 후 주소 예: `https://just-here-xxxx.onrender.com`  
6. Environment:
   - `PUBLIC_BASE_URL` = `https://www.justthis.co.kr`
   - `KAKAO_REST_API_KEY` = (있으면)

헬스체크: `https://just-here-xxxx.onrender.com/health`

---

## 2. 가비아 DNS 설정

가비아 로그인 → **My가비아** → **서비스 관리** → `justthis.co.kr` → **DNS 관리**

### A) www (필수)

| 호스트 | 타입 | 값 / 연결 |
|--------|------|-----------|
| `www` | **CNAME** | `just-here-xxxx.onrender.com` |

(끝에 점 `.` 을 요구하면 `just-here-xxxx.onrender.com.` )

### B) 루트 도메인 justthis.co.kr

가비아는 apex A/ALIAS가 애매할 수 있어 **웹 포워딩**이 제일 안전합니다.

| 방식 | 설정 |
|------|------|
| 권장 | **URL 포워딩(301)** : `justthis.co.kr` → `https://www.justthis.co.kr` |
| 대안 | Render가 안내하는 IP가 있으면 `@` **A 레코드** |

### C) 확인

```text
https://www.justthis.co.kr/health
→ {"ok": true, ...}
```

전파는 보통 수분~수시간.

---

## 3. (선택) Cloudflare 경유

가비아 DNS 대신 Cloudflare NS로 바꾸면 apex CNAME도 편합니다.

1. Cloudflare에 `justthis.co.kr` 추가  
2. 가비아 네임서버를 Cloudflare 값으로 변경  
3. Cloudflare DNS:
   - `www` CNAME → `just-here-xxxx.onrender.com` (Proxied)
   - `@` CNAME → `just-here-xxxx.onrender.com` (Proxied, CNAME flattening)

---

## 4. 체크리스트

- [ ] Render 배포 성공 (`/health` OK)
- [ ] 가비아 `www` CNAME 등록
- [ ] 루트 → www 포워딩
- [ ] `PUBLIC_BASE_URL=https://www.justthis.co.kr`
- [ ] Duo/영수증 공유 링크가 `justthis.co.kr` 로 나가는지 확인
- [ ] (카카오) 플랫폼 도메인에 `www.justthis.co.kr` 등록

---

## 5. 로컬에서 쓰는 포트

개발은 `8010` (`run.bat`). 도메인과 무관합니다.
