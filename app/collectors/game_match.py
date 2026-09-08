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


#: 🔴 [GM-2 2026-09-08] **표 목록을 손으로 적지 않는다.** 종전 결함의 원인이
#   정확히 그것이었다 — 이 모듈은 "새 표를 만들면 이 목록에 반드시 추가한다"고
#   자기 손으로 못박아 놓고(2026-08-27 predictions · 08-31 pick_ledger), 그 뒤
#   만들어진 표 **아홉 중 하나도 추가하지 않았다.** 문장에는 강제력이 없다.
#   `games` 삭제 시 CASCADE 로 함께 지워지는 표를 카탈로그에서 읽는다.
_CASCADE_TABLES = """
SELECT DISTINCT tc.table_name AS t, kcu.column_name AS c
  FROM information_schema.table_constraints tc
  JOIN information_schema.key_column_usage kcu
    ON kcu.constraint_name = tc.constraint_name
  JOIN information_schema.referential_constraints rc
    ON rc.constraint_name = tc.constraint_name
  JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name
 WHERE tc.constraint_type = 'FOREIGN KEY'
   AND ccu.table_name = 'games' AND rc.delete_rule = 'CASCADE'
 ORDER BY 1
"""

#: 유니크 제약의 컬럼들. 이관이 충돌하는지 판단하는 데 쓴다.
#  ⚠️ 부분 인덱스(`WHERE is_final`)도 유니크다 — `pick_ledger` 가 그것이고,
#     그래서 아래 일반 경로는 그 표를 건드리지 않는다(특수 처리가 이미 있다).
_UNIQUE_COLS = """
SELECT i.relname AS idx,
       array_agg(a.attname ORDER BY k.ord) AS cols,
       ix.indpred IS NOT NULL AS partial
  FROM pg_index ix
  JOIN pg_class i ON i.oid = ix.indexrelid
  JOIN pg_class t ON t.oid = ix.indrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = 'public'
  JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
  JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
 WHERE t.relname = $1 AND ix.indisunique AND NOT ix.indisprimary
 GROUP BY 1, 3
"""

#: 이미 **표마다 다른 충돌 정책**으로 손수 처리하는 표. 일반 경로가 건드리지
#  않는다 — 픽은 겹치면 지우고(정보 손실 없음), 레저는 지우지 않고 이력으로
#  강등한다(판정 기록을 지우지 않는 것이 그 표의 존재 이유다).
_HAND_MOVED = ("predictions", "expert_picks", "pick_ledger")


def _q(name: str) -> str:
    """식별자 인용. 이름은 카탈로그에서 왔지만 그대로 문자열에 끼우지 않는다."""
    return '"' + str(name).replace('"', '""') + '"'


