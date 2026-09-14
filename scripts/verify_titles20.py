import sys
sys.path.insert(0, r"C:\Users\zofdh\Projects\just-here\backend")
from app import titles

assert len(titles.PERSONAS) == 20, len(titles.PERSONAS)
r = titles.resolve_persona(
    intent="visit",
    weather="clear",
    left_swipe_count=0,
    right_swipe_count=1,
    decision_time_seconds=1.0,
    distance_m=100,
    place={"menu_name": "차돌", "name": "집", "category": "meat", "tags": [], "delivery_sensitivity": 0.5},
)
print("count", len(titles.PERSONAS))
print("first", r["title"], r["id"])
r2 = titles.resolve_persona(
    intent="delivery",
    weather="rain",
    left_swipe_count=2,
    right_swipe_count=1,
    decision_time_seconds=10.0,
    distance_m=800,
    place={"menu_name": "짜장", "name": "중식", "category": "chinese", "tags": [], "delivery_sensitivity": 0.4},
)
print("storm", r2["title"], r2["id"])
print("ok")
