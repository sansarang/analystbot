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

# 🔴 **사본을 두지 않는다.** 어느 소스가 어느 리그를 맡는지는
#    `app.registry` 가 원본이다. 여기서 다시 적으면 워치독과 어긋난다.


def _chain(sport: str):
    """그 종목을 담당하는 **활성** 소스들, 레지스트리 순서대로."""
    from app.registry import active_providers

    return [p.name for p in active_providers() if sport in p.sports]


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


#: 🔴 [SNAP-1 2026-09-15] 첫 스냅샷에 이름표를 붙인다.
#   ⚠️ **트리거가 붙인 태그를 덮지 않는다** — `snap_tag IS NULL` 인 행만,
#      그리고 그 (경기·provider) 에 open 계열이 **아직 없을 때만** 붙인다.
#      `pre`·`lineup` 이 `open_proxy` 로 바뀌면 이동 기준선이 뒤집힌다.
#   ⚠️ 멱등이다 — 두 번 돌려도 같은 결과다(계약이 단언한다).
_TAG_OPEN_SQL = """
    WITH first_seen AS (
        SELECT id FROM odds_snapshots
         WHERE game_id = $1 AND provider = $2 AND snap_tag IS NULL
           AND captured_at = (SELECT min(captured_at) FROM odds_snapshots
                               WHERE game_id = $1 AND provider = $2)
    )
    UPDATE odds_snapshots SET snap_tag = $3
     WHERE id IN (SELECT id FROM first_seen)
       AND NOT EXISTS (SELECT 1 FROM odds_snapshots
                        WHERE game_id = $1 AND provider = $2
                          AND snap_tag IN ('open', 'open_proxy'))
"""


async def tag_open(pool, game_id: int, provider: str) -> str | None:
    """이 경기·소스의 **가장 이른** 스냅샷에 `open`/`open_proxy` 를 붙인다.

    반환: 붙인 이름표(이미 있으면 None).
    🔴 `open` 의 정의(T-24h)는 `triggers.KINDS` 가 원본이다 — 숫자를 베끼지 않는다.
    """
    from app.engine.odds_move import open_tag

    row = await pool.fetchrow(
        """SELECT g.starts_at ko,
                  (SELECT min(captured_at) FROM odds_snapshots
                    WHERE game_id = $1 AND provider = $2) first_seen,
                  (SELECT count(*) FROM odds_snapshots
                    WHERE game_id = $1 AND provider = $2
                      AND snap_tag IN ('open', 'open_proxy')) already
             FROM games g WHERE g.id = $1""", game_id, provider)
    if not row or row["first_seen"] is None or row["already"]:
        return None
    tag = open_tag(row["ko"], row["first_seen"])
    await pool.execute(_TAG_OPEN_SQL, game_id, provider, tag)
    logger.info("[odds_free] snap_tag game=%s provider=%s → %s "
                "(첫값 %s · 킥오프 %s)", game_id, provider, tag,
                row["first_seen"], row["ko"])
    return tag


