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
        # 🔴 [PA-18 · 지시문 D2] 선발 최근 등판 평균 구속이 시즌 평균 대비
        #    −1.0mph 이상 떨어지면 **그 팀 −2%p**. 문턱은 statcast_velo 가
        #    원본이고(`VELO_DELTA_MIN`), 여기는 크기만 정한다.
        #    ⚠️ 부호는 호출부가 준다 — `velo_drop` 은 **홈 기준 차이**다
        #       (홈이 떨어졌으면 음수, 원정이 떨어졌으면 양수).
        "구속하락": ("velo_drop", -2.0, -2.0),
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


def away_prob(jg: dict, p_home: float | None) -> float | None:
    """홈 확률 → **원정 확률.** 🔴 규칙의 원본은 여기 한 곳이다.

    야구  무승부가 없다 → `1 - p_home`
    축구  무승부 질량이 있다 → `1 - p_home - p_draw`. **`1 - p_home` 이 아니다.**

    🔴 축구인데 무승부 질량을 모르면 **None** 이다. `1 - p_home` 으로 메우면
       그 숫자는 원정 승률이 아니라 "안 지는 확률"이고, 카드에 그대로 나간다.
       실사고 지점: `card.py` 한 줄 판정 · `performance.py` 최종 줄.
    ⚠️ `pipeline._run_*` 의 `p_claude_away` 와 **같은 규칙**이다 — 두 곳에
       적지 않으려고 이 함수를 만들었다(사본 금지).
    """
    if p_home is None:
        return None
    ph = float(p_home)
    if (jg.get("sport") or "").lower() != "soccer":
        return round(1.0 - ph, 4)
    tri = market_triple(jg.get("market_probs"), jg.get("home") or "",
                        jg.get("away") or "")
    if tri is None:
        return None                      # 모르면 만들지 않는다
    _, draw, _ = tri
    return round(max(0.0, min(1.0, 1.0 - ph - float(draw))), 4)


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
        # 🔴 [ADJ-3 2026-09-13] 상한은 **크기**에 건다. 종전
        #    `max(raw, cap) if cap < 0 else min(raw, cap)` 은 한쪽만 막았다 —
        #    입력이 음수가 되는 순간(원정이 더 지침) 절사 없이 통과했다.
        #    입력이 0 이상인 구간에서는 두 식의 결과가 같다(계약이 단언).
        lim = abs(cap)
        val = max(-lim, min(raw, lim))
        out[name] = round(val, 2)
    return out

# 🔴 [U13] 값은 `config/rules.yaml` 이 원본이다. 여기에 숫자를 **다시
#    적지 마라** — 두 곳에 적으면 사본이 되고, 사본은 원본이 바뀔 때
#    따라가지 않는다(실사고 2026-09-02 워치독 오탐 4건).
from app.engine import rules as _R


#: [결정 B 2026-09-13] **표의 크기를 절반으로 시작한다.**
#  🔴 178경기·변수별 표본은 회귀 추정에 부족하다 — 과거 원장 회귀는 하지 않는다.
#     대신 사전값을 축소해 넣고 CLV 로 사후 검증한다(1차 결정 6).
#     변수별 100건 이상 쌓이고 평균 CLV 부호가 조정 방향과 같으면 1.0,
#     반대면 0 으로 — 변수 단위로 개별 조정한다. 판단은 사용자가 한다.
ADJ_SHRINK = _R.get("prob.adj_shrink")

#: 합계 절사. 조정이 아무리 겹쳐도 시장에서 이만큼 넘게 떨어지지 않는다.
ADJ_SUM_CAP = _R.get("prob.adj_sum_cap")


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


