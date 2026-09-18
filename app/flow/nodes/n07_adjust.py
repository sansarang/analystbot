"""[v1.4 STEP 8] ⑦ 조정 — **확인된 변수만** %p 를 얻는다.

🔴 크기는 `flow.adjust_prior_pp[sport][var].max_abs` 안에서만. 표 밖 변수는 0 이다.
🔴 방향은 코드가 정한다. `strength` 는 근거의 성질이다 —
     수치 근거가 있으면 1.0, 정성이면 0.5 (지시문 STEP 8).
🔴 합계는 `flow.total_adjust_cap_pp` 로 클램프한다.
⚠️ 단위: `pp` 접미사 필드만 %p 다. 확률(0~1)과 섞지 않는다.
"""
from __future__ import annotations

import logging
import re

from app.flow import rules as R
from app.flow.labels import CONFIRMED

logger = logging.getLogger(__name__)

NODE = "n07_adjust"

#: 수치 근거인가 — 숫자가 들어 있으면 1.0, 아니면 0.5.
_NUM = re.compile(r"\d")

def _direction(sides: dict, pick_side: str | None) -> float:
    """부호. 🔴 **어느 팀 악재인가**로 정한다.

    우리 픽 쪽 악재 → 불리(−) · 상대 쪽 악재 → 유리(+) · 양쪽이면 0(상쇄).
    ⚠️ 한쪽으로 고정하면 근거와 **반대로** 확률이 움직인다. 실제 픽스처가
       그것을 잡았다 — "한화 선발 ERA 6.10"은 삼성(픽)에게 **유리**하다.
    """
    if not sides or not pick_side:
        return -1.0                       # 모르면 보수적으로 불리하게 읽는다
    other = "away" if pick_side == "home" else "home"
    mine, theirs = int(sides.get(pick_side, 0)), int(sides.get(other, 0))
    if mine and theirs:
        return 0.0
    if theirs:
        return +1.0
    return -1.0


async def run(state, ctx):
    """⑦ 조정."""
    sport = (state.sport or "").lower()
    table = R.vars_for(sport)
    per_var = (state.n06_verdict or {}).get("per_var") or {}
    ev = {e["var"]: e for e in (state.n05_evidence or [])}

    out: list = []
    for var, verdict in per_var.items():
        if verdict != CONFIRMED:
            continue
        spec = table.get(var) or {}
        max_abs = float(spec.get("max_abs", 0) or 0)
        if max_abs <= 0:                      # 표 밖 변수는 0 이다
            continue
        row = ev.get(var) or {}
        strength = 1.0 if _NUM.search(row.get("raw_excerpt") or "") else 0.5
        sign = _direction(row.get("sides") or {}, state.pick_side)
        if sign == 0.0:                   # 양쪽 다 악재면 상쇄 — 0 을 적지 않는다
            continue
        out.append({"var": var, "pp": round(sign * max_abs * strength, 2),
                    "strength": strength, "sign": sign})

    cap = float(R.get("total_adjust_cap_pp", 6.0))
    total = sum(a["pp"] for a in out)
    clamped = max(-cap, min(cap, total))
    if out and abs(total) > cap:
        scale = clamped / total
        for a in out:
            a["pp"] = round(a["pp"] * scale, 2)
        logger.info("[flow:n07] game=%s 합 %.1f%%p → 상한 %.1f 로 클램프",
                    state.game_id, total, cap)

    state.n07_adjust = out
    logger.info("[flow:n07] game=%s 조정 %d개 · 합 %+.2f%%p",
                state.game_id, len(out), sum(a["pp"] for a in out))
    return state
