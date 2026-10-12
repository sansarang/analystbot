"""🔴🔴 **확률 경로 재구성 — Elo 바닥 + 상성 잔차**(사용자 지시 2026-10-12 1번).

> ③ **Elo → 바닥 λ/승무패**. ⑪ **축0·축1만**(Elo 대비 잔차).
> **축2·축3·⑩ 전략 판정은 확률 경로 밖**(표시·검증).

🔴 왜 — 444경기 백필(J1+K리그1 두 시즌 · as-of 재생):
```
축0 개선 +0.0007 · 축1 +0.0001 · 축2 **−0.0038** · 축3 **−0.0039**
봇 vs Elo만 브라이어 차 −0.0052(95% −0.0119~+0.0015) → **못 이긴다**
```
축2·축3 은 넣으면 **손실이 커진다**(잡음이다). 그래서 확률은 **Elo 를 바닥**으로
깔고 축0·축1 만 그 위의 **잔차**로 얹는다.

🔴🔴 **C1 개정**: 옛 C1 은 *"S3 입력에 Elo 가 없다"* 였다 — 이제 **Elo 가 바닥**이다.
   ⚠️ 나머지 금지는 **그대로**다: 동기·일정·감독 발언·맞대결·시장·LLM 문장은
   확률에 닿지 않는다.
⚠️ 이 파일은 **수를 짓지 않는다** — 바닥은 적합된 순서형 로짓(`base.triple_of`),
   잔차 비중·β 는 `config/matchup_model.yaml` 이 든다.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

#: 🔴🔴 **잔차로 쓰는 축** — 백필에서 개선이 **양수**였던 둘뿐이다.
#  ⚠️ 늘리려면 **백필 전진 선택에서 양수**임을 먼저 보여야 한다(지시 2번).
RESIDUAL_AXES: tuple[str, ...] = ("axis0", "axis1")


def floor_of(*, kind: str, dr: float | None) -> tuple[list[float] | None, str]:
    """🔴🔴 ③ — **Elo 바닥 승무패**. `([홈, 무, 원정], 사유)`. 없으면 `(None, 사유)`.

    🔴 입구는 `app/core/base.triple_of` **하나다**(사본 금지) — 대회 유형별로
       적합된 순서형 로짓이고, 그 적합이 없으면 바닥도 **없다**.
    ⚠️ `dr` 은 **경기 전** 등급 차다(누설 금지 · L1).
    """
    if dr is None:
        return None, "🔴 Elo 등급 차가 **없다** — 바닥을 만들지 않는다"
    from app.core import base as _base
    got, why = _base.triple_of(str(kind), float(dr))
    if got is None:
        return None, f"🔴 Elo 바닥 없음 — {why}"
    return ([float(got.home), float(got.draw), float(got.away)],
            f"Elo 바닥(순서형 로짓 · 등급 차 {float(dr):+.1f}) — {why}")


def blend(floor: list[float] | None, *, gaps: dict, weights: dict,
          beta: float) -> tuple[list[float] | None, str]:
    """🔴🔴 ⑪ — 바닥에 **축0·축1 잔차**를 얹는다. `([홈, 무, 원정], 사유)`.

    🔴 잔차는 **로그 오즈 이동**이다: `exp(β × Σ 비중×축차)` 를 홈 쪽에 곱하고
       원정 쪽에 나눈다(무는 그대로 두고 **다시 정규화**한다).
    ⚠️ `RESIDUAL_AXES` 밖의 축은 **읽지 않는다** — 계약이 그것을 센다.
    """
    if not floor:
        return None, "🔴 바닥이 없다 — 잔차를 얹지 않는다"
    tilt = 0.0
    said: list[str] = []
    for name in RESIDUAL_AXES:
        got = float(dict(gaps or {}).get(name) or 0.0)
        w = float(dict(weights or {}).get(name) or 0.0)
        if got and w:
            tilt += w * got
            said.append(f"{name} {got:+.3f}×{w:g}")
    if not tilt:
        return list(floor), "잔차 0 — 바닥 그대로(축0·축1 이 비었다)"
    move = float(beta) * tilt
    home = float(floor[0]) * math.exp(move)
    away = float(floor[2]) * math.exp(-move)
    draw = float(floor[1])
    tot = home + draw + away
    out = [home / tot, draw / tot, away / tot]
    return out, (f"잔차 {' · '.join(said)} → 합 {tilt:+.3f} × β {beta:g} = "
                 f"로그 오즈 {move:+.3f} · 바닥 {floor[0]:.0%}/{floor[1]:.0%}/"
                 f"{floor[2]:.0%} → {out[0]:.0%}/{out[1]:.0%}/{out[2]:.0%}")


def direction_hit(p: list[float], hit: int) -> bool:
    """🔴 **방향 적중** — 가장 높은 칸이 결과와 같나(지표 고정 · 매 보고 첫 줄)."""
    if not p:
        return False
    return int(max(range(3), key=lambda i: float(p[i]))) == int(hit)
