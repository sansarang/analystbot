"""[v1.4 STEP 3] 배당 수학 — **마진 제거와 요구확률을 섞지 않는다.**

🔴 둘은 다른 숫자다:
     `devig_*`        마진을 뺀 **시장 확률**  → 우리 추정과 비교하는 값
     `required_prob`  `1/배당` (마진 포함)     → 값 판정(edge)의 기준
   지시문 STEP 3 의 "흔한 오류"가 바로 이 혼동이다 — `p_market` 자리에
   `1/odds` 를 넣으면 edge 가 늘 마진만큼 양수로 나와 ⑪이 전부 거짓 픽이 된다.

🔴 **`1 - p_home` 으로 원정 확률을 만들지 않는다**(축구). 무승부 질량이 있어
   셋으로 갈라야 한다 — `devig_3way` 를 쓴다.
⚠️ 순수 함수다. DB·HTTP·설정을 읽지 않는다.
"""
from __future__ import annotations


def devig_2way(o_a: float, o_b: float) -> tuple[float, float]:
    """야구 2-way. 반환 합은 1.0 이다."""
    inv = [1.0 / float(o_a), 1.0 / float(o_b)]
    s = sum(inv)
    return inv[0] / s, inv[1] / s


def devig_3way(o_h: float, o_d: float, o_a: float) -> tuple[float, float, float]:
    """축구 3-way(승·무·패). 반환 합은 1.0 이다."""
    inv = [1.0 / float(o_h), 1.0 / float(o_d), 1.0 / float(o_a)]
    s = sum(inv)
    return tuple(x / s for x in inv)


def required_prob(odds: float) -> float:
    """`1/배당`. **마진을 빼지 않는다** — 이것이 edge 의 기준선이다."""
    return 1.0 / float(odds)


def margin(*odds: float) -> float:
    """북 마진(오버라운드 − 1). 위생 검사용."""
    return sum(1.0 / float(o) for o in odds) - 1.0


def impossible_set(odds_list) -> bool:
    """이 **완전한 결과 집합**의 배당이 물리적으로 존재할 수 있는가.

    🔴 북은 마진 없이 호가를 내지 않는다. 합이 1 미만이면 차익거래가 되므로
       그런 호가는 **존재할 수 없고**, 긁기가 깨졌다는 신호다.

    🔴 [ODD-S 2026-09-23] 실측이 이것을 찾았다 — 배당 이동이 노이즈인지 재다가:
    ```
    g1774 롯데@한화  홈 2.08 고정 · 원정 2.20 ↔ 1.71 반복
      2.08/2.20 → 0.935  ← 불가능
      2.08/1.71 → 1.066  ← 정상(마진 6.6%)
    증분 자기상관 ρ₁  kbo −0.5849 → 불가능값 제외하면 **−0.1561**
    보유량  kbo 145/3,625(4.0%) · npb 94/3,789(2.5%) · mlb 5/7,179(0.1%)
    ```

    🔴 **`margin` 이 원본이다** — 오버라운드를 여기서 다시 짜지 않는다.
       그 함수는 "위생 검사용"이라 적혀 있었는데 **쓰는 곳이 0곳**이었다.

    ⚠️ **완전한 집합으로만 잰다.** 축구를 2-way 로 재면 무승부 몫 때문에
       정상 호가가 전부 불가능으로 읽힌다(실측 합 중앙 0.78). 호출부가
       (북·마켓·라인) 묶음을 통째로 넘겨야 한다.
    ⚠️ **둘 미만이면 판정하지 않는다.** 모르는 것을 버리면 조용한 폐기다.
    """
    vals = []
    for o in (odds_list or []):
        try:
            v = float(o)
        except (TypeError, ValueError):
            continue
        if v > 1.0:
            vals.append(v)
    if len(vals) < 2:
        return False
    return margin(*vals) < 0.0
