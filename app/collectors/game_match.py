"""[§8-37] 결과를 **예측이 붙어 있는 경기 행**에 붙인다.

실사고(2026-08-27) — 채점이 통째로 막혀 있던 진짜 이유:
  `games`는 `ON CONFLICT (sport, ext_id)`로 중복을 막는데, **같은 경기가 소스마다
  다른 ext_id를 받는다.**
      id=668  ext_id=odds:36cb8879...        scheduled   ← 예측이 여기 붙는다
      id=770  ext_id=kbo:2026-08-26:롯데:KIA  final 11-16 ← 결과가 여기 들어온다
  두 행이 같은 경기인데 DB는 남남으로 본다. 채점기는 `status='final'`인 행에서
  픽을 찾으므로 **예측이 붙은 행은 영원히 미채점**으로 남는다.
  실측 중복: KBO 5 · MLB 10 · NPB 6 (축구는 단일 소스라 0).

→ 결과 적재는 ext_id가 아니라 **경기 자체**(종목·홈·원정·시각)로 찾아 갱신한다.

⚠️ 날짜가 아니라 **시각 근접**으로 찾는다. UTC 날짜로 맞추면 MLB 야간경기가
   다음 날로 넘어가 못 찾는다(19:00 ET = 23:00 UTC, 서머타임에 따라 02:00 UTC).
⚠️ 못 찾으면 **새로 넣는다.** 예측이 없던 경기도 결과는 쌓여야 채점 표본이 된다.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 같은 경기로 볼 시각 허용 폭. 순연·시각 정정을 흡수하되 연전 다음 경기와는
# 겹치지 않는 크기다(하루 1경기 종목 기준).
MATCH_WINDOW_HOURS = 20

# ⚠️ `$4::timestamptz` 캐스트가 **필수**다. 없으면 PostgreSQL이
#    `$4 - make_interval(...)`에서 $4의 타입을 interval로 추론해
#    "operator does not exist: timestamp with time zone >= interval"로 죽는다.
#    그러면 공식 소스 적재가 조용히 폴백 경로로 새어 나간다(실측 2026-08-27).
_FIND = """
    SELECT id FROM games
    WHERE sport = $1 AND home = $2 AND away = $3
      AND starts_at BETWEEN $4::timestamptz - make_interval(hours => $5)
                        AND $4::timestamptz + make_interval(hours => $5)
    ORDER BY abs(extract(epoch FROM (starts_at - $4::timestamptz)))
    LIMIT 1
"""

_UPDATE = """
    UPDATE games SET status = $2,
                     home_score = COALESCE($3, home_score),
                     away_score = COALESCE($4, away_score),
                     updated_at = now()
    WHERE id = $1
"""

_INSERT = """
    INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                       status, home_score, away_score)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (sport, ext_id) DO UPDATE SET
        status = EXCLUDED.status,
        home_score = COALESCE(EXCLUDED.home_score, games.home_score),
        away_score = COALESCE(EXCLUDED.away_score, games.away_score),
        updated_at = now()
