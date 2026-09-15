"""브랜드 주문 URL이 아직 살아 있는지 확인.

브랜드가 사이트 구조를 바꾸면 배달 모드의 마지막 한 걸음이 조용히 깨진다.
카탈로그를 손볼 때와 배포 전에 돌린다.

    python scripts/check-brand-urls.py
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import brands  # noqa: E402

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def probe(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.status, res.geturl()
    except urllib.error.HTTPError as e:
        return e.code, url
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


bad: list[str] = []
for b in brands.BRANDS:
    status, final = probe(b["order_url"])
    ok = status == 200
    print(f"{'ok  ' if ok else 'FAIL'} {b['name']:<10} {status:<4} {b['order_url']}")
    if not ok:
        bad.append(f"{b['name']} ({b['brand_id']}) → {status} {final}")

print()
if bad:
    print(f"주문 URL {len(bad)}건이 깨졌습니다 — 카탈로그에서 고치거나 빼세요:")
    for line in bad:
        print(f"  - {line}")
    sys.exit(1)
print(f"브랜드 {brands.brand_count()}곳 주문 URL 정상")
