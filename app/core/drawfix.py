"""🔴🔴 **M1 무승부 보정 — 경계에서 건다**(사용자 지시 2026-10-12 5번).

> M1 무승부 과대(26.9 vs 20.9) — Dixon-Coles ρ 또는 무승부 스케일을 **교차 적합**해
> 보정 판 비교(**방향 적중률 손상 없을 때만**).

🔴 실측(460경기 · 시즌 교차 · `tools/m1_draw.py`):
```
없음(기준 M1)  로그손실 1.0527 · 방향 49.5% · 무승부 예측 26.8%
rho  +0.2      로그손실 1.0474(−0.0054 · 95% −0.0127~+0.0015) · 방향 49.5% · 22.7%
draw −0.2~−0.4 로그손실 1.0510(−0.0018) · 방향 49.5% · 21.2%
실제 무승부율 22.1%
```
🔴 그래서 **`rho` 를 채택했다** — 로그 손실이 낮고 구간 하한이 0 밖이며 **방향이
   손상되지 않았다**(사용자 조건).

🔴🔴 **얼린 옛 경로를 고치지 않는다**(계약 K0) — 보정은 그 격자가 나온 **뒤**에
   건다. ⚠️ 계수는 **판 파일**(`data/m1_draw/<리그>/<날>.yaml`)이 든다. 판이 없으면
   **보정하지 않는다**(손값 금지 · 그 사실을 사유에 적는다).
"""
from __future__ import annotations

import math

#: 🔴 판이 사는 표
TABLE = "m1_draw"


def bend(grid: dict, *, rho: float = 0.0, draw: float = 0.0) -> dict:
    """🔴 격자에 보정을 걸고 **다시 정규화**한다. `{(홈, 원정): 확률}`.

    🔴 `rho` — 낮은 스코어 네 칸: `0-0`·`1-1` ×(1−ρ) · `1-0`·`0-1` ×(1+ρ).
       ⚠️ Dixon-Coles 의 τ 와 **부호 규약이 다르다**(여기서는 ρ>0 이 무승부를
       **줄인다**) — 적합이 그 꼴로 수를 골랐다(`tools/m1_draw.py`).
    🔴 `draw` — **대각선 전체**에 `exp(draw)`.
    """
    if not rho and not draw:
        return dict(grid or {})
    out: dict = {}
    for key, val in dict(grid or {}).items():
        h, a = (int(key[0]), int(key[1]))
        mul = 1.0
        if draw and h == a:
            mul *= math.exp(float(draw))
        if rho:
            if (h, a) in ((0, 0), (1, 1)):
                mul *= 1.0 - float(rho)
            elif (h, a) in ((1, 0), (0, 1)):
                mul *= 1.0 + float(rho)
        out[(h, a)] = max(0.0, float(val) * mul)
    tot = sum(out.values()) or 1.0
    return {k: v / tot for k, v in out.items()}


def load(*, league: str, as_of=None) -> tuple[dict, str]:
    """🔴 보정 판. 없으면 `({}, 사유)` — **보정하지 않는다**(손값 금지)."""
    from app.core import versions as _v
    box = _v.path_of(TABLE, str(league).replace(":", "_"))
    try:
        got, why = _v.pick(box, as_of=as_of)
    except ValueError as exc:
        return {}, f"⬜ 무승부 보정 없음 — {exc}"
    if not got:
        return {}, f"⬜ 무승부 보정 판이 없다({why}) — 보정하지 않는다"
    return dict(got), f"무승부 보정 {why}"


def triple(grid: dict) -> list[float]:
    """🔴 격자 → 승·무·패(그 격자 하나에서)."""
    home = sum(v for (h, a), v in dict(grid).items() if int(h) > int(a))
    draw = sum(v for (h, a), v in dict(grid).items() if int(h) == int(a))
    away = sum(v for (h, a), v in dict(grid).items() if int(h) < int(a))
    tot = home + draw + away or 1.0
    return [home / tot, draw / tot, away / tot]