async def _move_cascade_rows(pool, keep: int, dups: list[int]) -> dict:
    """CASCADE 표의 행을 keep 으로 옮긴다. 반환 {"moved": n, "dropped": n, ...}.

    🔴 [GM-2] 종전에는 `DELETE FROM games` 의 CASCADE 가 **아홉 개 표를 소리
       없이** 지웠다. 가장 무거운 것은 `pitcher_appearances` — 자료4·9·10·14 의
       원천이라, 그 등판이 **모든 투수의 이력에서 영구히** 사라졌다. 다음 날
       그 투수의 "최근 5등판"은 4등판이 되고 리그 표본도 그만큼 줄었다.
       실측: 병합은 이미 31회 일어났고, 지금도 MLB 중복 그룹이 31개다.

    ⚠️ **못 옮기는 행을 조용히 보내지 않는다.** 유니크 제약이 걸리면 그 행은
       여전히 CASCADE 로 사라지는데, 그때는 수를 세어 로그로 남긴다.
       조용한 삭제를 시끄러운 삭제로 바꾸는 것이 이 함수의 나머지 절반이다.
    """
    out = {"moved": 0, "dropped": 0, "tables": 0}
    try:
        rows = await pool.fetch(_CASCADE_TABLES)
    except Exception as exc:
        logger.warning("[game_match] CASCADE 표 조회 실패 — 이관 생략: %s", exc)
        return out
    for r in rows:
        tbl, col = r["t"], r["c"]
        if tbl in _HAND_MOVED:
            continue
        try:
            uq = await pool.fetch(_UNIQUE_COLS, tbl)
        except Exception as exc:
            logger.warning("[game_match] %s 유니크 조회 실패 — 건너뜀: %s", tbl, exc)
            continue
        # 부분 유니크는 조건을 여기서 재현할 수 없다 — 손수 처리 대상이지
        # 일반 경로의 몫이 아니다. 건드리지 않고 넘긴다.
        if any(u["partial"] for u in uq):
            logger.info("[game_match] %s 부분 유니크 — 일반 이관에서 제외", tbl)
            continue
        # keep 쪽에 같은 키가 이미 있으면 그 행은 옮길 수 없다.
        conds = []
        for u in uq:
            cols = [c for c in u["cols"] if c != col]
            if not cols:                      # game_id 단독 유니크(경기당 1행)
                conds.append("TRUE")
                continue
            conds.append(" AND ".join(
                f"k.{_q(c)} IS NOT DISTINCT FROM s.{_q(c)}" for c in cols))
        where_free = ""
        if conds:
            clash = " OR ".join(f"({c})" for c in conds)
            where_free = (f" AND NOT EXISTS (SELECT 1 FROM {_q(tbl)} k "
                          f"WHERE k.{_q(col)} = $1 AND ({clash}))")
        try:
            moved = await pool.fetchval(
                f"WITH m AS (UPDATE {_q(tbl)} s SET {_q(col)} = $1 "
                f" WHERE s.{_q(col)} = ANY($2::bigint[]){where_free} "
                f" RETURNING 1) SELECT count(*) FROM m", keep, dups) or 0
            left = await pool.fetchval(
                f"SELECT count(*) FROM {_q(tbl)} WHERE {_q(col)} = ANY($1::bigint[])",
                dups) or 0
        except Exception as exc:
            logger.warning("[game_match] %s 이관 실패 — 건너뜀: %s", tbl, exc)
            continue
        out["moved"] += int(moved)
        out["tables"] += 1
        if left:
            out["dropped"] += int(left)
            logger.warning("[game_match] %s — %d행은 유니크 충돌로 옮기지 못했다 "
                           "(CASCADE 로 사라진다) keep=%s", tbl, left, keep)
    return out


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
           "moved_expert_picks": 0, "moved_ledger": 0}
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
        # 🔴 pick_ledger도 옮긴다. 빠뜨리면 DELETE FROM games 의 ON DELETE CASCADE가
        #    판정 기록을 **조용히 지운다** (실측 재현 2026-08-31: 병합 1건에
        #    레저 1행 소멸). 0단계 완료 조건이 "기록·채점 무결손"이므로
        #    이 누락은 조건을 구조적으로 깨뜨린다.
        #    2026-08-27에 predictions를 이관 대상에 넣었을 때 같은 이유였다 —
        #    새 표를 만들면 **이 목록에 반드시 추가한다.**
        #
        # ⚠️ 유니크 인덱스 `idx_pick_ledger_final(game_id, date) WHERE is_final`
        #    때문에 keep 쪽에 같은 날짜의 최종 행이 있으면 이관이 충돌한다.
        #    그때는 **지우지 않고** dup 쪽을 이력(is_final=false)으로 낮춰 보존한다 —
        #    판정 기록을 지우지 않는 것이 이 표의 존재 이유다.
        #    병합 출처는 merged_from에 남겨, 나중에 "이 이력 행이 재판정인지
        #    병합인지"를 되물을 수 있게 한다.
        await pool.execute(
            """UPDATE pick_ledger SET is_final = FALSE, merged_from = game_id
                WHERE game_id = ANY($2::int[]) AND is_final
                  AND EXISTS (SELECT 1 FROM pick_ledger k
                               WHERE k.game_id = $1 AND k.date = pick_ledger.date
                                 AND k.is_final)""", keep, dups)
        out["moved_ledger"] = out.get("moved_ledger", 0) + int(await pool.fetchval(
            "WITH m AS (UPDATE pick_ledger SET game_id = $1, "
            "  merged_from = COALESCE(merged_from, game_id) "
            "WHERE game_id = ANY($2::int[]) RETURNING 1) SELECT count(*) FROM m",
            keep, dups) or 0)
        # 🔴 [GM-2 2026-09-08] **나머지 CASCADE 표를 여기서 옮긴다.**
        #    위 세 표는 표마다 충돌 정책이 달라 손수 처리하고, 그 밖의 표는
        #    카탈로그에서 읽어 일반 규칙으로 옮긴다. 이 줄이 없던 동안
        #    아홉 개 표가 아래 DELETE 로 소리 없이 사라졌다.
        #    ⚠️ **DELETE 앞이어야 한다** — 순서를 바꾸면 옮길 행이 이미 없다.
        _c = await _move_cascade_rows(pool, keep, dups)
        for k in ("moved", "dropped", "tables"):
            out[f"cascade_{k}"] = out.get(f"cascade_{k}", 0) + _c[k]
        await pool.execute("DELETE FROM games WHERE id = ANY($1::int[])", dups)
        out["merged"] += len(dups)
    if out["merged"]:
        logger.info("[game_match] 중복 경기 %d행 병합 — 예측 %d건 · 레저 %d건 · "
                    "기타 CASCADE %d행/%d표 이관 (충돌로 못 옮긴 행 %d)",
                    out["merged"], out["moved_predictions"], out["moved_ledger"],
                    out.get("cascade_moved", 0), out.get("cascade_tables", 0),
                    out.get("cascade_dropped", 0))
    return out
