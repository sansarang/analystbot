"""[SWAP-1] 흐름 판정을 **결정 원장**에 남긴다.

사용자 2026-09-22: "바꿔끼우기 진행해라… 버그가 있어서도 안 되고
옛 경로로 가서는 안 된다"

🔴 **왜 이것이 전환의 첫 걸음인가.** 원장이 없으면 "흐름이 구경로보다 나은가"를
   **잴 수가 없다.** 오늘 만든 `decision_ledger` 와 지표 모듈이 그 자리다.
   재지 않고 갈아끼우면 나빠져도 모른다.

🔴 **`pick_ledger` 를 건드리지 않는다.** 그 표는 구경로의 것이고, 둘이 같은
   표에 쓰면 어느 경로의 성적인지 갈리지 않는다. 흐름은 `decision_ledger` 에
   `engine='flow_v14'` 로 남긴다 — 같은 지표로 **나란히** 비교된다.

⚠️ **실패가 흐름을 막지 않는다.** 기록은 관측이고, 관측이 판정을 죽이면 안 된다.
⚠️ 멱등이다. `UNIQUE (engine, game_id, market, line, side, ts_decided)` 가
   막는다 — 같은 실행을 두 번 돌려도 중복이 없다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ENGINE = "flow_v14"

_INSERT = """
    INSERT INTO decision_ledger
      (engine, game_id, sport, league, market, line, side, book, ts_decided,
       price_at_decision, p_model, p_market_at_decision, p_close, price_close,
       result, clv, roi_unit, status, note)
    VALUES ($1,$2,$3,$4,'h2h',NULL,$5,NULL,now(),
            NULL,$6,$7,NULL,NULL,NULL,NULL,NULL,'candidate',$8)
    ON CONFLICT (engine, game_id, market, line, side, ts_decided)
    DO NOTHING
"""


def _our_side_p(p_home, side: str | None):
    """홈 기준 확률 → **우리가 고른 쪽** 확률.

    🔴 `decisions._our_side_p` 와 **같은 규약**이다. CLV 의 부호가 여기서 갈린다.
    """
    from app.learning.decisions import _our_side_p as _f

    return _f(p_home, side)


def pick_of(state) -> tuple:
    """흐름 상태 → `(side, p_model, p_market)`. 못 정하면 `(None, …)`.

    🔴 **지어내지 않는다.** ⑧이 확률을 못 냈으면 방향도 없다 —
       `apply_code_verdict` 와 같은 규약이다.
    ⚠️ `p_code_pick` 은 **홈 기준**이다(`n08_pcode` 가 그렇게 쓴다).
    """
    pc = (getattr(state, "n08_pcode", None) or {}).get("p_code_pick")
    if pc is None:
        return None, None, None
    try:
        p_home = float(pc)
    except (TypeError, ValueError):
        return None, None, None
    side = "home" if p_home >= 0.5 else "away"
    mkt = (getattr(state, "n02_market", None) or {}).get("p_market")
    try:
        p_mkt = float(mkt) if mkt is not None else None
    except (TypeError, ValueError):
        p_mkt = None
    return side, _our_side_p(p_home, side), _our_side_p(p_mkt, side)


def note_of(state) -> str:
    """무엇을 보고 그렇게 정했는지 한 줄. 🔴 조용한 기록을 만들지 않는다."""
    conf = (getattr(state, "n09_conf", None) or {}).get("grade")
    adj = getattr(state, "n07_adjust", None) or []
    gate = (getattr(state, "n03_gate", None) or {}).get("label")
    stop = getattr(state, "stop_reason", None)
    parts = [f"run={getattr(state, 'run_id', '')}"]
    if gate:
        parts.append(f"게이트={gate}")
    if conf:
        parts.append(f"확신={conf}")
    parts.append(f"조정={len(adj)}건")
    if stop:
        parts.append(f"멈춤={stop}")
    return " · ".join(parts)[:300]


async def record(state, ctx) -> bool:
    """흐름 판정 1건을 원장에 남긴다. 반환: 남겼으면 True.

    ⚠️ **예외를 밖으로 던지지 않는다** — 기록 실패가 흐름을 죽이면 안 된다.
    """
    pool = getattr(ctx, "pool", None) if ctx is not None else None
    if pool is None:
        return False
    side, p_model, p_mkt = pick_of(state)
    if side is None:
        # 🔴 확률이 없으면 남기지 않는다. 0 이나 0.5 로 채우면 원장이 거짓이 된다.
        return False
    gid = getattr(state, "game_id", None)
    try:
        gid = int(gid)
    except (TypeError, ValueError):
        return False
    try:
        await pool.execute(
            _INSERT, ENGINE, gid, getattr(state, "sport", None),
            getattr(state, "league", None), side, p_model, p_mkt,
            note_of(state))
    except Exception as exc:
        logger.warning("[flow] 원장 기록 실패 game=%s: %s", gid, exc)
        return False
    logger.info("[flow] 원장 기록 game=%s %s p_model=%s p_market=%s",
                gid, side, p_model, p_mkt)
    return True