async def backfill_open_tags(pool, *, since_days: int = 400) -> dict:
    """[SNAP-1] 기존 행에 소급으로 `open`/`open_proxy` 를 붙인다.

    🔴 **한 번만 의미가 있고 멱등이다.** 이미 open 계열이 있는 (경기·소스) 는
       건드리지 않고, 트리거가 붙인 `pre`·`lineup` 등도 그대로 둔다.
    ⚠️ 규칙은 사용자 지시 그대로: 킥오프 T-24h 이전 첫 값 = `open`,
       그 이후 첫 값 = `open_proxy`.
    """
    pairs = await pool.fetch(
        """SELECT o.game_id, o.provider
             FROM odds_snapshots o JOIN games g ON g.id = o.game_id
            WHERE g.starts_at > now() - ($1 || ' days')::interval
            GROUP BY 1, 2
           HAVING count(*) FILTER (
                    WHERE o.snap_tag IN ('open', 'open_proxy')) = 0""",
        str(int(since_days)))
    out = {"pairs": len(pairs), "open": 0, "open_proxy": 0, "skip": 0}
    for r in pairs:
        tag = await tag_open(pool, r["game_id"], r["provider"])
        if tag is None:
            out["skip"] += 1
        else:
            out[tag] += 1
    logger.info("[odds_free] snap_tag 소급 — 대상 %d쌍 · open %d · open_proxy %d "
                "· 생략 %d", out["pairs"], out["open"], out["open_proxy"],
                out["skip"])
    return out


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
    # 🔴 [SNAP-1] 넣었으면 첫 값에 이름표를 붙인다. 실패해도 적재는 산다 —
    #    이름표는 분석용이고 값이 본체다.
    if n:
        try:
            await tag_open(pool, game_id, provider)
        except Exception as exc:
            logger.warning("[odds_free] snap_tag 실패 game=%s: %s", game_id, exc)
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
    for provider in _chain("mlb"):
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
    # ⚠️ [2026-09-03] **끝난 슬레이트는 실패가 아니다.** 경기가 시작되면
    #    ESPN 은 그 경기를 배당 목록에서 내린다. 대상이 없어진 것을 "전부
    #    실패"로 30분마다 WARNING 하면, 진짜 소스 고장이 그 속에 묻힌다.
    upcoming = 0
    try:
        upcoming = await pool.fetchval(
            """SELECT count(*) FROM games
                WHERE id = ANY($1::bigint[]) AND starts_at > now()""",
            list(index.values())) or 0
    except Exception as exc:
        logger.debug("[odds_free] 미시작 경기 조회 실패: %s", exc)
        upcoming = -1                      # 모르면 종전대로 경고한다
    if upcoming == 0:
        logger.info("[odds_free] MLB %s — 슬레이트 %d경기가 전부 시작·종료됐다. "
                    "배당 소스가 더는 싣지 않는다 (고장 아님)", date, len(index))
    else:
        logger.warning("[odds_free] MLB %s — 무료 소스 전부 실패 "
                       "(대상 경기 %d건 중 미시작 %s건)", date, len(index),
                       upcoming if upcoming >= 0 else "?")
    return out


async def collect_asia(pool, redis, sport: str, date: str) -> dict:
    """KBO·NPB 배당 — oddsportal 크롤(리그당 1요청).

    🔴 배트맨은 못 썼다. `requestClient.js` 가 광고하는 엔드포인트 10개가 전부
       "페이지 오류 안내 — 삭제 또는 이름이 변경" 을 돌려준다(6회 시도 후 중단).
       후보 5곳을 실측해 oddsportal 을 골랐다 — `oddsportal.py` 상단 표 참조.
    ⚠️ 리그당 **1요청**이다. 상대 서버를 두들기지 않는다.
    """
    from app.collectors.oddsportal import PROVIDER as OP, fetch_league

    if OP not in _chain(sport):
        logger.info("[odds_free] %s — %s 가 활성 소스가 아니다. 생략",
                    sport.upper(), OP)
        return {"provider": None, "games": 0, "rows": 0, "matched": 0,
                "unmatched": [], "no_games": False}
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


