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
    SELECT o.market, o.side, o.line, o.odds, o.snap_tag, o.provider, o.captured_at
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


def _sets(rows, home: str, away: str) -> list:
    """시각별 **완전한 h2h 한 벌** → `[(시각, 홈확률)]`, 오래된 것부터.

    🔴 [MOV-H 2026-09-23] 개장가를 뽑으려면 시각별로 갈라야 한다. 종전
       `_h2h` 는 "가장 최근 한 벌"만 냈다.
    🔴 **`impossible_set` 을 여기서도 지난다.** ODD-S 게이트는 앞으로 들어올
       것만 막고, 이미 쌓인 244행(kbo 145 · npb 94 · mlb 5)은 DB 에 남아
       있다. 거르지 않으면 **깨진 호가가 개장가로 뽑힌다.**
       판정은 `odds_math.impossible_set` 하나가 한다 — 사본 금지.
    ⚠️ 반쪽 벌(한 쪽만 온 시각)은 세지 않는다. 확률을 만들 수 없다.
    """
    from app.flow.odds_math import devig_2way, devig_3way, impossible_set

    by: dict = {}
    for r in rows:
        if (r.get("market") or "") != "h2h":
            continue
        ts = r.get("captured_at")
        if ts is None:
            continue
        side = str(r.get("side") or "")
        key = ("home" if side == home else
               "away" if side == away else
               "draw" if side.lower() in ("draw", "무", "tie") else None)
        if key is None:
            continue
        try:
            by.setdefault(ts, {})[key] = float(r["odds"])
        except (TypeError, ValueError):
            continue
    out = []
    for ts, q in sorted(by.items()):
        if impossible_set(list(q.values())):
            continue
        if {"home", "draw", "away"} <= set(q):
            ph = devig_3way(q["home"], q["draw"], q["away"])[0]
        elif {"home", "away"} <= set(q):
            ph = devig_2way(q["home"], q["away"])[0]
        else:
            continue
        out.append((ts, round(ph, 4)))
    return out


def move_of(rows, home: str, away: str) -> dict:
    """개장 → 현재 **홈 기준** 이동. 🔴 못 재면 `move_pp` 는 **None** 이다.

    ⚠️ 0 과 모름은 다른 말이다(MOV-1 이 적은 규약). 한 벌뿐이면 "안 움직였다"
       가 아니라 "모른다"다.
    """
    pts = _sets(rows, home, away)
    if not pts:
        return {"move_pp": None, "n_snaps": 0, "open_home": None,
                "now_home": None, "since": None}
    if len(pts) == 1:
        return {"move_pp": None, "n_snaps": 1, "open_home": pts[0][1],
                "now_home": pts[0][1], "since": pts[0][0]}
    return {"move_pp": round((pts[-1][1] - pts[0][1]) * 100, 2),
            "n_snaps": len(pts), "open_home": pts[0][1],
            "now_home": pts[-1][1], "since": pts[0][0]}


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
                            "move": move_of(rows, state.home, state.away),
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
        # 🔴 [MOV-H] 개장 → 현재 이동. ④가 이것을 가설에 접목한다.
        "move": move_of(rows, state.home, state.away),
        "market_missing": False,
    }
    logger.info("[flow:n02] game=%s p_home %.3f · p_away %.3f%s",
                state.game_id, p["home"], p["away"],
                f" · draw {p['draw']:.3f}" if p.get("draw") else "")
    return state
