"""[BLD-1 2026-09-11] PL-1 섀도 앙상블 — **기록만 한다. 카드도 게이트도 안 본다.**

🔴 **왜.** 운영 원장 재측정(2026-09-08, 경기 단위 `is_final`):

    우리 LLM 판정   AUC 0.470~0.519 · 브라이어 0.2530
    단순 Elo        AUC 0.558
    시장            AUC 0.654

    **판정이 단순 Elo 보다 못하다.** 야구는 `p_final = p_claude` 원값이고
    보정도 앙상블도 없다 — 축구는 이미 `0.50*p_model + 0.50*p_claude` 로
    섞는데 야구만 없다(FINDINGS PL-1).

    섞는 것이 실제로 나은지는 **재봐야 안다.** 그런데 지금은 잴 재료가
    없다 — 원장에 `p_claude` 만 남아서 "그때 섞었으면 어땠나"를 사후에
    볼 방법이 없다(CACHE-1 과 같은 뿌리).

    그래서 매 판정에 가중치 3종(0.3 / 0.5 / 0.7)의 혼합값을 **원장 옆에
    적어 둔다.** 리그별 50건이 쌓이면 그때 비교 리포트를 만든다.

🔴 **이것은 섀도다.**
   · 카드 텍스트를 바꾸지 않는다
   · 게이트·추천·확률 클립에 닿지 않는다
   · 되돌아가지 않는다 — 판정이 이 값을 읽으면 그 순간 "우리 판정"이 아니다
   `tests/test_shadow_blend.py` 가 import 경계로 이것을 강제한다.

⚠️ 식과 상수를 여기 적지 않는다. Elo→확률은 `models/elo_core.expected_home`,
   홈 이점은 `models/team_elo.HOME_ADV` 가 원본이다 — `elo_core` 머리말이
   이미 "식이 두 벌이 되면 한쪽만 고쳐진다"고 적어 놨다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 사용자 지정(2026-09-11): Elo 가중 0.3 / 0.5 / 0.7 세 값을 함께 남긴다.
#   하나만 남기면 "그 값이 최선이었나"를 사후에 물을 수 없다.
WEIGHTS: tuple[float, ...] = (0.3, 0.5, 0.7)


def p_elo(jg: dict) -> float | None:
    """자료12 레이팅 → 홈 기대 승률. 재료가 없으면 **None**(0.5 로 덮지 않는다).

    ⚠️ 0.5 로 채우면 "박빙"과 "모른다"가 같아진다. 그 둘은 다른 사실이다.
    """
    from app.models.elo_core import expected_home
    from app.models.team_elo import HOME_ADV

    e = (jg or {}).get("elo") or {}
    h, a = e.get("home") or {}, e.get("away") or {}
    try:
        hr, ar = h.get("레이팅"), a.get("레이팅")
        if hr is None or ar is None:
            return None
        return round(expected_home(float(hr) - float(ar) + HOME_ADV), 4)
    except (TypeError, ValueError) as exc:
        logger.debug("[shadow-blend] 레이팅을 못 읽었다: %s", exc)
        return None


def compute(jg: dict) -> dict | None:
    """원장에 넣을 섀도 값. 판정 확률이 없으면 None(기록하지 않는다).

    반환 예:
        {"p_claude": 0.54, "p_elo": 0.571,
         "w0.3": 0.549, "w0.5": 0.556, "w0.7": 0.562}

    Elo 가 없으면 사유를 값으로 남긴다 — **빈칸과 "재본 적 없음"을 구분한다.**
    """
    pc = (jg or {}).get("p_claude")
    if pc is None:
        return None
    try:
        pc = float(pc)
    except (TypeError, ValueError):
        return None
    pe = p_elo(jg)
    if pe is None:
        return {"p_claude": round(pc, 4), "p_elo": None, "why": "elo 없음"}
    out: dict = {"p_claude": round(pc, 4), "p_elo": pe}
    for w in WEIGHTS:
        out[f"w{w}"] = round(w * pe + (1.0 - w) * pc, 4)
    return out


def safe_compute(jg: dict) -> dict | None:
    """`compute` 의 방탄 판. **섀도가 본체를 죽이면 안 된다.**

    원장 기록은 판정의 유일한 영구 기록이다 — 섀도 계산이 터졌다고 그 행이
    안 들어가면 안 된다. 예외는 debug 한 줄이고 값은 None 이다.
    """
    try:
        return compute(jg)
    except Exception as exc:
        logger.debug("[shadow-blend] 계산 실패 game=%s: %s",
                     (jg or {}).get("game_id"), exc)
        return None
