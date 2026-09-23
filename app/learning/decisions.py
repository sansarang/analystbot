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

#: 🔴 [LED-1 2026-09-23 사용자 지시 "전부다 순서대로 수정해라"] **채점 대상.**
#   끝난 경기 · 아직 `result` 가 없는 행만. 점수가 없으면 고르지 않는다.
#   ⚠️ `market='h2h'` 만이다 — 총점·핸디 채점 규칙은 아직 없고, 없는 규칙을
#      지어내면 그게 거짓 성적이 된다.
_PENDING_SQL = """
    SELECT d.id, d.side, d.market, d.line, d.price_at_decision,
           g.home_score, g.away_score
      FROM decision_ledger d
      JOIN games g ON g.id = d.game_id
     WHERE d.result IS NULL
       AND g.status = 'final'
       AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
     ORDER BY d.id
     LIMIT $1
"""

_GRADE_SQL = """
    UPDATE decision_ledger
       SET result = $2, roi_unit = $3, status = 'settled', settled_at = now()
     WHERE id = $1
"""


def _h2h_result(side: str, hs, aws) -> str | None:
    """승패 채점. 🔴 모르면 **None**(건너뛴다) — 지어내지 않는다."""
    try:
        h, a = int(hs), int(aws)
    except (TypeError, ValueError):
        return None
    if h == a:
        return "push"
    won = "home" if h > a else "away"
    if side not in ("home", "away"):
        return None
    return "win" if side == won else "loss"


def _roi(result: str, price) -> float | None:
    """단위 스테이크 손익. 🔴 **가격이 없으면 None** — 0 으로 채우지 않는다.

    ⚠️ LE1-ROI 에서 겪은 실패다: 진 것만 −1 로 세고 이긴 것은 가격이 없다고
       버려서 ROI 가 −0.4656 으로 나왔다(고친 뒤 +0.0837).
    """
    if result == "push":
        return 0.0
    try:
        o = float(price)
    except (TypeError, ValueError):
        return None
    if result == "win":
        return round(o - 1.0, 4)
    if result == "loss":
        return -1.0
    return None


async def grade_pending(pool, *, limit: int = 2000) -> dict:
    """[LED-1] 끝난 경기의 원장 행을 채점한다.

    🔴 **왜 필요한가.** 실측 2026-09-23: `decision_ledger` 1,118행 중
       `flow_v14` 740행이 **채점 0** 이었다 — 흐름 판정이 맞았는지 셀 방법이
       없었고, 그러면 ⑦ 조정도 ⑨ 확신도 고칠 근거가 없다.

    🔴 **끝나지 않은 경기는 건드리지 않는다.** 점수가 없으면 건너뛴다.
    🔴 **모르는 마켓은 건너뛴다** — 총점·핸디 규칙이 아직 없고, 없는 규칙을
       지어내면 거짓 성적이 된다. 건너뛴 수를 세어 돌려준다(조용한 0 금지).
    ⚠️ 한 행이 실패해도 나머지는 간다.
    """
    out = {"seen": 0, "graded": 0, "skipped": 0, "failed": 0}
    if pool is None:
        return out
    try:
        rows = await pool.fetch(_PENDING_SQL, int(limit))
    except Exception as exc:
        logger.warning("[decisions] 채점 대상 조회 실패: %s", exc)
        return out
    for r in rows:
        out["seen"] += 1
        if str(r["market"] or "") != "h2h":
            out["skipped"] += 1
            continue
        res = _h2h_result(r["side"], r["home_score"], r["away_score"])
        if res is None:
            out["skipped"] += 1
            continue
        try:
            await pool.execute(_GRADE_SQL, r["id"], res,
                               _roi(res, r["price_at_decision"]))
            out["graded"] += 1
        except Exception as exc:
            out["failed"] += 1
            logger.warning("[decisions] 채점 실패 id=%s: %s", r["id"], exc)
    logger.info("[decisions] 원장 채점: %s", out)
    return out

