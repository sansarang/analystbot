"""[PROB-1] 확률 뼈대는 **시장**이다. 조정은 코드가, 서술만 LLM이.

사용자 결정 2026-09-13(결정 1):
    `p = 시장 확률(디빅) → 검증된 변수로 코드가 ±%p → LLM은 서술만`
    **(b)·(c) 금지 — LLM 프롬프트에 배당·시장확률·괴리 숫자를 넣지 않는다.**

🔴 **왜 뼈대를 바꿨나.** 운영 원장 178경기(`is_final`·채점 완료):
```
판정 확률 AUC 0.5122 [0.426, 0.601] · 브라이어 0.2537  ← 50%로 찍는 것보다 나쁘다
시장 확률 AUC 0.6421 [0.545, 0.734] · 브라이어 0.2394  ← 유일하게 유의
자료12 Elo AUC 0.440~0.477 (MLB) · 혼합하면 더 나빠진다 ← 대체재가 될 수 없다
```

⚠️ **디빅을 여기서 다시 구현하지 않는다.** `pipeline._market_probs` 가 북별로
   마진을 제거하고 평균까지 낸다(`market_edge.implied_probs` 사용). 이 모듈은
   그 결과 dict 를 받아 쓸 뿐이다.
⚠️ **승률 클립을 다시 적지 않는다.** `scoring.cap_probability` 가 원본이다.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: 조정 변수 표 — 사용자 결정 1-2 그대로. **종목 분기문이 아니라 조회다.**
#  각 항목: (jg 키, 1단위당 %p, 상한 %p)
#  🔴 이 표가 원본이다. 값을 다른 곳에 옮겨 적지 않는다.
ADJ_RULES: dict[str, dict[str, tuple[str, float, float]]] = {
    "baseball": {
        # 선발 변경(T4)은 방향이 상황에 달렸다 — 크기만 정하고 부호는 호출부가 준다
        "선발변경": ("starter_changed", 6.0, 6.0),
        "주전결장": ("out_starters", -1.5, -5.0),
        "필승조연투": ("bullpen_b2b", -1.0, -3.0),
        "이동연전": ("trip_day", -1.0, -1.0),
    },
    "soccer": {
        "주전결장": ("out_starters", -1.5, -6.0),
        "핵심결장": ("out_keyman", -2.0, -2.0),
        "짧은휴식": ("rest_days", -2.0, -2.0),
        "주중원정": ("midweek_away", -2.0, -2.0),
    },
}

#: 야구 3종목. 🔴 원본은 `scoring.BASEBALL_SPORTS` 다.
def _table(sport: str) -> dict:
    from app.engine.scoring import BASEBALL_SPORTS

    return ADJ_RULES["baseball" if sport in BASEBALL_SPORTS else "soccer"]


def p_market(probs: dict | None, home: str, away: str, sport: str) -> float | None:
    """디빅된 확률 dict → **홈 승 확률**. 못 고르면 None.

    🔴 없으면 **None 이다.** 0.5 로 채우거나 Elo 로 대체하지 않는다.
    """
    if not probs or home not in probs or away not in probs:
        return None
    return round(float(probs[home]), 4)


def market_triple(probs: dict | None, home: str, away: str) -> tuple | None:
    """축구 3-way (홈, 무, 원정). 무승부 칸이 없으면 None."""
    if not probs or home not in probs or away not in probs:
        return None
    draw = next((v for k, v in probs.items() if k not in (home, away)), None)
    if draw is None:
        return None
    return (round(float(probs[home]), 4), round(float(draw), 4),
            round(float(probs[away]), 4))


def _count(jg: dict, key: str) -> float:
    v = jg.get(key)
    if v is True:
        return 1.0
    if v is False or v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def adjustments(jg: dict) -> dict[str, float]:
    """검증된 변수만으로 만든 `{변수명: %p}`. 없으면 **빈 dict**.

    ⚠️ `짧은휴식`·`이동연전` 은 임계를 넘었는지의 참/거짓이다 — 호출부가
       `rest_days`(3 이하)·`trip_day`(3 이상)를 미리 판단해 불린으로 준다.
    """
    table = _table((jg.get("sport") or "").lower())
    out: dict[str, float] = {}
    for name, (key, per, cap) in table.items():
        n = _count(jg, key)
        if not n:
            continue
        raw = per * n
        val = max(raw, cap) if cap < 0 else min(raw, cap)
        out[name] = round(val, 2)
    return out


#: [결정 B 2026-09-13] **표의 크기를 절반으로 시작한다.**
#  🔴 178경기·변수별 표본은 회귀 추정에 부족하다 — 과거 원장 회귀는 하지 않는다.
#     대신 사전값을 축소해 넣고 CLV 로 사후 검증한다(1차 결정 6).
#     변수별 100건 이상 쌓이고 평균 CLV 부호가 조정 방향과 같으면 1.0,
#     반대면 0 으로 — 변수 단위로 개별 조정한다. 판단은 사용자가 한다.
ADJ_SHRINK = 0.5

#: 합계 절사. 조정이 아무리 겹쳐도 시장에서 이만큼 넘게 떨어지지 않는다.
ADJ_SUM_CAP = 6.0


def shrink_and_cap(adj: dict[str, float] | None) -> dict[str, float]:
    """표 크기 → 축소 → 합계 절사. **원장에는 축소 전 값을 남긴다**
    (어떤 변수가 얼마로 발생했는지가 사후 검증의 재료다)."""
    if not adj:
        return {}
    out = {k: round(v * ADJ_SHRINK, 2) for k, v in adj.items()}
    total = sum(out.values())
    if abs(total) > ADJ_SUM_CAP and total:
        scale = ADJ_SUM_CAP / abs(total)
        out = {k: round(v * scale, 2) for k, v in out.items()}
    return out


def p_code(market: float | None, adj: dict[str, float] | None,
           sport: str, settings=None) -> float | None:
    """`p_market + Σ adj`(%p) 를 승률 상·하한으로 절사한 값.

    🔴 `market` 이 None 이면 **None** 이다 — 대체값을 만들지 않는다.
    """
    if market is None:
        return None
    from app.engine.scoring import cap_probability

    # 🔴 [결정 B] 표 크기를 그대로 더하지 않는다 — 축소·절사를 거친다.
    p = float(market) + sum(shrink_and_cap(adj).values()) / 100.0
    capped, _ = cap_probability(p, sport, settings)
    return round(float(capped), 4)


def adj_json(adj: dict[str, float] | None) -> str:
    """원장에 남길 JSON. 빈 조정은 `{}` — NULL 이 아니다(조사했는데 없었다는 뜻)."""
    return json.dumps(adj or {}, ensure_ascii=False)