"""


async def apply_result(pool, *, sport: str, league: str, ext_id: str,
                       starts_at: datetime, home: str, away: str, status: str,
                       home_score, away_score) -> str:
    """결과를 반영한다. 반환: "updated"(기존 경기 갱신) | "inserted"(신규).

    기존 행을 찾으면 **그 행을 갱신**한다 — 그래야 그 행에 붙은 예측이 채점된다.
    """
    gid = await pool.fetchval(_FIND, sport, home, away, starts_at, MATCH_WINDOW_HOURS)
    if gid is not None:
        await pool.execute(_UPDATE, gid, status, home_score, away_score)
        return "updated"
    await pool.execute(_INSERT, sport, league, ext_id, starts_at, home, away,
                       status, home_score, away_score)
    return "inserted"


async def merge_duplicate_games(pool, sport: str | None = None) -> dict:
    """이미 갈라진 중복 행을 합친다. 반환: {"merged", "moved_predictions", ...}.

    유지할 행(**예측이 붙은 쪽**)에 점수를 옮기고, 나머지 행의 참조를 넘긴 뒤
    지운다. 예측이 없으면 더 오래된(먼저 만들어진) 행을 남긴다.

    ⚠️ 예측·전문가픽의 `game_id`를 먼저 옮긴 뒤에 지운다 — 순서를 바꾸면
       외래키가 깨지거나 예측이 조용히 사라진다.
    """
    where = "WHERE sport = $1" if sport else ""
    args = [sport] if sport else []
    groups = await pool.fetch(
        f"""
        SELECT sport, home, away,
               date_trunc('day', starts_at AT TIME ZONE 'UTC') AS d,
               array_agg(id ORDER BY id) AS ids
        FROM games {where}
        GROUP BY 1, 2, 3, 4
        HAVING count(*) > 1
        """, *args)
    out = {"groups": len(groups), "merged": 0, "moved_predictions": 0,
           "moved_expert_picks": 0}
    for g in groups:
        ids = list(g["ids"])
        # 예측이 붙은 행을 남긴다 — 그것이 우리가 판정한 경기다
        keep = await pool.fetchval(
            "SELECT game_id FROM predictions WHERE game_id = ANY($1::int[]) "
            "GROUP BY game_id ORDER BY count(*) DESC LIMIT 1", ids) or ids[0]
        dups = [i for i in ids if i != keep]
        if not dups:
            continue
        # 점수·상태를 살린다 (final 쪽 값이 있으면 그것으로)
        best = await pool.fetchrow(
            "SELECT status, home_score, away_score FROM games "
            "WHERE id = ANY($1::int[]) AND home_score IS NOT NULL "
            "ORDER BY (status = 'final') DESC LIMIT 1", ids)
        if best:
            await pool.execute(_UPDATE, keep, best["status"],
                               best["home_score"], best["away_score"])
        out["moved_predictions"] += int(await pool.fetchval(
            "WITH m AS (UPDATE predictions SET game_id = $1 "
            "WHERE game_id = ANY($2::int[]) RETURNING 1) SELECT count(*) FROM m",
            keep, dups) or 0)
        # ⚠️ expert_picks에는 유니크 인덱스 `uq_expert_picks(game_id, expert,
        #    site, pick)`가 있다. 같은 픽이 양쪽 행에 있으면 이관이 충돌해
        #    **병합 전체가 예외로 죽는다**(실측 2026-08-27). 겹치는 쪽을 먼저
        #    지우고 나머지만 옮긴다 — 어차피 같은 픽이라 정보 손실이 없다.
        out["dropped_dup_picks"] = out.get("dropped_dup_picks", 0) + int(
            await pool.fetchval(
                "WITH d AS (DELETE FROM expert_picks e "
                " WHERE e.game_id = ANY($2::int[]) AND EXISTS ("
                "   SELECT 1 FROM expert_picks k WHERE k.game_id = $1"
                "     AND k.expert IS NOT DISTINCT FROM e.expert"
                "     AND k.site IS NOT DISTINCT FROM e.site"
                "     AND k.pick IS NOT DISTINCT FROM e.pick)"
                " RETURNING 1) SELECT count(*) FROM d", keep, dups) or 0)
        out["moved_expert_picks"] += int(await pool.fetchval(
            "WITH m AS (UPDATE expert_picks SET game_id = $1 "
            "WHERE game_id = ANY($2::int[]) RETURNING 1) SELECT count(*) FROM m",
            keep, dups) or 0)
        await pool.execute("DELETE FROM games WHERE id = ANY($1::int[])", dups)
        out["merged"] += len(dups)
    if out["merged"]:
        logger.info("[game_match] 중복 경기 %d행 병합 — 예측 %d건 이관",
                    out["merged"], out["moved_predictions"])
    return out