#: 🔴 [CLV-F 2026-09-23 사용자 지시 "딥서치해서 찾아서 수정해라"] **CLV 대상.**
#
#   딥서치 근거(→ docs/FORKS.md F-20): CLV 는 **결과보다 빠른 신호**다 —
#   적중률은 결과 지표라 50건의 60% 적중이 운으로도 나오지만, CLV 는 과정
#   지표라 같은 표본에서 훨씬 덜 흔들린다. 양의 CLV 를 꾸준히 내는 쪽이
#   장기 수익을 낸다.
#
#   실측 2026-09-23: flow_v14 원장 23경기 중 **종료는 2건**인데 **종가
#   스냅샷은 17건**이다 — 결과를 기다리면 2건, CLV 로 재면 17건이다.
#
# 🔴 **킥오프가 지난 경기만** 고른다. 아직 안 끝난 경기의 "종가"는 종가가
#    아니다. 누설(look-ahead)은 `prices.CLOSE_WHERE` 가 이미 막는다 —
#    `captured_at <= LEAST(기준, starts_at)` 이라 킥오프 이후 스냅샷은
#    애초에 안 들어온다.
# ⚠️ 이미 채운 행은 다시 안 본다.
_CLV_PENDING_SQL = """
    SELECT d.id, d.game_id, d.side, d.market, d.line, d.p_market_at_decision
      FROM decision_ledger d
      JOIN games g ON g.id = d.game_id
     WHERE d.p_close IS NULL
       AND d.p_market_at_decision IS NOT NULL
       AND g.starts_at < now()
     ORDER BY d.id
     LIMIT $1
"""

_CLV_SET_SQL = """
    UPDATE decision_ledger SET p_close = $2, clv = $3 WHERE id = $1
"""


async def fill_clv(pool, *, limit: int = 2000) -> dict:
    """[CLV-F] 종가로 CLV 를 채운다 — **결과를 기다리지 않는다.**

    🔴 부호 규약의 원본은 `metrics.clv` 하나다(사본 금지): 종가가 **우리
       쪽으로** 움직이면 양수다. 두 확률은 같은 쪽 기준이어야 하고, 그 변환은
       적재할 때(`_our_side_p`) 이미 끝나 있다.
    ⚠️ 한 행이 실패해도 나머지는 간다. 건너뛴 수를 센다(조용한 0 금지).
    """
    from app.learning import metrics as _M
    from app.learning import prices as _P

    out = {"seen": 0, "filled": 0, "skipped": 0, "failed": 0}
    if pool is None:
        return out
    try:
        rows = await pool.fetch(_CLV_PENDING_SQL, int(limit))
    except Exception as exc:
        logger.warning("[decisions] CLV 대상 조회 실패: %s", exc)
        return out
    for r in rows:
        out["seen"] += 1
        base = r["p_market_at_decision"]
        if base is None:
            out["skipped"] += 1
            continue
        try:
            pc = await _P.close_p(pool, game_id=int(r["game_id"]),
                                  side=str(r["side"]),
                                  market=str(r["market"] or "h2h"),
                                  line=r["line"])
        except Exception as exc:
            out["failed"] += 1
            logger.warning("[decisions] 종가 조회 실패 id=%s: %s", r["id"], exc)
            continue
        if pc is None:
            out["skipped"] += 1
            continue
        v = _M.clv({"p_market_at_decision": float(base), "p_close": float(pc)})
        if v is None:
            out["skipped"] += 1
            continue
        try:
            await pool.execute(_CLV_SET_SQL, r["id"], round(float(pc), 6),
                               round(float(v), 6))
            out["filled"] += 1
        except Exception as exc:
            out["failed"] += 1
            logger.warning("[decisions] CLV 기록 실패 id=%s: %s", r["id"], exc)
    logger.info("[decisions] CLV 채움: %s", out)
    return out

#: 🔴 [CLV-B 2026-09-23] **옛 원장의 시장 확률·가격을 소급 복원한다.**
#
#   실측: flow_v14 740행 전건 `p_market_at_decision` 이 NULL 이라 CLV 대상이
#   0건이었다. LED-1 에서 키를 고쳤지만 그건 새 행부터고, 옛 행은 영원히
#   빈칸이다. 결정 시각 **이전** h2h 스냅샷은 740/740 전건 있다.
#
# 🔴 **누설이 아니다.** `captured_at <= ts_decided` 만 쓴다 — 결정 시점에
#    이미 있던 가격이다(딥서치 F-20 이 1순위 위협으로 꼽은 look-ahead 를
#    이 조건이 막는다). 종가는 건드리지 않는다 — `fill_clv` 가 따로 한다.
# ⚠️ **덮어쓰지 않는다.** 이미 값이 있으면 대상이 아니다 — 갈아치우면 그때
#    무엇을 봤는지가 사라진다.
_BF_PENDING_SQL = """
    SELECT id, game_id, side, market, line, ts_decided
      FROM decision_ledger
     WHERE p_market_at_decision IS NULL
     ORDER BY id
     LIMIT $1
"""

_BF_SET_SQL = """
    UPDATE decision_ledger
       SET p_market_at_decision = $2,
           price_at_decision = COALESCE(price_at_decision, $3)
     WHERE id = $1
"""


