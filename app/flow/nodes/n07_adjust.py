"""[v1.4 STEP 8] ⑦ 조정 — **확인된 변수만** %p 를 얻는다.

🔴 크기는 `flow.adjust_prior_pp[sport][var].max_abs` 안에서만. 표 밖 변수는 0 이다.
🔴 [FIX-1·2 2026-09-20] 방향과 강도는 **증거의 `direction`** 에서 온다.
   종전에는 `sides` 의 **항목 수**로 부호를, `raw_excerpt` 에 숫자가 있는지로
   강도를 정했다. 그래서 상대 선발이 6.0이닝 1자책인 경기와 4.0이닝 5자책인
   경기에 똑같이 `+3.0 · strength 1.0` 이 붙었다(실측 MLB 4경기 전부).
🔴 방향을 못 정하면 **0 이고 행을 만들지 않는다.** 종전 "모르면 −1" 은
   폐기했다 — 그러면 자료가 없을수록 확률이 내려간다(모름을 근거로 쓴 것이다).
🔴 합계는 `flow.total_adjust_cap_pp` 로 클램프한다.
⚠️ 단위: `pp` 접미사 필드만 %p 다. 확률(0~1)과 섞지 않는다.
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import CONFIRMED

logger = logging.getLogger(__name__)

NODE = "n07_adjust"

def _direction_of(direction: dict | None, pick_side: str | None) -> float:
    """부호. 🔴 **(상대 악재 + 우리 호재) − (우리 악재 + 상대 호재)** 의 부호다.

    `direction` 은 팀별 호재 +1 / 악재 −1 / 모름 0 이다(`app/flow/direction.py`).
    🔴 못 정하면 **0.0** — 종전의 "모르면 −1(보수적으로 불리)"은 폐기했다.
       모름을 불리의 근거로 쓰면 자료가 적을수록 확률이 내려간다.
    ⚠️ 상쇄 0 과 미상 0 은 값이 같다 — 구분은 `basis` 가 한다.
    """
    if not direction or not pick_side:
        return 0.0
    other = "away" if pick_side == "home" else "home"
    score = int(direction.get(pick_side, 0) or 0) - int(direction.get(other, 0) or 0)
    return 1.0 if score > 0 else (-1.0 if score < 0 else 0.0)


def _from_sides(sides: dict | None, excerpt: str, dev_full: float) -> dict:
    """`sides` 만 있는 옛 증거를 방향으로 옮긴다 — **호환 경로**다.

    🔴 `sides` 의 원래 뜻은 `_direction` 머리말이 적어 둔 **"악재의 주체"** 다
       (`{팀: 항목 수}`). 그 뜻 그대로 `{팀: -1}` 로 읽는다.
    ⚠️ 새 증거(`n05`)는 언제나 `direction` 을 싣는다. 이 경로는 픽스처·드라이런
       처럼 주입된 행에만 쓰인다 — 거기서 종전 강도 규칙(수치 1.0 · 정성 0.5)을
       유지하려고 dev 를 그 값이 나오도록 넣는다.
    """
    if not sides:
        return {}
    out = {"home": 0, "away": 0,
           "dev": dev_full if any(ch.isdigit() for ch in (excerpt or "")) else dev_full / 2,
           "basis": "옛 sides 에서 옮김"}
    for side in ("home", "away"):
        if int(sides.get(side, 0) or 0):
            out[side] = -1
    return out


def _strength_of(dev, dev_full: float) -> float:
    """강도 = `min(1.0, |dev| / dev_full)`. 🔴 편차를 모르면 **0.0**."""
    if dev is None or not dev_full:
        return 0.0
    return round(min(1.0, abs(float(dev)) / float(dev_full)), 4)


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
        dev_full = float(R.get("direction.dev_full", 0.5))
        d = row.get("direction") or _from_sides(
            row.get("sides"), row.get("raw_excerpt") or "", dev_full)
        sign = _direction_of(d, state.pick_side)
        strength = _strength_of(d.get("dev"), dev_full)
        if sign == 0.0 or strength <= 0.0:
            # 🔴 방향이 없거나 편차가 0이면 **행을 만들지 않는다.**
            #    상쇄인지 미상인지는 basis 가 말한다.
            logger.info("[flow:n07] game=%s var=%s 조정 없음 — sign=%s · dev=%s · %s",
                        state.game_id, var, sign, d.get("dev"), d.get("basis") or "방향 미상")
            continue
        out.append({"var": var, "pp": round(sign * max_abs * strength, 2),
                    "strength": strength, "sign": sign,
                    "dev": d.get("dev"), "basis": d.get("basis")})

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
