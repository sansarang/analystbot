"""🔴🔴 **④ 디빅** — 배당 → 공정 확률. 네 층 지시서 §2-5.

> 같은 마켓의 **모든 결과 배당이 있어야** 계산한다(승무패 셋, 핸디·총점·양팀득점 둘).
> 하나라도 빠지면 그 마켓은 *"시장 확률 없음"*.
> 기본: **비례 방식**(각 배당 역수 ÷ 역수 합).
> 승무패(3-way)는 **Shin 방식**도 같이 계산해 괄호로 보인다.
> **업체 몫**(역수 합 − 1)을 마켓마다 적는다.

🔴 **기대값·금액은 여기 없다**(§0 금지). 이 파일은 확률과 업체 몫만 만든다.
⚠️ 계약이 수까지 못 박았다: `1.66/3.79/4.55 → 55.5/24.3/20.2%`(±0.1), 합 1.0.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 Shin 방식 이분 탐색 한계 — 더 쪼개도 소수 네 자리가 안 바뀐다(실측)
_SHIN_STEPS = 60


def proportional(prices: list[float]) -> tuple[list[float], float]:
    """🔴 비례 방식 — `(확률들, 업체 몫)`. ⚠️ 빈 목록·1 이하 배당은 **거부**한다."""
    if not prices or any((p or 0) <= 1.0 for p in prices):
        return [], 0.0
    inv = [1.0 / float(p) for p in prices]
    tot = sum(inv)
    return [v / tot for v in inv], tot - 1.0


def shin(prices: list[float]) -> list[float]:
    """🔴 Shin(1993) 방식 — 정보 가진 베터 몫 `z` 를 풀어 공정 확률을 뺀다.

    ⚠️ 연구상 비례 방식과 차이는 **대체로 작고**, 배당 5 이상 큰 역배에서 Shin·파워
       방식이 조금 낫다(지시서 §2-5). 🔴 그래서 **둘을 함께 보인다** — 하나를
       고르지 않는다(고를 근거를 우리가 아직 못 쟀다).

    풀이: `π_i = (√(z² + 4(1−z)·q_i²/Σq) − z) / (2(1−z))`, `q_i = 1/배당`.
    `Σπ = 1` 이 되는 `z` 를 이분으로 찾는다.
    """
    if not prices or any((p or 0) <= 1.0 for p in prices):
        return []
    q = [1.0 / float(p) for p in prices]
    s = sum(q)
    if s <= 1.0:
        return [v / s for v in q]       # 🔴 몫이 없다(또는 음수) — 비례와 같다

    def _probs(z: float) -> list[float]:
        out = []
        for qi in q:
            root = (z * z + 4.0 * (1.0 - z) * qi * qi / s) ** 0.5
            out.append((root - z) / (2.0 * (1.0 - z)))
        return out

    lo, hi = 0.0, 0.9999
    for _ in range(_SHIN_STEPS):
        mid = (lo + hi) / 2.0
        if sum(_probs(mid)) > 1.0:
            lo = mid
        else:
            hi = mid
    got = _probs((lo + hi) / 2.0)
    tot = sum(got)
    return [v / tot for v in got] if tot else []


def median_of(rows: list[list[float]]) -> list[float]:
    """🔴 §2-4 — 업체별 **디빅한 확률**의 중앙값. ⚠️ 디빅 **전** 평균은 금지다.

    ⚠️ 실수하기 쉬운 자리다: 배당을 먼저 평균하면 업체 몫이 섞여 들어간다.
    """
    rows = [r for r in rows if r]
    if not rows:
        return []
    n = len(rows[0])
    if any(len(r) != n for r in rows):
        return []
    out: list[float] = []
    for i in range(n):
        col = sorted(r[i] for r in rows)
        mid = len(col) // 2
        out.append(col[mid] if len(col) % 2 else (col[mid - 1] + col[mid]) / 2.0)
    tot = sum(out)
    return [v / tot for v in out] if tot else []


def double_chance(home: float, draw: float, away: float) -> dict[str, float]:
    """🔴 §2-5 마지막 — 더블찬스는 **승무패 공정 확률에서 유도**한다(따로 안 받는다)."""
    return {"unbeaten:home": home + draw, "unbeaten:away": away + draw}
