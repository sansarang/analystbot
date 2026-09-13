"""[MBF-1] 모델 확률을 운영 `jg` 에 붙인다 (3차 결정 F(C) + G).

🔴 **결정 F(C)**: 모델 확률은 **코드 쪽(`prob.py`)에만** 들어간다.
   Gemini 프롬프트는 종전·v3 어느 쪽도 건드리지 않는다.
🔴 **결정 G**: `model_w = 0.0` 으로 시작한다 — 기록만 하고 발송 숫자에
   영향이 없다. 상향은 300건 뒤 사용자 판정이다.

⚠️ **새로 수집하지 않는다.** 이미 `jg` 에 붙어 있는 재료만 쓰고, 없으면 그 축은
   사전값으로 대체하고 `missing` 에 적는다(0 과 미계산을 구분한다).
⚠️ 동기 순수 함수다 — DB·HTTP 를 부르지 않는다(계약이 단언).
"""
from __future__ import annotations

import logging

from app.model_baseball import model as M

logger = logging.getLogger(__name__)

SRC = "model_baseball.v1"


def league_rpg(sport: str) -> float:
    """리그 팀당 평균 득점. 🔴 숫자를 여기 적지 않는다 — 설정이 원본이다."""
    from app.config import get_settings

    s = get_settings()
    key = {"kbo": "kbo_runs_per_game", "npb": "npb_runs_per_game"}.get(
        (sport or "").lower(), "league_runs_per_game")
    return float(getattr(s, key))


def _starts(research: dict, side: str) -> list[dict]:
    """`slim_start` 모양 → 모델 입력. 키 이름만 바꾼다(값은 그대로)."""
    out = []
    for r in research.get(f"{side}_starter_recent") or []:
        ip = r.get("innings")
        if ip is None:
            continue
        out.append({"ip": float(ip), "r": float(r.get("r") or 0)})
    return out


def _pen(research: dict, side: str) -> list[dict]:
    blk = (research.get(f"{side}_bullpen") or {}).get("최근3경기") or {}
    ip, runs = blk.get("이닝"), blk.get("실점")
    if ip is None or runs is None:
        return []
    return [{"ip": float(ip), "r": float(runs)}]


def build(jg: dict) -> dict:
    """`jg` → `{p_model, exp_total, components, missing, src}`.

    실패해도 예외를 내지 않는다 — 판정·발송을 막지 않는다.
    """
    sport = (jg.get("sport") or "").lower()
    prior = league_rpg(sport)
    research = jg.get("research") or {}
    missing: list[str] = []
    sides: dict[str, dict] = {}
    for side in ("home", "away"):
        st = _starts(research, side)
        pen = _pen(research, side)
        if not st:
            missing.append(f"sp_{side}")
        if not pen:
            missing.append(f"bp_{side}")
        sides[side] = {
            "sp": M.sp_axis(st, prior),
            "bp": M.bp_axis(pen, prior),
            # 타선은 운영 `jg` 에 wOBA 가 없다 — 사전값(리그 평균)으로 둔다.
            #   ⚠️ 타순 기반 타선 축은 4단계 이후 재료가 생기면 붙인다.
            "off": M.team_offense(None, None, {"woba": 0.320, "rpg": prior}),
        }
        missing.append(f"off_{side}")
    out = M.predict(sides["home"], sides["away"])
    return {"p_model": out["p_home"], "exp_total": out["exp_total"],
            "components": out["components"], "missing": missing, "src": SRC}
