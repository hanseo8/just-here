"""검증 메뉴 카탈로그 형식 검사. 랭킹 연결 여부는 보지 않는다."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import data_dir  # noqa: E402
from app.verified_menus import REQUIRED, catalog_path, load_catalog  # noqa: E402

root = Path(__file__).resolve().parents[1]
example = root / "data" / "verified-menus.songdo.example.json"
live = catalog_path()

ex = load_catalog(example)
print(f"양식: {ex['count']}행 통과 (example 행은 제외) example_file={ex.get('example_file')}")
if ex["count"] != 0:
    print("FAIL 양식 파일의 예시 행이 검증 메뉴로 들어갔다")
    sys.exit(1)

cat = load_catalog(live if live.exists() else example)
print(f"실제 입력 경로: {live}")
print(f"DATA_DIR: {data_dir()}")
print(f"영구 디스크 여부(DATA_DIR 설정): {cat.get('persistent')}")
print(f"입력: {cat['count']}행 검증됨 ready={cat['ready']} wired={cat.get('wired_to_ranking')}")
print("필수:", ", ".join(REQUIRED), "+ source_url|source_note")
print("20~30개는 실험 규모이지 품질 보장이 아니다.")
if cat["ready"] or cat.get("wired_to_ranking"):
    print("FAIL 아직 랭킹에 연결하면 안 된다")
    sys.exit(1)
if live.name.endswith(".example.json"):
    print("FAIL 예시 파일을 운영 입력 경로로 쓰면 안 된다")
    sys.exit(1)
print("통과")