async def collect_soccer(pool, redis, date: str) -> dict:
    """[ODP-1] 축구 1X2 배당 — oddsportal, **리그당 1요청**.

    🔴 팀명은 **결정적 정규화 + 명시 별칭**으로만 맞춘다. 유사도(퍼지)를 쓰지
       않는다 — AC밀란이 인테르로 붙은 사고가 그것 때문이었다.
    🔴 **양쪽 키가 다 맞아야** 붙인다. 한쪽만 맞으면 버린다(미매칭으로 남긴다).
    ⚠️ 실패해도 다른 리그를 막지 않는다.
    """
    from app.collectors.oddsportal import (
        PROVIDER as OP, SOCCER_URL, fetch_soccer_league, team_key,
    )

    out = {"provider": OP, "games": 0, "rows": 0, "matched": 0,
           "unmatched": [], "no_games": False}
    if OP not in _chain("soccer"):
        logger.info("[odds_free] SOCCER — %s 가 활성 소스가 아니다. 생략", OP)
        out["provider"] = None
        return out
    idx = await _match_soccer_ids(pool, date)
    if not idx:
        out["no_games"] = True
        logger.info("[odds_free] SOCCER %s — games 에 그 슬레이트가 없다", date)
        return out
    for league in SOCCER_URL:
        try:
            slate = await fetch_soccer_league(league)
        except Exception as exc:
            logger.warning("[odds_free] SOCCER %s 수집 실패: %s", league, exc)
            continue
        out["games"] += len(slate)
        for blk in slate:
            gid = idx.get((blk["key_home"], blk["key_away"]))
            if gid is None:
                out["unmatched"].append(
                    f"{blk['away_raw']}@{blk['home_raw']}({league})")
                continue
            # 🔴 저장은 **우리 표기**로 한다 — 디빅이 games 팀명으로 찾는다.
            names = idx_names.get((blk["key_home"], blk["key_away"]), {})
            rows = []
            for r in blk["rows"]:
                side = r["side"]
                # 🔴 [ACL-2 2026-09-15] **키를 만든 것과 같은 함수로 비교한다.**
                #    `key_home`/`key_away` 는 `team_key()`(국가 접미사 제거 +
                #    별칭)로 만들어 놓고 여기서만 `norm()` 으로 비교했다.
                #    ACL-1 이 접미사 제거를 넣은 순간 둘이 갈라졌고,
                #    홈·원정 줄이 오즈포털 원표기로 저장돼 **Draw 만** 우리
                #    팀명과 맞았다(실측 2026-09-15: 4경기 전부 None/4.8/None).
                if team_key(side) == blk["key_home"]:
                    side = names.get("home", side)
                elif team_key(side) == blk["key_away"]:
                    side = names.get("away", side)
                rows.append({**r, "side": side})
            out["matched"] += 1
            out["rows"] += await store_rows(pool, gid, rows, OP)
    logger.info("[odds_free] SOCCER %s — 경기 %d · 매칭 %d · 행 %d%s",
                date, out["games"], out["matched"], out["rows"],
                f" · 미매칭 {out['unmatched'][:6]}" if out["unmatched"] else "")
    return out


#: `collect_soccer` 가 이름 환원에 쓰는 표. `_match_soccer_ids` 가 채운다.
idx_names: dict[tuple[str, str], dict] = {}


async def _match_soccer_ids(pool, date: str) -> dict[tuple[str, str], int]:
    """(정규화 홈키, 정규화 원정키) → games.id. 없는 경기는 만들지 않는다.

    🔴 [ODP-2] `$1::date` 에는 **`datetime.date` 를 넘긴다.** 문자열을 주면
       asyncpg 가 bind 에서 `DataError: 'str' object has no attribute
       'toordinal'` 로 터지고, 호출부가 그것을 삼켜 축구 배당이 조용히
       0건이 된다(실측 2026-09-13~14, 12시간 0건). 같은 파일 `coverage` 와
       같은 형태다.
    """
    from datetime import date as _d

    from app.collectors.oddsportal import norm

    rows = await pool.fetch(
        """SELECT id, home, away FROM games
            WHERE sport = 'soccer'
              AND (starts_at AT TIME ZONE 'Asia/Seoul')::date
                  BETWEEN $1::date - 1 AND $1::date + 1""",
        _d.fromisoformat(date))
    out: dict[tuple[str, str], int] = {}
    idx_names.clear()
    for r in rows:
        k = (norm(r["home"]), norm(r["away"]))
        out[k] = r["id"]
        idx_names[k] = {"home": r["home"], "away": r["away"]}
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
