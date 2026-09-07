"""ELO 공통 커널 — 축구·야구가 **같은 함수**를 쓴다.

🔴 [C7 2026-09-07] 사본 금지. 종전에는 `soccer_elo.replay` 하나뿐이었고,
   야구 자료12 를 만들며 같은 식을 한 번 더 적을 뻔했다. 식이 두 벌이 되면
   한쪽만 고쳐지고, 그때 두 리그의 레이팅이 조용히 갈린다.

레이팅 규약은 표준 ELO 다 — 1500 시작, 400 스케일, 로지스틱 기대값.
바뀌는 것은 K 와 홈 이점뿐이고 둘 다 호출부가 넘긴다.
"""
from __future__ import annotations

import math
from collections import defaultdict

#: 400점 차 = 10배 승산. ELO 의 정의값이라 상수다.
LOG10 = math.log(10.0)
#: 시작 레이팅. 리그 평균이 여기 고정된다.
BASE_RATING = 1500.0


def sigmoid(z: float) -> float:
    """수치 안정 로지스틱. |z|>35 이면 부동소수 한계라 포화시킨다."""
    if z < -35:
        return 0.0
    if z > 35:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def expected_home(diff: float) -> float:
    """레이팅 차(홈 이점 포함) → 홈 기대 승률."""
    return sigmoid(diff * LOG10 / 400.0)


def replay(matches: list[dict], home_adv: float, k: float = 20.0,
           weight=None) -> tuple[dict[str, float], list[tuple]]:
    """시간순 리플레이. **예측은 갱신 전 레이팅으로** 낸다 (walk-forward).

    `matches` 원소: `{"home", "away", "res"("H"|"D"|"A"), "market", "season"}`
    (`market`·`season` 은 백테스트 기록용이고 레이팅에는 안 쓴다).

    `weight(match) -> float` 를 주면 그 경기의 K 를 `k * weight` 로 쓴다.
    🔴 **최근 가중은 여기 한 곳에서만 한다.** 호출부가 각자 감쇠를 구현하면
       그것이 곧 사본이다. 야구 자료12 는 오래된 경기의 K 를 줄여 "오늘 시점
       실력값"을 만든다(`team_elo._decay_weight`).

    반환: `({team: rating}, [(diff, res, market, season), ...])`
    """
    ratings: dict[str, float] = defaultdict(lambda: BASE_RATING)
    records: list[tuple] = []
    for m in matches:
        d = ratings[m["home"]] + home_adv - ratings[m["away"]]
        records.append((d, m["res"], m.get("market"), m.get("season")))
        expected = expected_home(d)
        score = 1.0 if m["res"] == "H" else 0.5 if m["res"] == "D" else 0.0
        k_eff = k * (weight(m) if weight else 1.0)
        delta = k_eff * (score - expected)
        ratings[m["home"]] += delta
        ratings[m["away"]] -= delta
    return dict(ratings), records
