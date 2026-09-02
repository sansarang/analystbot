"""[무과금 전환 1d] 무료 배당 3원 체계의 **단일 진입점**.

  espn    ESPN Core API (MLB)          1순위 · 무인증 · 무제한
  sharp   SharpAPI 무료 티어 (MLB)      2순위 · 교차검증 겸 폴백 · 키 필요
  betman  배트맨 프로토 (KBO·NPB·MLB)   아시아 · Go 크롤러가 수집

🔴 **가치 게이트는 소스를 구분하지 않는다.** 같은 `odds_snapshots` 스키마에
   `provider` 만 달리해 적재하고, 아래 계층은 종전 로직 그대로다.

🔴 **배당은 판정 입력에 흐르지 않는다.** 이 모듈도 판정 경로에서 import 되지
   않는다 — import 경계 테스트가 강제한다.

⚠️ The Odds API 는 **지우지 않았다.** `app/collectors/odds.py` 그대로 두고
   `ODDS_PROVIDER` env 로 껐다. 유료 복귀가 필요하면 값만 바꾸면 된다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 무료 소스 우선순위. 앞에서 배당을 얻으면 뒤는 부르지 않는다(교차검증 제외).
MLB_CHAIN = ("espn", "sharp")
ASIA_PROVIDER = "oddsportal"


async def _match_game_ids(pool, sport: str, date: str) -> dict[str, int]:
    """(home, away) 팀명 → games.id. 없는 경기는 건너뛴다 — 만들지 않는다."""
    from datetime import date as _d

    tz = "America/New_York" if sport == "mlb" else "Asia/Seoul"
    rows = await pool.fetch(
        f"""SELECT id, home, away FROM games
             WHERE sport = $1
               AND (starts_at AT TIME ZONE '{tz}')::date = $2""",
        sport, _d.fromisoformat(date))
    return {f"{r['home']}|{r['away']}": r["id"] for r in rows}


async def store_rows(pool, game_id: int, rows: list[dict], provider: str) -> int:
    """행 목록을 `odds_snapshots` 에 적재. 반환 적재 건수."""
    n = 0
    for r in rows:
        try:
            await pool.execute(
                """INSERT INTO odds_snapshots
                       (game_id, book, market, side, line, odds, provider)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                game_id, r["book"], r["market"], r["side"],
                r.get("line"), r["odds"], provider)
            n += 1
        except Exception as exc:
            logger.warning("[odds_free] 적재 실패 game=%s %s: %s",
                           game_id, r.get("side"), exc)
    return n


async def upcoming_mlb_dates(pool, hours: int = 36) -> list[str]:
    """**DB에 실제로 있는** 다가올 MLB 경기의 ET 슬레이트 날짜들.

    🔴 실사고 2026-09-02 14:42: `mlb_slate_date()` 로 날짜를 계산해 수집했더니
       ESPN 은 14경기 배당을 정상으로 줬는데 **매칭 0** 이었다. 그 슬레이트가
       `games` 에 아직 없었기 때문이다 — MLB 스케줄은 새벽 프리페치가 넣는데
       ET 자정이 지나면 `mlb_slate_date()` 는 이미 다음 슬레이트를 가리킨다.
       그 사이 몇 시간 동안 "배당을 못 붙였다"가 아니라 **"붙일 경기가
       없었다"** 였고, 워치독은 그걸 소스 고장으로 읽었다.

    날짜를 계산하지 않는다. **DB 에 있는 경기에서 역으로 읽는다.**
    """
    from datetime import timedelta

    rows = await pool.fetch(
        """SELECT DISTINCT (starts_at AT TIME ZONE 'America/New_York')::date AS d
             FROM games
            WHERE sport = 'mlb' AND status = 'scheduled'
              AND starts_at > now() - interval '2 hours'
              AND starts_at < now() + make_interval(hours => $1)
            ORDER BY 1""", hours)
    return [r["d"].isoformat() for r in rows]


