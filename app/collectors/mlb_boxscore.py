"""[§9-라인업 전적] MLB 종료 경기 statsapi boxscore → lineup_events.

KBO 공식·NPB Yahoo `/top`과 같다. 사이트만 statsapi다.
`source='boxscore'` — 발표 라인업(crawler 스냅샷)과 섞지 않는다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.collectors.lineups import MLBLineupClient, parse_boxscore
from app.collectors.mlb import MLBClient, upsert_games

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


def parse_mlb_ip(v) -> float | None:
    """statsapi inningsPitched. '5.1' = 5이닝 1아웃, '5.2' = 2아웃."""
    s = str(v or "").strip()
    if not s or s in (".", "-", "—"):
        return None
    try:
        if "." in s:
            whole, frac = s.split(".", 1)
            outs = int(frac[0]) if frac else 0
            if outs not in (0, 1, 2):
                return float(s)
            return int(whole or 0) + outs / 3.0
        return float(int(s))
    except (TypeError, ValueError):
        return None


def parse_pitching(box: dict) -> dict[str, list[dict]]:
    """boxscore → {"home": [appearance, ...], "away": [...]}."""
    out: dict[str, list[dict]] = {"home": [], "away": []}
    teams = (box or {}).get("teams") or {}
    for side in ("home", "away"):
        team = teams.get(side) or {}
        players = team.get("players") or {}
        for i, pid in enumerate(team.get("pitchers") or []):
            key = pid if str(pid).startswith("ID") else f"ID{pid}"
            pdata = players.get(key) or {}
            person = pdata.get("person") or {}
            name = (person.get("fullName") or "").strip()
            if not name:
                continue
            st = ((pdata.get("stats") or {}).get("pitching") or {})
            pit = st.get("numberOfPitches")
            if pit is None:
                pit = st.get("pitchesThrown")
            row = {
                "name": name,
                "is_starter": i == 0,
                "innings": parse_mlb_ip(st.get("inningsPitched")),
                "batters": st.get("battersFaced"),
                "hits": st.get("hits"),
                "hr": st.get("homeRuns"),
                "k": st.get("strikeOuts"),
                "bb": st.get("baseOnBalls"),
                "r": st.get("runs"),
                "er": st.get("earnedRuns"),
            }
            if pit is not None:
                row["pitches"] = pit
            out[side].append(row)
    return out


def parse_batting(box: dict) -> dict[str, list[dict]]:
    """boxscore → {"home": [타자 성적, ...], "away": [...]}.

    🔴 [BAT-1 2026-09-08] **이 응답은 늘 오고 있었는데 버리고 있었다.**
       바로 위 `parse_pitching` 이 투수만 읽는다. 같은 `players` 사전에
       `stats.batting` 이 선수별로 들어 있다(실측: 팀당 11명).
       그래서 판정은 타자에 대해 자료3 의 **이름 아홉 개**밖에 몰랐고,
       라인업 확정이 재판정을 촉발하면 타순 **순서에서 추론**할 수밖에 없었다.
       실측: 잠정 70.4%(27경기) vs 확정 51.5%(130경기).

    ⚠️ **타석 기록 자체가 없는 선수만 뺀다** — `atBats` 가 `None` 인 경우다.
       🔴 [정정 2026-09-09] 종전 주석은 "없거나 **0**이면 싣지 않는다"였는데
          코드는 `None` 만 걸렀다. **주석이 거짓이었다.** 실측: 저장된 행 중
          `ab=0` 이 kbo 109/691 · mlb 49/582 · npb 17/119.
          그리고 **거르지 않는 쪽이 옳다** — 4볼넷 출루한 타자는 `ab=0` 이지만
          실제로 나온 경기다. 우리는 타율을 계산하지 않으므로 분모 오염도 없다
          (`batter_recent` 는 원본 합계만 준다).
       ⚠️ 다만 `경기` 는 **창 안의 경기 수**이지 타석이 있던 경기 수가 아니다.
          대주자로만 나온 경기도 1로 센다 — 판정은 `타수` 를 함께 본다.
    ⚠️ `battingOrder` 는 `"100"`(1번) · `"501"`(5번 자리 교체) 처럼 백 단위다.
       앞자리가 타순이다.
    """
    out: dict[str, list[dict]] = {"home": [], "away": []}
    teams = (box or {}).get("teams") or {}
    for side in ("home", "away"):
        team = teams.get(side) or {}
        for pdata in (team.get("players") or {}).values():
            person = (pdata or {}).get("person") or {}
            name = (person.get("fullName") or "").strip()
            if not name:
                continue
            st = ((pdata.get("stats") or {}).get("batting") or {})
            ab = st.get("atBats")
            if ab is None:
                continue                      # 타석 기록이 없다 — 지어내지 않는다
            order = pdata.get("battingOrder")
            slot = None
            try:
                if order is not None:
                    slot = int(str(order)) // 100 or None
            except (TypeError, ValueError):
                slot = None
            out[side].append({
                "batter": name,
                "slot": slot,
                "pos": ((pdata.get("position") or {}).get("abbreviation") or "").strip() or None,
                "ab": ab,
                "h": st.get("hits"),
                "r": st.get("runs"),
                "rbi": st.get("rbi"),
                "hr": st.get("homeRuns"),
                "bb": st.get("baseOnBalls"),
                "so": st.get("strikeOuts"),
            })
    return out


def _opt_stat(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v is None or v == "":
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def side_form_facts(box: dict, side: str) -> dict:
    """last-3 한 경기. 시즌 ERA는 넣지 않는다. 없는 칸은 생략."""
    from app.collectors.last3 import strip_banned

    pits = parse_pitching(box).get(side) or []
    starter = next((p for p in pits if p.get("is_starter")), None)
    rel = [p for p in pits if not p.get("is_starter")]
    team = ((box or {}).get("teams") or {}).get(side) or {}
    batting = ((team.get("teamStats") or {}).get("batting") or {})
    fielding = ((team.get("teamStats") or {}).get("fielding") or {})
    out: dict = {"bullpen_count": len(rel)}
    if starter:
        if starter.get("name"):
            out["starter_name"] = starter["name"]
        if starter.get("innings") is not None:
            out["starter_ip"] = starter["innings"]
        if starter.get("r") is not None:
            out["starter_r"] = starter["r"]
        if starter.get("pitches") is not None:
            out["starter_pitches"] = starter["pitches"]
    if rel:
        ip = [p["innings"] for p in rel if p.get("innings") is not None]
        if ip:
            out["bullpen_ip"] = round(sum(ip), 3)
    hits = _opt_stat(batting, "hits")
    if hits is not None:
        out["hits"] = hits
    hr = _opt_stat(batting, "homeRuns")
    if hr is not None:
        out["hr"] = hr
    bb = _opt_stat(batting, "baseOnBalls")
    if bb is not None:
        out["bb"] = bb
    k = _opt_stat(batting, "strikeOuts")
    if k is not None:
        out["k"] = k
    err = _opt_stat(fielding, "errors")
    if err is not None:
        out["errors"] = err
    return strip_banned(out)


def apply_boxscores(form: dict[str, dict], boxes_by_pk: dict) -> None:
    """schedule last-3에 boxscore 이닝·실점·타격 칸을 얹는다."""
    from app.collectors.last3 import strip_banned

    for pkt in (form or {}).values():
        for row in pkt.get("games") or []:
            pk = str(row.get("game_id") or "")
            box = (boxes_by_pk or {}).get(pk)
            if not box:
                continue
            side = "home" if row.get("home") else "away"
            row.update(side_form_facts(box, side))
            cleaned = strip_banned(dict(row))
            row.clear()
            row.update(cleaned)


def order_text(parsed_side: dict) -> str:
    names = parsed_side.get("batting_order") or []
    return "-".join(n for n in names if n)


# 선발 로테이션 5인 × 최근 2~3등판.
# ⚠️ NPB(6인 로테이션)는 28일이다 — 종목마다 로테이션이 다르므로 상수를
#    공유하지 않는다. 여기를 바꾸려면 MLB 실측 근거를 따로 대야 한다.
APPEARANCE_DAYS = 21


async def backfill(pool, as_of: date | None = None, days: int = APPEARANCE_DAYS,
                   limit_per_team: int = 10,
                   schedule_client: MLBClient | None = None,
                   lineup_client: MLBLineupClient | None = None) -> dict:
    """최근 종료 경기 선발 9명·등판을 `source='boxscore'`로 적재한다."""
    from app.collectors import batter_log
    from app.collectors.lineup_history import record
    from app.collectors.pitcher_log import record_appearances

    as_of = as_of or datetime.now(ET).date()
    schedule_client = schedule_client or MLBClient()
    lineup_client = lineup_client or MLBLineupClient()
    stats = {"games": 0, "rows": 0, "appearances": 0, "batters": 0,
             "skipped": 0, "no_game": 0, "teams": 0}
    per_team: dict[str, int] = {}

    for back in range(days):
        day = (as_of - timedelta(days=back)).isoformat()
        try:
            await upsert_games(pool, day, client=schedule_client)
        except Exception as exc:
            logger.warning("[MLB백필] 일정 %s 적재 실패: %s", day, exc)
        try:
            sched = await schedule_client.fetch_schedule(day)
        except Exception as exc:
            logger.warning("[MLB백필] 일정 %s 조회 실패: %s", day, exc)
            continue
        from app.collectors.mlb import _parse_games

        for g in _parse_games(sched):
            if g.get("status") != "final":
                stats["skipped"] += 1
                continue
            gid_db = await pool.fetchval(
                "SELECT id FROM games WHERE sport = $1 AND ext_id = $2",
                "mlb", g["ext_id"]) if pool else None
            if gid_db is None:
                stats["no_game"] += 1
                continue
            try:
                box = await lineup_client.fetch_boxscore(g["ext_id"])
            except Exception as exc:
                logger.debug("[MLB백필] %s boxscore 실패: %s", g["ext_id"], exc)
                stats["skipped"] += 1
                continue
            # 🔴 [BAT-3] **타순 확정 관문보다 앞에서 적재한다.** 아래
            #    `confirmed` 가 False 면 이 경기는 통째로 버려지는데, 타자
            #    성적은 타순 확정 여부와 무관하게 이미 응답에 와 있다.
            #    NPB 가 2026-09-01 에 같은 모양의 결함을 겪었다(打順 실패가
            #    등판까지 버려 선발 32.6%가 표본 ≤1).
            stats["batters"] += await batter_log.store_batting(
                pool, gid_db, "mlb", parse_batting(box), source="boxscore")
            parsed = parse_boxscore(box)
            if not parsed.get("confirmed"):
                stats["skipped"] += 1
                continue
            pits = parse_pitching(box)
            stats["games"] += 1
            for side in ("home", "away"):
                team = g[side]
                if per_team.get(team, 0) >= limit_per_team:
                    continue
                text = order_text(parsed.get(side) or {})
                starter = next((p["name"] for p in (pits.get(side) or [])
                                if p.get("is_starter") and p.get("name")), None)
                if await record(pool, gid_db, side, team, text,
                                starter=starter, source="boxscore"):
                    stats["rows"] += 1
                    per_team[team] = per_team.get(team, 0) + 1
            stats["appearances"] += await record_appearances(
                pool, gid_db, "mlb", g["home"], g["away"], pits,
                source="boxscore")
    stats["teams"] = len(per_team)
    logger.info("[MLB백필] 경기 %d · 적재 %d행 · 등판 %d · 타자 %d · %d팀 "
                "(건너뜀 %d · 경기없음 %d)",
                stats["games"], stats["rows"], stats.get("appearances", 0),
                stats["batters"], stats["teams"], stats["skipped"], stats["no_game"])
    return stats
