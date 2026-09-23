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
            $6,$7,$8,NULL,NULL,NULL,NULL,NULL,'candidate',$9)
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

    🔴 [SIDE-1 2026-09-23] **여기가 뒤집혀 있었다.** 종전 주석은
       "`p_code_pick` 은 홈 기준이다(`n08_pcode` 가 그렇게 쓴다)"였는데
       생산자는 그렇게 쓰지 않는다:
       ```
       n08_pcode.run:72   side = state.pick_side
                          p_code_pick = 시장[side] + 조정      ← **픽 기준**
       ```
       그래서 확률이 절반을 넘는지로 방향을 되짚으면 **원정 픽이 홈으로**
       적힌다. 실측 2026-09-23 최근 30일 58경기 중 **13건(22.4%)** 이 반대
       팀으로 기록됐다(원장 쏠림 home 525 : away 221 이 그 서명이다).
       CLV·채점·ROI 가 전부 그 행을 본다.

       ⚠️ `test_종목_분기가_한_곳에만_있다` 가 이미 이 짓을 금지하고 있었다.
          종전 코드는 변수명이 `p_home` 이라 그 정규식을 **빠져나갔다** —
          원문 대조 가드는 이름을 바꾸면 뚫린다.

    🔴 **방향의 원본은 `state.pick_side`(①이 정한다) 하나다.** 확률에서
       되짚지 않는다 — 되짚기는 ①과 시장이 갈릴 때 반드시 틀린다.
    ⚠️ `pick_side` 가 없으면 **적지 않는다.** 추정하면 22.4% 가 다시 생긴다.
    """
    pc = (getattr(state, "n08_pcode", None) or {}).get("p_code_pick")
    side = getattr(state, "pick_side", None)
    if pc is None:
        return None, None, None
    if side not in ("home", "away"):
        logger.warning("[flow:record] game=%s pick_side 가 없다 — 원장에 적지 않는다",
                       getattr(state, "game_id", None))
        return None, None, None
    try:
        p_ours = float(pc)
    except (TypeError, ValueError):
        return None, None, None
    # 🔴 [LED-1 2026-09-23] **키가 안 맞았다.** ②는 `p` 에 `{home,draw,away}`
    #    로 쓰는데 여기서 `p_market` 을 읽어 **740행 전건 시장 확률이 비었고**
    #    그래서 CLV 를 한 건도 못 쟀다(실측: decision_ledger clv 96/1118,
    #    flow_v14 는 0).
    #    ⚠️ 시장은 **홈 기준**으로 들어온다 — 그것만 `_our_side_p` 로 돌린다.
    #       `p_ours` 는 이미 픽 기준이라 돌리지 않는다.
    _mp = (getattr(state, "n02_market", None) or {}).get("p") or {}
    mkt = _mp.get("home") if isinstance(_mp, dict) else None
    try:
        p_mkt = float(mkt) if mkt is not None else None
    except (TypeError, ValueError):
        p_mkt = None
    return side, p_ours, _our_side_p(p_mkt, side)


def price_of(state):
    """우리가 고른 쪽의 **소수배당**. 🔴 없으면 None — 지어내지 않는다.

    🔴 [LED-2 2026-09-23] 종전 INSERT 는 이 자리에 NULL 을 박았다. 그래서
       `roi_unit` 을 영영 못 냈다(실측: flow_v14 740행 전건 가격 없음).
       ②가 배당을 갖고 있는데 안 실었을 뿐이다.
    """
    side, _p, _m = pick_of(state)
    if side is None:
        return None
    odds = (getattr(state, "n02_market", None) or {}).get("odds") or {}
    v = odds.get(side)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


#: 🔴 [LED-2] **같은 판단의 되풀이를 막는다.** 충돌 키에 `ts_decided` 가 있어
#   흐름이 15분마다 돌 때마다 새 행이 생겼다 — 실측 740행 / 23경기 = 경기당
#   **32.2행**(구경로는 1.0행). 한 경기가 32번 세어지면 그 결과가 32배
#   가중되어 성적 통계가 거짓이 된다.
# ⚠️ **판단이 바뀐 기록은 남긴다**(라인 이동 학습의 재료다). 막는 것은
#    같은 쪽·같은 확률의 되풀이뿐이라 `p_model` 까지 보고 판단한다.
_SAME_SQL = """
    SELECT id FROM decision_ledger
     WHERE engine = $1 AND game_id = $2 AND market = 'h2h'
       AND side = $3 AND p_model = $4
     LIMIT 1
"""


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
    # 🔴 [LED-2] 같은 쪽·같은 확률이 이미 있으면 **안 쓴다.**
    try:
        dup = await pool.fetchrow(_SAME_SQL, ENGINE, gid, side, p_model)
    except Exception as exc:
        logger.warning("[flow] 원장 중복 조회 실패 game=%s: %s", gid, exc)
        return False
    if dup:
        return False
    try:
        await pool.execute(
            _INSERT, ENGINE, gid, getattr(state, "sport", None),
            getattr(state, "league", None), side, price_of(state),
            p_model, p_mkt, note_of(state))
    except Exception as exc:
        logger.warning("[flow] 원장 기록 실패 game=%s: %s", gid, exc)
        return False
    logger.info("[flow] 원장 기록 game=%s %s p_model=%s p_market=%s",
                gid, side, p_model, p_mkt)
    return True
