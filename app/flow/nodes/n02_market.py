"""[v1.4 STEP 3] ② 시장값 — 배당을 **마진 제거 확률**로 바꾼다.

🔴 `p`(devig)와 `required`(1/배당)를 **필드로 분리한다.** 섞으면 ⑪의 edge 가
   늘 마진만큼 양수로 나와 거짓 픽이 된다(지시문 STEP 3 "흔한 오류").
🔴 야구는 `devig_2way`, 축구는 `devig_3way` 만 부른다.
⚠️ 배당이 없으면 `p=None` · `market_missing=True`. 확률을 지어내지 않는다.
⚠️ 파생(총점·팀토탈·핸디)은 **원배당 그대로** 싣는다 — ⑪이 쓴다.
"""
from __future__ import annotations

import logging

from app.flow.odds_math import devig_2way, devig_3way

logger = logging.getLogger(__name__)

NODE = "n02_market"

#: 이름표 붙은 스냅샷만 본다. 기준선 규칙의 원본은 `odds_move.BASELINE_ORDER` 다.
_SQL = """
    SELECT o.market, o.side, o.line, o.odds, o.snap_tag, o.provider
      FROM odds_snapshots o
     WHERE o.game_id = $1
     ORDER BY o.captured_at DESC
"""


async def _rows(state, ctx) -> list:
    if "odds_rows" in (ctx.inject or {}):
        return list(ctx.inject["odds_rows"] or [])
    if ctx.pool is None:
        return []
    try:
        gid = int(state.game_id)
    except (TypeError, ValueError):
        return []
    try:
        return [dict(r) for r in await ctx.pool.fetch(_SQL, gid)]
    except Exception as exc:
        logger.warning("[flow:n02] 배당 조회 실패 game=%s: %s", state.game_id, exc)
        return []


def _h2h(rows, home: str, away: str) -> dict:
    """가장 최근 h2h 한 벌. `side` 는 **팀 이름**이다(0-b 실측)."""
    out: dict = {}
    for r in rows:
        if (r.get("market") or "") != "h2h":
            continue
        side = str(r.get("side") or "")
        key = ("home" if side == home else
               "away" if side == away else
               "draw" if side.lower() in ("draw", "무", "tie") else None)
        if key and key not in out:
            out[key] = float(r["odds"])
    return out


def _derivatives(rows, home: str, away: str) -> dict:
    """총점·핸디·팀토탈 원배당. **가공하지 않는다.**"""
    der: dict = {"total": {}, "ah": [], "team_total_home": {},
                 "team_total_away": {}}
    for r in rows:
        m, side = (r.get("market") or ""), str(r.get("side") or "")
        line = None if r.get("line") is None else float(r["line"])
        odds = float(r["odds"])
        low = side.lower()
        if m == "totals":
            if "over" in low and "over" not in der["total"]:
                der["total"].update({"line": line, "over": odds})
            elif "under" in low and "under" not in der["total"]:
                der["total"].update({"line": line, "under": odds})
        elif m == "spreads":
            der["ah"].append({"line": line, "side": side, "odds": odds})
        elif m in ("team_totals", "team_total"):
            slot = ("team_total_home" if home and home in side else
                    "team_total_away" if away and away in side else None)
            if slot:
                key = "over" if "over" in low else "under"
                der[slot].setdefault("line", line)
                der[slot].setdefault(key, odds)
    return der


async def run(state, ctx):
    """② 시장값."""
    rows = await _rows(state, ctx)
    odds = _h2h(rows, state.home, state.away)
    sport = (state.sport or "").lower()

    have = ({"home", "draw", "away"} <= set(odds) if sport == "soccer"
            else {"home", "away"} <= set(odds))
    if not have:
        logger.info("[flow:n02] game=%s 배당 없음 — 시장 없음", state.game_id)
        state.n02_market = {"odds": odds or {}, "p": None, "required": None,
                            "derivatives": _derivatives(rows, state.home, state.away),
                            "market_missing": True}
        return state

    if sport == "soccer":
        ph, pd, pa = devig_3way(odds["home"], odds["draw"], odds["away"])
        p = {"home": round(ph, 4), "draw": round(pd, 4), "away": round(pa, 4)}
    else:
        ph, pa = devig_2way(odds["home"], odds["away"])
        p = {"home": round(ph, 4), "draw": None, "away": round(pa, 4)}

    state.n02_market = {
        "odds": odds, "p": p,
        # 🔴 요구확률은 **따로** 둔다. `p` 와 같은 자리에 넣지 않는다.
        "required": {k: round(1.0 / v, 4) for k, v in odds.items()},
        "derivatives": _derivatives(rows, state.home, state.away),
        "market_missing": False,
    }
    logger.info("[flow:n02] game=%s p_home %.3f · p_away %.3f%s",
                state.game_id, p["home"], p["away"],
                f" · draw {p['draw']:.3f}" if p.get("draw") else "")
    return state
