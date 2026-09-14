"""공유용 페르소나 타이틀 — 최종 20선 (우선순위 매칭 + 에셋 매핑)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))

SPICY_KEYWORDS = ("매운", "마라", "불", "캡사이신", "매움", "spicy", "핫", "매콤")
MEAT_KEYWORDS = (
    "고기",
    "육",
    "삼겹",
    "갈비",
    "치킨",
    "돈가스",
    "구이",
    "튀김",
    "스테이크",
    "pork",
    "beef",
    "chicken",
    "meat",
    "BBQ",
    "바베큐",
)
HERB_KEYWORDS = (
    "샐러드",
    "포케",
    "채식",
    "채소",
    "비건",
    "salad",
    "poke",
    "veggie",
    "그린",
)
CARB_KEYWORDS = (
    "면",
    "국수",
    "라멘",
    "우동",
    "파스타",
    "빵",
    "떡볶이",
    "피자",
    "김밥",
    "덮밥",
    "초밥",
    "pasta",
    "pizza",
    "noodle",
    "udon",
    "ramen",
    "빵",
)
HANGOVER_KEYWORDS = (
    "해장",
    "국밥",
    "순대국",
    "설렁탕",
    "쌀국수",
    "콩나물",
    "북어",
    "찌개",
    "국물",
)
HEAT_KEYWORDS = ("매운", "마라", "이열치열", "뜨거운", "국물", "찌개", "불", "핫")


@dataclass(frozen=True)
class Persona:
    id: str
    title: str
    sub_text: str
    asset_id: str
    sticker: str
    color_a: str
    color_b: str
    priority: int
    group: str  # A|B|C|D

    @property
    def theme(self) -> str:
        return self.asset_id


PERSONAS: list[Persona] = [
    # —— Group A 스와이프/결정 ——
    Persona("first_love", "운명적 첫사랑", "첫눈에 반해버렸어! 운명처럼 다가온 오늘의 원픽", "bg_destiny", "💘", "#FF6B6B", "#FF8E8B", 1, "A"),
    Persona("picky_king", "미식계의 흥선대원군", "아무거나 먹지 않는 철벽 방어!", "bg_ironwall", "🧱", "#4A4A4A", "#2C3E50", 2, "A"),
    Persona("no_hesitation", "고민 0초 노빠꾸 직진러", "내 사전에 고민은 없다", "bg_sprint", "🚦", "#00E676", "#1DE9B6", 3, "A"),
    Persona("decision_paralysis", "결정장애 종결자", "메뉴판을 정독하고 또 정독한 끝에 내린 결단", "bg_overthink", "🌀", "#5C6BC0", "#283593", 4, "A"),
    Persona("meat_myway", "마이웨이 육식주의자", "오직 고기로 직진", "bg_meat", "🥩", "#F44336", "#BF360C", 5, "A"),
    Persona("herbivore", "풀케어 초식주의자", "내 몸은 내가 지킨다", "bg_herb", "🥬", "#66BB6A", "#1B5E20", 6, "A"),
    Persona("chameleon", "변덕쟁이 카멜레온", "질릴 틈을 주지 않는 미식 유목민", "bg_chameleon", "🦎", "#AB47BC", "#6A1B9A", 7, "A"),
    # —— Group B 환경/시간 ——
    Persona("storm_survivor", "폭우 뚫는 생존 먹방러", "비바람이 몰아쳐도 내 밥그릇은 내가 지킨다", "bg_survival", "☔", "#34495E", "#5D6D7E", 8, "B"),
    Persona("night_hyena", "심야의 하이에나", "당신의 진짜 식욕은 그때부터 시작", "bg_midnight", "🐺", "#1A1A2E", "#E94560", 9, "B"),
    Persona("food_nomad", "동해번쩍 맛집 유목민", "국경(지역)도 넘는 프로 탈주러", "bg_nomad", "🧭", "#D4A373", "#FAEDCD", 10, "B"),
    Persona("heat_explorer", "한낮의 용광로 탐험가", "뜨거운 입맛", "bg_heat", "🔥", "#FF7043", "#E65100", 11, "B"),
    Persona("morning_hunter", "모닝 헌터", "얼리버드 미식가", "bg_morning", "🌅", "#FFCC80", "#FF8A65", 12, "B"),
    Persona("weekend_hermit", "나홀로 방구석 셰프", "이불 밖은 위험해", "bg_hermit", "🛌", "#90A4AE", "#455A64", 13, "B"),
    # —— Group C 메뉴/지갑 ——
    Persona("spicy_ranker", "맵부심 상위 1% 랭커", "혈관에 캡사이신이 흐르는 당신", "bg_spicy", "🌶️", "#D32F2F", "#FF0000", 14, "C"),
    Persona("temp_guardian", "절대 온도 수호자", "1도까지 계산하는 철저한 온도 집착러", "bg_temp", "🌡️", "#FF5A00", "#FF9B00", 15, "C"),
    Persona("flexer", "오늘만 사는 플렉서", "지독한 자본주의의 맛", "bg_flex", "💸", "#FFD700", "#F1C40F", 16, "C"),
    Persona("value_hunter", "가성비 파괴자", "알뜰살뜰 소비 챔피언", "bg_value", "🪙", "#26A69A", "#004D40", 17, "C"),
    Persona("carb_addict", "탄수화물 중독자", "에너지는 오직 탄수화물로부터", "bg_carb", "🍞", "#FFB74D", "#EF6C00", 18, "C"),
    Persona("hangover_god", "해장의 신", "국물 한 모금에 영혼을 맡긴다", "bg_hangover", "🥣", "#4DB6AC", "#00695C", 19, "C"),
    # —— Group D 기본 ——
    Persona("instinct_master", "본능 100% 그냥이거 마스터", "귀찮음이 식욕을 이길 순 없지", "bg_basic", "🛋️", "#FF5A00", "#E62E00", 99, "D"),
]

_BY_ID = {p.id: p for p in PERSONAS}


def _text_blob(place: dict) -> str:
    tags = " ".join(place.get("tags") or [])
    return f"{tags} {place.get('menu_name', '')} {place.get('name', '')} {place.get('category', '')} {place.get('kakao_category', '')}"


def _has_any(blob: str, keywords: tuple[str, ...]) -> bool:
    b = blob.lower()
    return any(k.lower() in b for k in keywords)


def _hour_now(hour: int | None = None) -> int:
    if hour is not None:
        return int(hour) % 24
    return datetime.now(KST).hour


def _weekday_now(weekday: int | None = None) -> int:
    if weekday is not None:
        return int(weekday) % 7
    return datetime.now(KST).weekday()


def _is_spicy(place: dict) -> bool:
    return _has_any(_text_blob(place), SPICY_KEYWORDS)


def _is_meat(place: dict) -> bool:
    blob = _text_blob(place)
    if _has_any(blob, HERB_KEYWORDS):
        return False
    cat = (place.get("category") or "").lower()
    if cat in ("meat",):
        return True
    return _has_any(blob, MEAT_KEYWORDS)


def _is_herbivore(place: dict) -> bool:
    return _has_any(_text_blob(place), HERB_KEYWORDS)


def _is_carb(place: dict) -> bool:
    cat = (place.get("category") or "").lower()
    if cat in ("noodle", "western"):
        blob = _text_blob(place)
        if _has_any(blob, ("피자", "pasta", "파스타", "빵", "면", "noodle", "떡볶이", "pizza")):
            return True
        if cat == "noodle":
            return True
    return _has_any(_text_blob(place), CARB_KEYWORDS)


def _is_hangover(place: dict) -> bool:
    return _has_any(_text_blob(place), HANGOVER_KEYWORDS)


def _is_heat_menu(place: dict) -> bool:
    return _has_any(_text_blob(place), HEAT_KEYWORDS)


def _price(place: dict) -> float | None:
    for key in ("price_krw", "estimated_price_per_person"):
        v = place.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def match_reason(*, persona_id: str, intent: str, weather: str, distance_m: float | None, radius_m: int | None) -> str:
    reasons = {
        "first_love": "첫 카드에서 바로 매칭 완료!",
        "picky_king": "10번 이상 거른 끝에 찾은 원픽",
        "no_hesitation": "3초 안에 결정한 초고속 매칭",
        "decision_paralysis": "30번 넘게 고민한 끝에 내린 결단",
        "meat_myway": "고기·구이 시그널로 직진 매칭",
        "herbivore": "클린·채소 중심 메뉴로 매칭",
        "chameleon": "카테고리 유랑 끝, 오늘의 원픽 확정",
        "storm_survivor": f"오늘 비/눈이라 배달 {(radius_m or 1000)}m 이내로 매칭 완료!",
        "night_hyena": "심야 배달 타임 맞춤 매칭",
        "food_nomad": f"현재 위치에서 {int(distance_m or 0)}m — 원거리 탈주 매칭",
        "heat_explorer": "폭염 속 이열치열 메뉴 매칭",
        "morning_hunter": "모닝 타임 얼리버드 매칭",
        "weekend_hermit": "주말 낮, 방구석 배달 매칭",
        "spicy_ranker": "매운맛 시그널이 강한 메뉴로 매칭",
        "temp_guardian": "온도·식감 민감 메뉴라 가까운 곳으로 매칭",
        "flexer": "하이엔드 예산 시그널 매칭",
        "value_hunter": "가성비 최강 메뉴로 매칭",
        "carb_addict": "탄수화물 충전 메뉴로 매칭",
        "hangover_god": "해장 국물 시그널 매칭",
    }
    if persona_id in reasons:
        return reasons[persona_id]
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
    weekday: int | None = None,
    category_path: list[str] | None = None,
    herbivore_streak: int = 0,
    taste: list[str] | None = None,
) -> dict[str, Any]:
    """그룹 A→B→C→D 우선순위로 첫 매칭 페르소나 반환."""
    h = _hour_now(hour)
    wd = _weekday_now(weekday)
    weekend = wd >= 5
    price = _price(place)
    sens = float(place.get("delivery_sensitivity") or 0)
    total_swipes = int(left_swipe_count) + int(right_swipe_count)
    cats = category_path or []
    unique_cats = {c for c in cats if c}

    # —— A ——
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
    elif total_swipes >= 30:
        p = _BY_ID["decision_paralysis"]
    elif _is_meat(place) and not _is_herbivore(place):
        p = _BY_ID["meat_myway"]
    elif _is_herbivore(place):
        # 연속 5회는 계정 히스토리 연동 시 강화. MVP는 클린 메뉴 확정으로 부여.
        p = _BY_ID["herbivore"]
    elif len(unique_cats) >= 4:
        p = _BY_ID["chameleon"]
    # —— B ——
    elif weather in ("rain", "snow") and intent == "delivery":
        p = _BY_ID["storm_survivor"]
    elif (h >= 22 or h <= 4) and intent == "delivery":
        p = _BY_ID["night_hyena"]
    elif distance_m is not None and distance_m >= 5000:
        p = _BY_ID["food_nomad"]
    elif weather == "hot" and _is_heat_menu(place):
        p = _BY_ID["heat_explorer"]
    elif 6 <= h < 9:
        p = _BY_ID["morning_hunter"]
    elif weekend and 11 <= h < 15 and intent == "delivery":
        p = _BY_ID["weekend_hermit"]
    # —— C ——
    elif _is_spicy(place):
        p = _BY_ID["spicy_ranker"]
    elif sens >= 0.85:
        p = _BY_ID["temp_guardian"]
    elif price is not None and price >= 30000:
        p = _BY_ID["flexer"]
    elif price is not None and price <= 10000:
        p = _BY_ID["value_hunter"]
    elif _is_carb(place):
        p = _BY_ID["carb_addict"]
    elif _is_hangover(place) and (
        (weekend and h < 12) or (6 <= h < 11) or (h >= 22 or h <= 4)
    ):
        p = _BY_ID["hangover_god"]
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
        "group": p.group,
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
            "group": p.group,
        }
        for p in PERSONAS
    ]