async def collect_mlb(pool, date: str) -> dict:
    """MLB 배당 수집 — ESPN 먼저, 실패·빈손이면 SharpAPI.

    반환 {provider, games, rows, matched, unmatched[], no_games}
    ⚠️ `no_games=True` 는 **소스 실패가 아니다** — 붙일 경기가 DB에 없다는 뜻이다.
    """
    from app.collectors.espn_odds import fetch_slate

    out = {"provider": None, "games": 0, "rows": 0, "matched": 0,
           "unmatched": [], "no_games": False}
    index = await _match_game_ids(pool, "mlb", date)
    if not index:
        # 붙일 경기가 없다. 소스를 때릴 이유도 없다 — 헛호출을 아낀다.
        out["no_games"] = True
        logger.info("[odds_free] MLB %s — games 에 그 슬레이트가 없다 "
                    "(아직 적재 전). 배당 수집 생략", date)
        return out
    for provider in MLB_CHAIN:
        try:
            if provider == "espn":
                slate = await fetch_slate(date, "mlb")
            else:
                from app.collectors.sharp_odds import fetch_slate as sharp_slate

                slate = await sharp_slate(date)
        except Exception as exc:
            logger.warning("[odds_free] %s 수집 실패 — 다음 소스로: %s", provider, exc)
            continue
        if not slate:
            logger.info("[odds_free] %s 배당 0건 — 다음 소스로", provider)
            continue
        rows_n = matched = 0
        for blk in slate.values():
            gid = index.get(f"{blk['home']}|{blk['away']}")
            if gid is None:
                out["unmatched"].append(f"{blk['away']}@{blk['home']}")
                continue
            matched += 1
            rows_n += await store_rows(pool, gid, blk["rows"], provider)
        out.update(provider=provider, games=len(slate), rows=rows_n,
                   matched=matched)
        logger.info("[odds_free] MLB %s — provider=%s 경기 %d · 매칭 %d · 행 %d"
                    "%s", date, provider, len(slate), matched, rows_n,
                    f" · 미매칭 {len(out['unmatched'])}" if out["unmatched"] else "")
        if rows_n:
            return out
    logger.warning("[odds_free] MLB %s — 무료 소스 전부 실패 "
                   "(대상 경기 %d건은 DB에 있다)", date, len(index))
    return out


async def collect_asia(pool, redis, sport: str, date: str) -> dict:
    """KBO·NPB 배당 — oddsportal 크롤(리그당 1요청).

    🔴 배트맨은 못 썼다. `requestClient.js` 가 광고하는 엔드포인트 10개가 전부
       "페이지 오류 안내 — 삭제 또는 이름이 변경" 을 돌려준다(6회 시도 후 중단).
       후보 5곳을 실측해 oddsportal 을 골랐다 — `oddsportal.py` 상단 표 참조.
    ⚠️ 리그당 **1요청**이다. 상대 서버를 두들기지 않는다.
    """
    from app.collectors.oddsportal import PROVIDER as OP, fetch_league

    out = {"provider": OP, "games": 0, "rows": 0, "matched": 0, "unmatched": []}
    index = await _match_game_ids(pool, sport, date)
    if not index:
        out["no_games"] = True
        logger.info("[odds_free] %s %s — games 에 그 슬레이트가 없다. 수집 생략",
                    sport.upper(), date)
        return out
    slate = await fetch_league(sport)
    out["games"] = len(slate)
    for blk in slate.values():
        gid = index.get(f"{blk['home']}|{blk['away']}")
        if gid is None:
            out["unmatched"].append(f"{blk['away']}@{blk['home']}")
            continue
        out["matched"] += 1
        out["rows"] += await store_rows(pool, gid, blk["rows"], OP)
    logger.info("[odds_free] %s %s — provider=%s 경기 %d · 매칭 %d · 행 %d%s",
                sport.upper(), date, OP, out["games"], out["matched"],
                out["rows"],
                f" · 미매칭 {out['unmatched']}" if out["unmatched"] else "")
    return out


async def coverage(pool, sport: str, date: str) -> dict:
    """[검증 3] 커버리지 — 그 슬레이트 경기 중 배당이 붙은 비율."""
    from datetime import date as _d

    tz = "America/New_York" if sport == "mlb" else "Asia/Seoul"
    row = await pool.fetchrow(
        f"""SELECT count(*) AS total,
                   count(*) FILTER (WHERE EXISTS (
                       SELECT 1 FROM odds_snapshots o
                        WHERE o.game_id = g.id
                          AND o.captured_at > now() - interval '12 hours')) AS with_odds
              FROM games g
             WHERE g.sport = $1
               AND (g.starts_at AT TIME ZONE '{tz}')::date = $2""",
        sport, _d.fromisoformat(date))
    total = (row or {}).get("total") or 0
    got = (row or {}).get("with_odds") or 0
    return {"sport": sport, "date": date, "total": total, "with_odds": got,
            "rate": (got / total) if total else None}