async def backfill_market(pool, *, limit: int = 5000) -> dict:
    """[CLV-B] 결정 시점 시장 확률·가격을 소급으로 채운다.

    🔴 디빅 규약의 원본은 `prices.devig` 하나다(사본 금지).
    ⚠️ 한 행이 실패해도 나머지는 간다. 건너뛴 수를 센다.
    """
    from app.learning import prices as _P

    out = {"seen": 0, "filled": 0, "skipped": 0, "failed": 0}
    if pool is None:
        return out
    try:
        rows = await pool.fetch(_BF_PENDING_SQL, int(limit))
    except Exception as exc:
        logger.warning("[decisions] 소급 대상 조회 실패: %s", exc)
        return out
    for r in rows:
        out["seen"] += 1
        side = str(r["side"] or "")
        try:
            raw = await _P.last_prices(pool, game_id=int(r["game_id"]),
                                       market=str(r["market"] or "h2h"),
                                       at=r["ts_decided"], line=r["line"])
        except Exception as exc:
            out["failed"] += 1
            logger.warning("[decisions] 소급 가격 조회 실패 id=%s: %s", r["id"], exc)
            continue
        if not raw or side not in raw:
            out["skipped"] += 1
            continue
        pr = _P.devig(raw)
        p = pr.get(side)
        if p is None:
            out["skipped"] += 1
            continue
        try:
            await pool.execute(_BF_SET_SQL, r["id"], round(float(p), 6),
                               float(raw[side]))
            out["filled"] += 1
        except Exception as exc:
            out["failed"] += 1
            logger.warning("[decisions] 소급 기록 실패 id=%s: %s", r["id"], exc)
    logger.info("[decisions] 시장 확률 소급: %s", out)
    return out

#: 🔴 [CLV-S 2026-09-23] **한 선택당 한 번만 센다.**
#
#   딥서치 근거(→ docs/FORKS.md F-21): "베팅 시점에 받은 가격은 **고정된
#   스냅샷**이고 **재평가하지 않는다**". CLV 는 선택당 한 번 재는 것이다.
#
#   실측: 흐름은 한 경기를 여러 번 판단한다(15분 잡). 킥오프 직전 재평가는
#   **정의상 CLV≈0 또는 음수**다 — 그 가격이 이미 종가다:
#     0~30분   33행 · CLV0 27 · 양수   0
#     30~90분  68행 · CLV0 50 · 양수   0
#     180분+  401행 · CLV0 89 · 양수 166 · 평균 +0.00273
#   섞어 평균 내면 일찍 내린 판단의 값어치가 지워진다(실측 30.8%).
#
# ⚠️ 자료를 지우지 않는다 — 원장은 그대로 두고 **세는 법**을 고친다.
#    `DISTINCT ON (game_id, side)` + `ts_decided` 오름차순 = **첫 판단**.
_CLV_SUM_SQL = """
    SELECT DISTINCT ON (game_id, side) clv
      FROM decision_ledger
     WHERE clv IS NOT NULL
       AND ($1::text IS NULL OR engine = $1)
     ORDER BY game_id, side, ts_decided
"""

#: 🔴 딥서치: CLV 도 **200~500건**은 있어야 "실력"이라 말할 수 있다.
#   그 아래에서는 숫자를 내되 **결론을 붙이지 않는다.**
CLV_ENOUGH_N = 200


async def clv_summary(pool, *, engine: str | None = None) -> dict:
    """[CLV-S] CLV 요약 — **선택당 첫 판단 하나**만 센다.

    반환 `{n, avg, beat, flat, moved, beat_of_moved, enough}`.

    🔴 `flat`(CLV 정확히 0)을 **따로 센다.** 0 은 "졌다"가 아니라 "시장이
       안 움직였다"다. 섞으면 거짓 비관이 나온다(실측 30.8%).
    ⚠️ 표본이 없으면 `avg` 는 **None** 이다 — 0 으로 적지 않는다.
    """
    out = {"n": 0, "avg": None, "beat": 0, "flat": 0, "moved": 0,
           "beat_of_moved": 0, "enough": False}
    if pool is None:
        return out
    try:
        rows = await pool.fetch(_CLV_SUM_SQL, engine)
    except Exception as exc:
        logger.warning("[decisions] CLV 요약 실패: %s", exc)
        return out
    vals = []
    for r in rows:
        try:
            vals.append(float(r["clv"]))
        except (TypeError, ValueError):
            continue
    if not vals:
        return out
    eps = 1e-9
    out["n"] = len(vals)
    out["avg"] = round(sum(vals) / len(vals), 6)
    out["beat"] = sum(1 for v in vals if v > eps)
    out["flat"] = sum(1 for v in vals if abs(v) <= eps)
    moved = [v for v in vals if abs(v) > eps]
    out["moved"] = len(moved)
    out["beat_of_moved"] = sum(1 for v in moved if v > 0)
    out["enough"] = len(vals) >= CLV_ENOUGH_N
    return out
