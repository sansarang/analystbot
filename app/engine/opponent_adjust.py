"""[자료1 상대 보정] **누구를 상대로 낸 득점인가**를 숫자로 만든다.

🔴 왜 (실측 2026-09-07 WSH@LAD 리허설): 판정은 이미 상대 수준을 **서술로**
   보고 있었다 — 근거2 가 `"경기당 4.67득점, 상대순위 3~4위"` 였다. 자료1 이
   `opponent_rank`·`opponent_win_pct` 를 이미 싣기 때문이다.
   없는 것은 그것을 **숫자로 합친 값**이다. 판정이 세 줄을 맨눈으로 보정하고
   있었고, 그 보정은 근거에 남지도 채점되지도 않았다.

⚠️ **시즌 집계표가 아니다.** 상대의 **최근 `m1_opp_window` 경기** 실점만 센다.
   대원칙(`app/engine/CLAUDE.md`)이 금지하는 것은 시즌 누적이고, 이것은
   자료9(불펜 최근 3경기)·자료12(경기마다 갱신되는 상태값)와 같은 부류다.
⚠️ 순위·승률로 보정하지 않는다. 순위는 팀의 **종합** 성적이고 우리가 묻는
   것은 **그 팀이 요즘 몇 점을 내주는가** 하나다.
⚠️ 표본이 얇은 상대는 **뺀다**. 얇은 숫자로 얇은 숫자를 보정하면 오늘
   자료13 이 무너진 자리로 돌아간다(표본 1~3짜리 비율의 곱).

원천은 `games` 뿐이다 — 새 크롤 소스를 만들지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 그 팀이 `before` 이전 최근 N경기에서 **내준** 점수.
_OPP_ALLOWED = """
    SELECT count(*) AS n, avg(allowed) AS ra
      FROM (
        SELECT CASE WHEN home = $2 THEN away_score ELSE home_score END AS allowed
          FROM games
         WHERE sport = $1 AND status = 'final'
           AND home_score IS NOT NULL AND away_score IS NOT NULL
           AND ($2 = home OR $2 = away)
           AND starts_at < $3
         ORDER BY starts_at DESC
         LIMIT $4
      ) t
"""


def _cfg():
    from app.config import get_settings

    return get_settings()


async def opponent_allowed(pool, sport: str, team: str, before) -> dict:
    """그 상대가 최근 창에서 경기당 몇 점을 내줬나. 못 재면 빈 dict."""
    if pool is None or not sport or not team or before is None:
        return {}
    s = _cfg()
    try:
        row = await pool.fetchrow(_OPP_ALLOWED, sport, team, before,
                                  int(s.m1_opp_window))
    except Exception as exc:
        logger.debug("[m1-adj] %s %s 상대 실점 조회 실패: %s", sport, team, exc)
        return {}
    n = int((row or {}).get("n") or 0)
    if n < int(s.m1_opp_min_games):
        return {}
    return {"경기": n, "경기당실점": round(float(row["ra"] or 0), 2)}


async def side_block(pool, sport: str, jg: dict, side: str) -> dict:
    """한 팀의 상대 보정. 3경기 중 **잴 수 있는 것만** 쓰고 몇 건인지 밝힌다.

    `배율` 은 "상대가 평소 내주는 만큼 냈으면 1.0" 이다.
    1.2 면 상대 평균보다 20% 더 냈다는 뜻이고, 그게 자료1 의 원시
    `runs_per_game_l3` 가 말하지 못하는 부분이다.
    """
    from app.engine.starter_recent import _aware

    r = jg.get("research") or {}
    u = r.get(f"{side}_usage") or {}
    games = u.get("games")
    if not isinstance(games, list) or not games:
        return {}
    got, runs, allowed = 0, 0.0, 0.0
    for g in games:
        opp = g.get("opponent")
        when = _aware(g.get("date"))
        if not opp or when is None or g.get("runs") is None:
            continue
        blk = await opponent_allowed(pool, sport, opp, when)
        if not blk:
            continue
        got += 1
        runs += float(g["runs"])
        allowed += float(blk["경기당실점"])
    if not got or allowed <= 0:
        return {}
    out = {"대상경기": got, "총경기": len(games),
           "상대평균실점": round(allowed / got, 2),
           "우리득점": round(runs / got, 2),
           "배율": round((runs / got) / (allowed / got), 2)}
    if got < len(games):
        out["주의"] = f"{len(games)}경기 중 {got}경기만 보정(상대 표본 부족)"
    return out


async def attach(pool, jg: dict) -> bool:
    """`jg["m1_adjust"]` 를 채운다. 한쪽이라도 재면 True.

    ⚠️ I/O 는 여기서 끝낸다 — 판정 경로(`matchup.boxscore_payload`)는 이미
       채워진 값을 읽기만 한다. 자료10·11 과 같은 규약이다.
    """
    sport = (jg.get("sport") or "").lower()
    out: dict = {}
    for side in ("home", "away"):
        try:
            blk = await side_block(pool, sport, jg, side)
        except Exception as exc:
            logger.warning("[m1-adj] %s %s 보정 실패: %s", sport, side, exc)
            blk = {}
        if blk:
            out[side] = blk
    jg["m1_adjust"] = out
    if out:
        logger.info("[m1-adj] game=%s %s", jg.get("game_id"),
                    " · ".join(f"{k} 배율 {v['배율']}(상대 {v['상대평균실점']}실점, "
                               f"{v['대상경기']}/{v['총경기']}경기)"
                               for k, v in out.items()))
    else:
        logger.info("[m1-adj] game=%s 보정 불가 — 상대 표본 부족", jg.get("game_id"))
    return bool(out)