def p_send(jg: dict, settings=None) -> float | None:
    """[SEND-1 결정 B-1] **카드와 보드가 함께 쓰는 홈 승 확률.**

        p_send = 시장(디빅) + Σ조정 + 딥서치 이동 → 합계 절사 → 승률 절사

    🔴 시장이 없으면 **None 이다.** 0.5 나 Elo 로 대체하지 않는다 —
       소비 지점이 종전 값(제미나이 확률)으로 폴백한다.
    🔴 **딥서치 이동을 더한다**(사용자 결정 2026-09-13). 호출 비용을 이미
       썼는데 버리면 그 돈이 낭비다. 다만 조정과 **같은 상한** 안에 둔다 —
       LLM 이 낸 %p 가 시장에서 무한정 멀어지지 못하게.
    ⚠️ 딥서치는 **판정 뒤에** 돈다(`build_analysis`: 판정 2145 → 딥서치 2167).
       그래서 이 함수는 딥서치 **뒤**에서 불려야 값이 온전하다.
    """
    mkt = jg.get("p_market_spine")
    if mkt is None:
        return None
    sport = (jg.get("sport") or "").lower()
    moved = ((jg.get("deepsearch") or {}).get("이동_pp")) or 0.0
    try:
        moved = float(moved)
    except (TypeError, ValueError):
        moved = 0.0
    total = sum(shrink_and_cap(adjustments(jg)).values()) + moved
    if abs(total) > ADJ_SUM_CAP:
        total = ADJ_SUM_CAP if total > 0 else -ADJ_SUM_CAP
    from app.engine.scoring import cap_probability

    capped, _ = cap_probability(float(mkt) + total / 100.0, sport, settings)
    return round(float(capped), 4)


#: [결정 G 2026-09-13] 모델 확률의 가중치. **0 에서 시작한다** —
#  기록만 하고 발송 숫자에 영향이 없다. 300건 뒤 사용자가 상향을 판정한다:
#    4단계 A/D 에서 모델이 ELO 를 이겼고, 전방 300건에서 p_model 브라이어가
#    p_market + 0.005 이하이며, model_gap_pp 방향 가상 pick 의 CLV 평균 > 0,
#    CI 하한 > 0 → 0.5. 다음 300건에서 같으면 1.0(= 뼈대 교체).
MODEL_W = 0.0


def model_gap_pp(p_model, p_market) -> float | None:
    """모델 − 시장 (%p). 사후 분해의 재료다."""
    if p_model is None or p_market is None:
        return None
    return round((float(p_model) - float(p_market)) * 100, 2)


def p_code(market: float | None, adj: dict[str, float] | None,
           sport: str, settings=None, *, p_model=None, model_w=None) -> float | None:
    """`p_market + Σ adj`(%p) 를 승률 상·하한으로 절사한 값.

    🔴 `market` 이 None 이면 **None** 이다 — 대체값을 만들지 않는다.
    """
    if market is None:
        return None
    from app.engine.scoring import cap_probability

    # 🔴 [결정 B] 표 크기를 그대로 더하지 않는다 — 축소·절사를 거친다.
    p = float(market) + sum(shrink_and_cap(adj).values()) / 100.0
    # 🔴 [결정 G] 모델 축. `model_w = 0` 이면 **항등**이다(계약이 단언).
    w = MODEL_W if model_w is None else float(model_w)
    if p_model is not None and w:
        p += w * (float(p_model) - float(market))
    capped, _ = cap_probability(p, sport, settings)
    return round(float(capped), 4)


def adj_json(adj: dict[str, float] | None) -> str:
    """원장에 남길 JSON. 빈 조정은 `{}` — NULL 이 아니다(조사했는데 없었다는 뜻)."""
    return json.dumps(adj or {}, ensure_ascii=False)


def code_pick(jg: dict) -> dict | None:
    """[P0-1] **코드가 고른 결과.** LLM 은 여기에 관여하지 않는다.

    반환은 `apply_winner` 가 그대로 먹는 모양이다 —
    축구는 `{"결과": 홈승|무|원정승}`, 야구는 `{"승자": 팀명}`.

    🔴 `p_code` 가 없으면 **None** 이다. 시장 뼈대가 없다는 뜻이고, 그때는
       승자를 지어내지 않는다(사용자 지시 2026-09-15). 호출부가 보드로 내린다.
    ⚠️ 축구 3-way 는 `p_code`(홈) · 시장 무승부 · 나머지(원정)로 읽는다.
       `1 - p_home ≠ p_away` 이므로 **무승부 질량을 빼야** 한다 —
       `pipeline._run_*` 가 `p_claude_away` 를 만드는 방식과 같다(사본 금지).
    """
    p = jg.get("p_code")
    if p is None:
        return None
    home, away = jg.get("home") or "", jg.get("away") or ""
    if (jg.get("sport") or "").lower() != "soccer":
        return {"승자": home if float(p) >= 0.5 else away}
    from app.engine.verdict import THREEWAY

    tri = market_triple(jg.get("market_probs"), home, away)
    if tri is None:
        return None
    draw = tri[1]
    rest = max(0.0, 1.0 - float(p) - float(draw))
    best = max((float(p), THREEWAY[0]), (float(draw), THREEWAY[1]),
               (rest, THREEWAY[2]))
    return {"결과": best[1]}
