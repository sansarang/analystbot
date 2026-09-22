"""[§9-라인업 전적] NPB 종료 경기 Yahoo `/top` 打順 → lineup_events.

왜 필요한가 (2026-08-28 실측):
  KBO는 공식 박스스코어 백필이 있어 유사 타순 전적이 붙는다. NPB는
  `lineup_events` 0행 · 크롤러는 선발 투수만 넣었다. attach()는 종목 공용이라
  재료가 없으면 전적이 안 나온다.

⚠️ 이것은 **실제 출전 기록**이다. 발표 라인업(crawler)과 섞지 않는다.
⚠️ `/stats`·npb.jp 「最新のオーダー」는 교체·막판 타순이다. `/top`의
   `打順` 1~9번만 쓴다(실측: 대타 행 없음).
⚠️ 경기 매칭은 날짜 + 홈/원정. 날짜만으로 고르면 같은 날 6경기 중 아무거나 잡힌다.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.collectors.yahoo_npb import (
    TEAM_TO_ODDS,
    YahooNPBClient,
    parse_batter_rows,
    parse_batting_orders,
    parse_finals,
    parse_pitching_stats,
    score_card_html,
)

logger = logging.getLogger(__name__)

NPB_TEAMS = tuple(TEAM_TO_ODDS.values())
JST = ZoneInfo("Asia/Tokyo")


async def fetch_final_lineups(game_id: str, client: YahooNPBClient) -> dict:
    """한 종료 경기 → {"home": [9], "away": [9]} 또는 빈 dict."""
    html = await client.game(game_id)
    lu = parse_batting_orders(html)
    if not lu["home"] or not lu["away"]:
        return {}
    return lu


def parse_batting(html: str) -> dict:
    """[BAT-2] Yahoo `/stats` → {"home": [...], "away": [...]}.

    ⚠️ **첫 표가 원정**이다 — `parse_pitching_stats`·`parse_batting_stats` 와
       같은 규약이고, `/top` 打順(홈 먼저)과는 **반대**다. 섞지 않는다.
    ⚠️ 표가 둘 다 잡히지 않으면 **빈 목록**을 준다. 한쪽만 있는 것을 홈/원정
       중 하나로 고르면 반대편 팀에 붙는다.
    """
    found = parse_batter_rows(html)
    if len(found) < 2:
        return {"home": [], "away": []}
    return {"away": found[0], "home": found[1]}


# 선발 로테이션 × 최근 등판. 타순 이력 상한(팀당 10경기)과 창을 나눈다.
# 14일로 자르면 오늘 선발이 등판 1회만 남는다 (실측 2026-08-29, 12명 중 10명 n=1).
#
# 🔴 **NPB는 6인 로테이션이라 KBO·MLB(5인)와 같은 창을 쓰면 안 된다.**
#    실측 2026-09-01 — 최근 21일 창에서 오늘 선발 12명의 등판 수:
#      3등판  大野 雄大 · モイネロ · 九里 亜蓮 · 平良 海馬
#      2등판  吉村 · 髙橋 · 床田 · 山﨑
#      1등판  石田 · 伊藤            ← 추천 게이트 탈락(MIN_STARTS)
#      0등판  戸郷 · 高野
#    상한이 정확히 3이다. 21 ÷ 6 = 3.5 이므로 구조적 한계다.
#    같은 날 평균 표본: KBO 3.39 · MLB 2.25 · **NPB 1.57**.
#    그 결과 최근 7일 NPB 선발의 **32.6%**가 "표본 ≤1"로 추천 자격을 잃었다
#    (KBO 0% · MLB 14.4%). 수집 결함도 이름 불일치도 아니었다 —
#    타순 파싱은 102/102 성공, 등판·타순 어긋난 경기 0건으로 확인했다.
#    28일이면 6인 로테이션에서 4~5등판이 잡힌다.
APPEARANCE_DAYS = 28


async def backfill(pool, as_of: date | None = None, days: int = APPEARANCE_DAYS,
                   limit_per_team: int = 10,
                   client: YahooNPBClient | None = None) -> dict:
    """최근 종료 경기 선발 9명·등판을 `source='boxscore'`로 적재한다.

    타순 이력은 팀당 `limit_per_team`에서 멈춘다. 등판 로그는 창 안의
    종료 경기를 건너뛰지 않는다 — 건너뛰면 오늘 선발의 2~3등판이 빈다.
    """
    from app.collectors import batter_log
    from app.collectors.game_match import _FIND
    from app.collectors.lineup_history import record
    from app.collectors.pitcher_log import record_appearances

    client = client or YahooNPBClient()
    as_of = as_of or datetime.now(JST).date()
    stats = {"games": 0, "rows": 0, "appearances": 0, "batters": 0,
             "skipped": 0, "no_game": 0, "teams": 0}
    per_team: dict[str, int] = {}
    seen: set[str] = set()

    for back in range(days):
        day = (as_of - timedelta(days=back)).isoformat()
        try:
            html = score_card_html(await client.schedule(day))
            finals = parse_finals(html)
        except Exception as exc:
            logger.warning("[NPB백필] 일정 %s 실패: %s", day, exc)
            continue
        starts = datetime.fromisoformat(f"{day}T18:00:00").replace(
            tzinfo=JST).astimezone(UTC)
        for g in finals:
            gid = g["game_id"]
            if gid in seen:
                continue
            seen.add(gid)
            gid_db = await pool.fetchval(
                "SELECT id FROM games WHERE sport = $1 AND ext_id = $2",
                "npb", f"yahoo:{gid}") if pool else None
            if gid_db is None and pool:
                # 🔴 [FIND-6 2026-09-23] KBO 와 **같은 결함**이었다 —
                #    인자 5개. 여기는 위의 `yahoo:{gid}` 조회가 먼저 맞아
                #    대부분 가려져 있었다(NPB 적재는 09-21 까지 살아 있었다).
                #    ⚠️ 접두사를 일정과 다르게 둔다(병합되게).
                gid_db = await pool.fetchval(
                    _FIND, "npb", g["home"], g["away"], starts, 20,
                    f"npbbox:{gid}")
            if gid_db is None:
                stats["no_game"] += 1
                continue
            # 🔴 **타순과 등판을 한 관문에 묶지 않는다.**
            #    종전에는 `/top` 打順 파싱이 실패하면 `continue` 로 빠져나가
            #    **투수 등판까지 함께 버렸다.** 타순은 `/top`, 등판은 `/stats`
            #    로 **서로 다른 페이지**인데, /stats 는 멀쩡히 응답했을 수도
            #    있는 것을 시도조차 하지 않았다.
            #    실측 2026-09-01: NPB 등판 858행(선발 204)으로 KBO 1,860행
            #    (선발 371)의 절반이었고, 그 결과 최근 7일 선발의 32.6%가
            #    "표본 ≤1"로 잡혀 추천 자격을 잃었다(KBO 0% · MLB 14.4%).
            lu = {}
            try:
                lu = await fetch_final_lineups(gid, client)
            except Exception as exc:
                logger.debug("[NPB백필] %s 打順 조회 실패: %s", gid, exc)
            pits = {"home": [], "away": []}
            bats: dict = {}
            try:
                # 🔴 [BAT-3] 투수표와 타자표가 **같은 페이지**다. 한 번만 받는다.
                st_html = await client.stats(gid)
                pits = parse_pitching_stats(st_html)
                bats = parse_batting(st_html)
            except Exception as exc:
                logger.debug("[NPB백필] %s /stats 실패: %s", gid, exc)
            stats["batters"] += await batter_log.store_batting(
                pool, gid_db, "npb", bats, source="boxscore")

            # 등판 기록 — 타순 성패와 무관하게 먼저 적재한다.
            n_app = await record_appearances(
                pool, gid_db, "npb", g["home"], g["away"], pits,
                source="boxscore")
            stats["appearances"] += n_app
            if not lu:
                # 타순만 실패. 등판은 건졌으므로 통계에 남긴다.
                stats["lineup_only_skip"] = stats.get("lineup_only_skip", 0) + 1
                stats["skipped"] += 1
                if n_app:
                    stats["rescued_app"] = stats.get("rescued_app", 0) + n_app
                continue
            stats["games"] += 1
            for side in ("home", "away"):
                team = g[side]
                if per_team.get(team, 0) >= limit_per_team:
                    continue
                starter = next((p["name"] for p in (pits.get(side) or [])
                                if p.get("is_starter") and p.get("name")), None)
                if await record(pool, gid_db, side, team, lu[side],
                                starter=starter, source="boxscore"):
                    stats["rows"] += 1
                    per_team[team] = per_team.get(team, 0) + 1
    stats["teams"] = len(per_team)
    logger.info("[NPB백필] 경기 %d · 적재 %d행 · 등판 %d · 타자 %d · %d팀 "
                "(건너뜀 %d · 경기없음 %d · 타순만실패 %d → 등판 %d건 회수)",
                stats["games"], stats["rows"], stats.get("appearances", 0),
                stats["batters"], stats["teams"], stats["skipped"], stats["no_game"],
                stats.get("lineup_only_skip", 0), stats.get("rescued_app", 0))
    return stats
