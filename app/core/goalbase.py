"""🔴🔴 **두 팀 총골 기준의 수축** — 수정 지시 2026-10-13 4번.

> λ 2.818 / 2.170 · 총골 4.99 는 ACL Elite 실측 2.82 의 1.77배 → 이상값으로 보고
> 원인부터 찾는다.

🔴 **찾은 원인** — λ 바닥은 `facts.standings["match_total_baseline"]`(그 대회
   순위표에서 **두 팀의 경기당 총골** 평균)이고, ACL 리그 단계는 그때 **2경기**
   뿐이었다. 상하이–대전의 그 수는 **5.5** 였다(대회 실측 2.8213 의 1.95배).
🔴 **고치는 자리는 ③(구조 사실)** 이다 — 운영 확률은 **얼린 M1**(`old_engine`)이
   내고 그것이 같은 칸을 읽는다(K0 라 손대지 않는다). 그래서 **칸을 고친다**:
   ③ 이 수축한 수를 싣고, 원값·표본·사유를 **옆 칸에** 남긴다(#3).
🔴 **새 계수를 만들지 않는다** — 가중은 `w = min(1, 표본/FULL)` 이고 `FULL` 은
   이미 쓰고 있는 문턱(`probmodel.TEAM_HOME_FULL` = 8)과 **같은 수**다.
⚠️ 표본을 **모르면 수축하지 않는다** — 모르는 것을 작다고 보면 옛 카드·계약의
   수가 조용히 바뀐다(실측: 계약 둘이 빨개졌다).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 그대로 쓰기 시작하는 표본(경기 수) — `TEAM_HOME_FULL` 과 같은 수
FULL = 8


def shrink(raw: float | None, *, played: object,
           comp_total: float | None) -> tuple[float | None, str]:
    """🔴🔴 `(수축한 두 팀 총골, 사유)`. 못 수축하면 원값과 그 사유다."""
    if raw is None:
        return None, "⬜ 두 팀 총골 기준이 없다"
    said_raw = float(raw)
    if comp_total is None:
        return said_raw, (f"두 팀 총골 {said_raw:g} · ⬜ **대회 실측 평균이 "
                          f"없어 수축 못 했다**")
    if played is None:
        return said_raw, (f"두 팀 총골 {said_raw:g} · ⬜ **표본 칸이 없다** — "
                          f"수축 못 했다")
    n = int(played or 0)
    w = min(1.0, n / FULL) if n > 0 else 0.0
    if w >= 1.0:
        return said_raw, (f"두 팀 총골 {said_raw:g}(표본 {n}경기 ≥ {FULL} → "
                          f"그대로)")
    got = w * said_raw + (1.0 - w) * float(comp_total)
    return got, (f"두 팀 총골 {said_raw:g}(표본 {n}경기) **수축 {w:.0%}** ↔ "
                 f"대회 실측 {float(comp_total):g}골 {1 - w:.0%} → "
                 f"**{got:.3f}골**")
