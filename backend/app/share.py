"""식탐 영수증 공유 (인메모리 MVP)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Receipt:
    id: str
    title: str
    place_name: str
    menu_name: str
    intent: str
    tier: str
    created_at: str
    sub_text: str = ""
    theme: str = "bg_basic"
    match_reason: str = ""
    persona_id: str = ""
    sticker: str = "🛋️"
    asset_id: str = "bg_basic"
    extra: dict[str, Any] = field(default_factory=dict)


RECEIPTS: dict[str, Receipt] = {}


def create_receipt(
    *,
    title: str,
    place_name: str,
    menu_name: str,
    intent: str,
    tier: str = "",
    sub_text: str = "",
    theme: str = "bg_basic",
    match_reason: str = "",
    persona_id: str = "",
    sticker: str = "🛋️",
    asset_id: str = "bg_basic",
    extra: dict[str, Any] | None = None,
) -> Receipt:
    aid = asset_id or theme or "bg_basic"
    r = Receipt(
        id=uuid.uuid4().hex[:10],
        title=title,
        place_name=place_name,
        menu_name=menu_name,
        intent=intent,
        tier=tier,
        created_at=datetime.now(timezone.utc).isoformat(),
        sub_text=sub_text,
        theme=aid,
        match_reason=match_reason,
        persona_id=persona_id,
        sticker=sticker,
        asset_id=aid,
        extra=extra or {},
    )
    RECEIPTS[r.id] = r
    return r


def get_receipt(receipt_id: str) -> Receipt | None:
    return RECEIPTS.get(receipt_id)


def share_text(r: Receipt, share_url: str) -> str:
    mode = "방문" if r.intent == "visit" else "배달"
    lines = [
        "나만의 식탐 영수증",
        f"{r.sticker} 「{r.title}」",
    ]
    if r.sub_text:
        lines.append(r.sub_text)
    lines.append(f"{r.place_name} · {r.menu_name} ({mode})")
    if r.match_reason:
        lines.append(f"매칭: {r.match_reason}")
    lines.extend(
        [
            "",
            "메뉴 고민은 사치, 너도 그냥여기 어때?",
            share_url,
        ]
    )
    return "\n".join(lines)


from .config import public_base_url


def share_payload(r: Receipt, base_url: str) -> dict:
    base = public_base_url(base_url)
    url = f"{base}/r/{r.id}"
    return {
        "id": r.id,
        "title": r.title,
        "sub_text": r.sub_text,
        "theme": r.theme,
        "asset_id": r.asset_id or r.theme,
        "sticker": r.sticker,
        "match_reason": r.match_reason,
        "persona_id": r.persona_id,
        "place_name": r.place_name,
        "menu_name": r.menu_name,
        "intent": r.intent,
        "share_url": url,
        "share_path": f"/r/{r.id}",
        "share_text": share_text(r, url),
    }
