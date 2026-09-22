"""[LE-1a] `decision_ledger` 읽기·쓰기 + 기존 판정 소급 적재.

🔴 **왜 소급 적재를 하나.** 지시문 LE-1 완료 조건이 "우리 실시간 원장의
   Brier·CLV **첫 표**(봇 판정 79% 복사 상태의 **기준선**으로 남긴다)"다.
   기준선이 없으면 나중에 "나아졌다"를 말할 근거가 없다.

🔴 **확률을 '우리가 고른 쪽' 기준으로 바꿔 넣는다.** `pick_ledger` 의
   `p_code`·`p_market` 은 **홈 기준**이다(실측: `"p_market": mp.get("home")`).
   원정 픽에 홈 확률을 그대로 쓰면 CLV 의 부호가 뒤집힌다.

⚠️ **멱등이다.** `UNIQUE (engine, game_id, market, line, side, ts_decided)` +
   `ON CONFLICT DO NOTHING`. 두 번 돌려도 중복이 없어야 롤백이 안전하다.
⚠️ `p_home`(=옛 Claude Judge · 실측 AUC 0.5007) 은 **쓰지 않는다.** 방향
   유도에만 쓰이고(`predicted_side` 의 마지막 폴백) 지표에는 안 들어간다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 소급 적재 대상. 🔴 `is_final` 만 — 잠정 판정은 여러 행이라 같은 결정을
#  여러 번 세게 된다. 채점 여부는 안 가린다(미채점은 `result=NULL`).
_PICKS_SQL = """
    SELECT l.id, l.game_id, l.sport, l.league, l.judged_at,
           l.p_code, l.p_market, l.p_home, l.favored, l.predicted_side,
           l.odds_at_verdict, l.odds_closing, l.hit, l.void, l.judge_by
      FROM pick_ledger l
     WHERE l.is_final AND l.judged_at IS NOT NULL
     ORDER BY l.judged_at
"""

_INSERT = """
    INSERT INTO decision_ledger
      (engine, game_id, sport, league, market, line, side, book, ts_decided,
       price_at_decision, p_model, p_market_at_decision, p_close, price_close,
       result, clv, roi_unit, status, note)
    VALUES ($1,$2,$3,$4,'h2h',NULL,$5,NULL,$6,$7,$8,$9,$10,$11,$12,$13,$14,
            $15,$16)
    ON CONFLICT (engine, game_id, market, line, side, ts_decided)
    DO NOTHING
"""


def _our_side_p(p_home, side: str | None):
    """홈 기준 확률 → **우리가 고른 쪽** 확률. 🔴 부호의 출발점이다."""
    if p_home is None or side not in ("home", "away"):
        return None
    try:
        v = float(p_home)
    except (TypeError, ValueError):
        return None
    return round(v if side == "home" else 1.0 - v, 4)


def _result_of(hit, void) -> str | None:
    """`pick_ledger` 채점 → 결과 어휘. ⚠️ 무승부(`hit=None`)는 미정이 아니라
    **분모 제외**다 — `push` 로 적어 ROI 0 이 되게 한다."""
    from app.learning.metrics import LOSS, VOID, WIN

    if void:
        return VOID
    if hit is True:
        return WIN
    if hit is False:
        return LOSS
    return None


async def backfill_from_picks(pool, *, limit: int | None = None) -> dict:
    """`pick_ledger` → `decision_ledger`. 반환: 건수 요약.

    🔴 **종가 확률은 `prices.close_p` 로 다시 구한다.** `pick_ledger.odds_closing`
       은 우리 쪽 **배당** 하나라서 devig 을 못 한다(반대쪽이 없다).
    ⚠️ 한 행이 실패해도 나머지를 막지 않는다.
    """
    from app.engine.pick_ledger import predicted_side
    from app.learning import metrics as M
    from app.learning import prices as P

    out = {"read": 0, "inserted": 0, "skipped_no_side": 0, "failed": 0}
    rows = await pool.fetch(_PICKS_SQL)
    if limit:
        rows = rows[: int(limit)]
    async with pool.acquire() as conn:
        for r in rows:
            out["read"] += 1
            side = predicted_side(r["favored"], r["p_home"],
                                  r["predicted_side"])
            if side is None:
                out["skipped_no_side"] += 1
                continue
            p_model = _our_side_p(r["p_code"], side)
            p_mkt = _our_side_p(r["p_market"], side)
            try:
                p_close = await P.close_p(conn, game_id=r["game_id"], side=side)
            except Exception as exc:
                logger.info("[learning] 종가 확률 실패 game=%s: %s",
                            r["game_id"], exc)
                p_close = None
            res = _result_of(r["hit"], r["void"])
            row = {"p_market_at_decision": p_mkt, "p_close": p_close,
                   "result": res, "price_at_decision": r["odds_at_verdict"]}
            try:
                await conn.execute(
                    _INSERT,
                    str(r["judge_by"] or "bot_v14"), r["game_id"], r["sport"],
                    r["league"], side, r["judged_at"],
                    r["odds_at_verdict"], p_model, p_mkt, p_close,
                    r["odds_closing"], res, M.clv(row), M.roi_unit(row),
                    "settled" if res else "candidate",
                    f"backfill from pick_ledger#{r['id']}")
                out["inserted"] += 1
            except Exception as exc:
                out["failed"] += 1
                logger.warning("[learning] 적재 실패 pick=%s: %s", r["id"], exc)
    logger.info("[learning] 소급 적재 %s", out)
    return out


_LOAD = """
    SELECT engine, game_id, sport, league, market, line, side, book,
           ts_decided, price_at_decision, p_model, p_market_at_decision,
           p_close, result, clv, roi_unit, status
      FROM decision_ledger
     WHERE ($1::text IS NULL OR engine = $1)
       AND ($2::text IS NULL OR sport = $2)
     ORDER BY ts_decided
"""


async def load(pool, *, engine: str | None = None,
               sport: str | None = None) -> list[dict]:
    """지표 계산용 행 목록. ⚠️ 여기서 지표를 계산하지 않는다 —
    그건 `metrics.py`(순수 함수)의 일이다."""
    return [dict(r) for r in await pool.fetch(_LOAD, engine, sport)]
