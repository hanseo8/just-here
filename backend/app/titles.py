"""공유용 페르소나 타이틀 — 우선순위 매칭 + 에셋 매핑."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))

SPICY_KEYWORDS = ("매운", "마라", "불", "캡사이신", "매움", "spicy", "핫")


@dataclass(frozen=True)
class Persona:
    id: str
    title: str
    sub_text: str
    asset_id: str  # CSS theme / Asset ID (bg_*)
    sticker: str  # emoji placeholder until PNG/Lottie
    color_a: str
    color_b: str
    priority: int

    @property
    def theme(self) -> str:
        return self.asset_id


PERSONAS: list[Persona] = [
    Persona(
        "first_love",
        "운명적 첫사랑",
        "첫눈에 반해버렸어! 운명처럼 다가온 오늘의 원픽",
        "bg_destiny",
        "💘",
        "#FF6B6B",
        "#FF8E8B",
        1,
    ),
    Persona(
        "picky_king",
        "미식계의 흥선대원군",
        "아무거나 먹지 않는 철벽 방어! AI도 땀 뻘뻘 흘리게 만든 까다로운 입맛",
        "bg_ironwall",
        "🧱",
        "#4A4A4A",
        "#2C3E50",
        2,
    ),
    Persona(
        "no_hesitation",
        "고민 0초 노빠꾸 직진러",
        "내 사전에 고민은 없다. 목표가 정해지면 일단 걷고 보는 타입",
        "bg_sprint",
        "🚦",
        "#00E676",
        "#1DE9B6",
        3,
    ),
    Persona(
        "storm_survivor",
        "폭우 뚫는 생존 먹방러",
        "비바람이 몰아쳐도 내 밥그릇은 내가 지킨다!",
        "bg_survival",
        "☔",
        "#34495E",
        "#5D6D7E",
        4,
    ),
    Persona(
        "night_hyena",
        "심야의 하이에나",
        "모두가 잠든 시간, 당신의 식욕은 이제부터 시작됩니다.",
        "bg_midnight",
        "🐺",
        "#1A1A2E",
        "#E94560",
        5,
    ),
    Persona(
        "food_nomad",
        "동해번쩍 맛집 유목민",
        "맛있는 걸 위해서라면 국경(지역)도 넘는 프로 탈주러",
        "bg_nomad",
        "🧭",
        "#D4A373",
        "#FAEDCD",
        6,
    ),
    Persona(
        "spicy_ranker",
        "맵부심 상위 1% 랭커",
        "혈관에 캡사이신이 흐르는 당신, 오늘 화장실은 포기하셨군요?",
        "bg_spicy",
        "🌶️",
        "#D32F2F",
        "#FF0000",
        7,
    ),
    Persona(
        "temp_guardian",
        "절대 온도 수호자",
        "식은 음식은 용서 못 해! 1도까지 계산하는 치밀함",
        "bg_temp",
        "🌡️",
        "#FF5A00",
        "#FF9B00",
        8,
    ),
    Persona(
        "flexer",
        "오늘만 사는 플렉서",
        "통장 잔고보다 내 입이 즐거운 게 먼저! 지독한 자본주의의 맛",
        "bg_flex",
        "💸",
        "#FFD700",
        "#F1C40F",
        9,
    ),
    Persona(
        "instinct_master",
        "본능 100% 그냥여기 마스터",
        "귀찮음이 식욕을 이길 순 없지. 앱이 골라주는 대로 편하게 먹는 게 최고!",
        "bg_basic",
        "🛋️",
        "#FF5A00",
        "#E62E00",
        99,
    ),
]

_BY_ID = {p.id: p for p in PERSONAS}


def _text_blob(place: dict) -> str:
    tags = " ".join(place.get("tags") or [])
    return f"{tags} {place.get('menu_name', '')} {place.get('name', '')} {place.get('category', '')}"


def _is_spicy(place: dict) -> bool:
    blob = _text_blob(place).lower()
    return any(k.lower() in blob for k in SPICY_KEYWORDS)


def _hour_now(hour: int | None = None) -> int:
    if hour is not None:
        return int(hour) % 24
    return datetime.now(KST).hour


def match_reason(
    *,
    persona_id: str,
    intent: str,
    weather: str,
    distance_m: float | None,
    radius_m: int | None,
) -> str:
    if persona_id == "first_love":
        return "첫 카드에서 바로 매칭 완료!"
    if persona_id == "picky_king":
        return "10번 이상 거른 끝에 찾은 원픽"
    if persona_id == "no_hesitation":
        return "3초 안에 결정한 초고속 매칭"
    if persona_id == "storm_survivor":
        r = radius_m or 1000
        return f"오늘 비/눈이라 배달 {r}m 이내로 매칭 완료!"
    if persona_id == "night_hyena":
        return "심야 타임 맞춤 매칭"
    if persona_id == "food_nomad":
        d = int(distance_m or 0)
        return f"현재 위치에서 {d}m — 원거리 탈주 매칭"
    if persona_id == "spicy_ranker":
        return "매운맛 시그널이 강한 메뉴로 매칭"
    if persona_id == "temp_guardian":
        return "온도·식감 민감 메뉴라 가까운 곳으로 매칭"
    if persona_id == "flexer":
        return "하이엔드 예산 시그널 매칭"
    mode = "방문" if intent == "visit" else "배달"
    if weather in ("rain", "snow"):
        return f"날씨·{mode} 조건으로 근처 매칭 완료!"
    return f"{mode} 모드 기준, 지금 위치 근처로 매칭 완료!"


def resolve_persona(
    *,
    intent: str,
    weather: str,
    left_swipe_count: int,
    right_swipe_count: int,
    decision_time_seconds: float | None,
    distance_m: float | None,
    place: dict[str, Any],
    hour: int | None = None,
) -> dict[str, Any]:
    """우선순위 1→N 순서로 첫 매칭 페르소나 반환."""
    h = _hour_now(hour)
    price = place.get("price_krw") or place.get("estimated_price_per_person")
    sens = float(place.get("delivery_sensitivity") or 0)

    if right_swipe_count == 1 and left_swipe_count == 0:
        p = _BY_ID["first_love"]
    elif left_swipe_count >= 10:
        p = _BY_ID["picky_king"]
    elif (
        intent == "visit"
        and decision_time_seconds is not None
        and decision_time_seconds < 3
    ):
        p = _BY_ID["no_hesitation"]
    elif weather in ("rain", "snow") and intent == "delivery":
        p = _BY_ID["storm_survivor"]
    elif h >= 22 or h <= 4:
        p = _BY_ID["night_hyena"]
    elif distance_m is not None and distance_m >= 5000:
        p = _BY_ID["food_nomad"]
    elif _is_spicy(place):
        p = _BY_ID["spicy_ranker"]
    elif sens >= 0.85:
        p = _BY_ID["temp_guardian"]
    elif isinstance(price, (int, float)) and price >= 30000:
        p = _BY_ID["flexer"]
    else:
        p = _BY_ID["instinct_master"]

    reason = match_reason(
        persona_id=p.id,
        intent=intent,
        weather=weather,
        distance_m=distance_m,
        radius_m=None,
    )
    return {
        "id": p.id,
        "title": p.title,
        "sub_text": p.sub_text,
        "theme": p.asset_id,
        "asset_id": p.asset_id,
        "sticker": p.sticker,
        "colors": [p.color_a, p.color_b],
        "priority": p.priority,
        "match_reason": reason,
    }


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "title": p.title,
            "sub_text": p.sub_text,
            "theme": p.asset_id,
            "asset_id": p.asset_id,
            "sticker": p.sticker,
            "colors": [p.color_a, p.color_b],
            "priority": p.priority,
        }
        for p in PERSONAS
    ]
