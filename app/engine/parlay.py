"""파레이 — EV 플러스 레그만으로 2~4폴더 전수 탐색, EV순 상위 반환."""

from itertools import combinations
from math import prod


def best_parlays(
    legs: list[dict], min_legs: int = 2, max_legs: int = 4, top: int = 3
) -> list[dict]:
    """legs: [{game_id, pick, p, odds, ev}] (ev > 0인 레그만 전달할 것).

    같은 경기 레그 2개가 들어간 조합은 제외. EV 내림차순 상위 top개 반환.
    """
    candidates = [leg for leg in legs if leg["ev"] > 0]
    parlays = []
    for n in range(min_legs, min(max_legs, len(candidates)) + 1):
        for combo in combinations(candidates, n):
            if len({leg["game_id"] for leg in combo}) < n:
                continue  # 동일 경기 중복 레그 금지
            p = prod(leg["p"] for leg in combo)
            odds = prod(leg["odds"] for leg in combo)
            parlays.append({
                "legs": [{"game_id": leg["game_id"], "pick": leg["pick"]} for leg in combo],
                "p": p,
                "odds": round(odds, 4),
                "ev": p * odds - 1.0,
            })
    parlays.sort(key=lambda x: x["ev"], reverse=True)
    return parlays[:top]
