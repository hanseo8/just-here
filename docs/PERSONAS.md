# 공유 페르소나 · 에셋 매핑

배경 = CSS 그라데이션 (Asset ID) · 스티커 = 이모지 플레이스홀더 (추후 PNG/Lottie)

| Asset ID | 타이틀 | Hex | Sticker |
|----------|--------|-----|---------|
| `bg_destiny` | 운명적 첫사랑 | `#FF6B6B` → `#FF8E8B` | 💘 |
| `bg_ironwall` | 미식계의 흥선대원군 | `#4A4A4A` → `#2C3E50` | 🧱 |
| `bg_sprint` | 고민 0초 노빠꾸 직진러 | `#00E676` → `#1DE9B6` | 🚦 |
| `bg_survival` | 폭우 뚫는 생존 먹방러 | `#34495E` → `#5D6D7E` | ☔ |
| `bg_midnight` | 심야의 하이에나 | `#1A1A2E` → `#E94560` | 🐺 |
| `bg_nomad` | 동해번쩍 맛집 유목민 | `#D4A373` → `#FAEDCD` | 🧭 |
| `bg_spicy` | 맵부심 상위 1% 랭커 | `#D32F2F` → `#FF0000` | 🌶️ |
| `bg_temp` | 절대 온도 수호자 | `#FF5A00` → `#FF9B00` | 🌡️ |
| `bg_flex` | 오늘만 사는 플렉서 | `#FFD700` → `#F1C40F` | 💸 |
| `bg_basic` | 본능 100% 그냥여기 마스터 | `#FF5A00` → `#E62E00` | 🛋️ |

PNG 교체 시: `web/assets/stickers/{asset_id}.png` 넣고 `.receipt-sticker`에 `background-image`만 바꾸면 됨.
