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

# 같은 경기로 볼 시각 허용 폭. 순연·시각 정정을 흡수한다.
# 🔴 [GM-4] **연전이면 이 창만으로는 못 가른다** — 실측 2026-09-13: 같은 대진이
#   19.5h 간격으로 이틀 연속 열려 창 안에 들어왔다. 그래서 `_FIND` 가 ext_id
#   접두사로 한 겹 더 가른다. 창 자체는 좁히지 않는다(순연·시각정정을 놓친다).
MATCH_WINDOW_HOURS = 20

#: 🔴 [GM-3 2026-09-08] **병합 전용 창.** `MATCH_WINDOW_HOURS`(20h)와 목적이
#   다르다 — 저것은 "이 결과를 어느 경기에 붙일까"이고 이것은 "이 두 행이 같은
#   경기인가"다. 20h 로 병합하면 3연전의 야간→주간 경기(18h 차)가 합쳐진다.
#   실측 2026-09-08 (MLB 2026 정규시즌 263쌍의 간격):
#     0~0.5h 3건 · **0.5~4h 0건** · 4~6h 11건 · 6~9h 8건 · 9~24h 241건
#   빈 띠 한가운데인 2시간을 쓴다. 좁히면 진짜 중복이 안 합쳐져 예측이 붙은
#   행이 미채점으로 남고(실사고 2026-08-27), 넓히면 다른 경기를 지운다.
MERGE_WINDOW_HOURS = 2

# ⚠️ `$4::timestamptz` 캐스트가 **필수**다. 없으면 PostgreSQL이
#    `$4 - make_interval(...)`에서 $4의 타입을 interval로 추론해
#    "operator does not exist: timestamp with time zone >= interval"로 죽는다.
#    그러면 공식 소스 적재가 조용히 폴백 경로로 새어 나간다(실측 2026-08-27).
#: 🔴 [GM-4 2026-09-13] **같은 소스의 다른 id 는 다른 경기다.**
#   실사고: 오늘 `yahoo:2021039419`(13:30) 가 어제 `yahoo:2021039414`(18:00)
#   행을 갱신했고, 봇이 **어제 경기를 판정**했다. 두 경기 간격 19.5h 로
#   `MATCH_WINDOW_HOURS`(20h) 안이었다 — 연전이면 창만으로는 못 가른다.
#   ⚠️ **소스가 다른 병합은 그대로 둔다.** 그것이 이 모듈의 존재 이유다
#      (실사고 2026-08-27: `odds:…` 행과 `kbo:…` 행이 남남이라 채점이 막혔다).
#      가르는 기준은 `ext_id` 의 접두사다 — 같으면 다른 경기, 다르면 병합.
_FIND = """
    SELECT id FROM games
    WHERE sport = $1 AND home = $2 AND away = $3
      AND starts_at BETWEEN $4::timestamptz - make_interval(hours => $5)
                        AND $4::timestamptz + make_interval(hours => $5)
      AND NOT (ext_id IS DISTINCT FROM $6
               AND split_part(ext_id, ':', 1) = split_part($6::text, ':', 1))
    ORDER BY abs(extract(epoch FROM (starts_at - $4::timestamptz)))
    LIMIT 1
"""

_UPDATE = """
    UPDATE games SET status = $2,
                     home_score = COALESCE($3, home_score),
                     away_score = COALESCE($4, away_score),
                     -- 🔴 [W3-2] 종료 근거. 덮어쓰지 않는다 — 한 번 AET 로
                     --    기록된 경기가 나중 목록에서 지워지면 안 된다.
                     result_basis = COALESCE($5, result_basis),
                     updated_at = now()
    WHERE id = $1
"""

_INSERT = """
    INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                       status, home_score, away_score, result_basis)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    ON CONFLICT (sport, ext_id) DO UPDATE SET
        status = EXCLUDED.status,
        home_score = COALESCE(EXCLUDED.home_score, games.home_score),
        away_score = COALESCE(EXCLUDED.away_score, games.away_score),
        result_basis = COALESCE(EXCLUDED.result_basis, games.result_basis),
        updated_at = now()
"""


async def apply_result(pool, *, sport: str, league: str, ext_id: str,
                       starts_at: datetime, home: str, away: str, status: str,
                       home_score, away_score, result_basis=None) -> str:
    """결과를 반영한다. 반환: "updated"(기존 경기 갱신) | "inserted"(신규).

    기존 행을 찾으면 **그 행을 갱신**한다 — 그래야 그 행에 붙은 예측이 채점된다.
    """
    gid = await pool.fetchval(_FIND, sport, home, away, starts_at,
                              MATCH_WINDOW_HOURS, ext_id)
    if gid is not None:
        await pool.execute(_UPDATE, gid, status, home_score, away_score,
                           result_basis)
        return "updated"
    await pool.execute(_INSERT, sport, league, ext_id, starts_at, home, away,
                       status, home_score, away_score, result_basis)
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
       실측: 병합은 이미 31회 일어났다.
       🔴 [정정 2026-09-09] 종전 주석은 "지금도 MLB 중복 그룹이 31개다"라고
          적었는데, 운영에서 다시 재니 **0개**다(옛 UTC-날짜 정의로도 0).
          31 은 GM-3 이 창을 고치기 전의 수이고 그 뒤 상황이 바뀌었다 —
          손으로 적어 둔 수는 원본이 바뀔 때 따라오지 않는다.
          지금 수를 보려면 `duplicate_group_count(pool, "mlb")` 를 부른다.

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
        # 🔴 [GM-4 2026-09-09] **dup 을 한 개씩 옮긴다.**
        #    종전에는 `ANY($2)` 로 전부 한 UPDATE 에 넣었다. 충돌 검사는
        #    `keep` 쪽만 보므로, **dup 끼리 같은 키를 갖고 keep 에는 없으면**
        #    둘 다 검사를 통과해 같은 문장 안에서 유니크 제약을 깼다.
        #    그러면 예외 → `continue` → **그 표를 통째로 건너뛴다** —
        #    충돌하지 않는 행까지 CASCADE 로 사라지고 `dropped` 는 0으로 남아
        #    요약이 손실을 축소 보고했다.
        #    실측 재현(로컬 DB, 합성 경기 3행): moved 0 · dropped 0 · 실손실 2행.
        #    한 개씩 돌리면 앞 dup 이 옮긴 행이 이미 keep 에 있으므로 다음
        #    dup 은 **이미 있는 시끄러운 손실 경로**로 들어간다.
        failed = False
        for one in dups:
            try:
                moved = await pool.fetchval(
                    f"WITH m AS (UPDATE {_q(tbl)} s SET {_q(col)} = $1 "
                    f" WHERE s.{_q(col)} = $2{where_free} "
                    f" RETURNING 1) SELECT count(*) FROM m", keep, one) or 0
            except Exception as exc:
                logger.warning("[game_match] %s game=%s 이관 실패: %s", tbl, one, exc)
                failed = True
                continue
            out["moved"] += int(moved)
        try:
            left = await pool.fetchval(
                f"SELECT count(*) FROM {_q(tbl)} WHERE {_q(col)} = ANY($1::bigint[])",
                dups) or 0
        except Exception as exc:
            logger.warning("[game_match] %s 잔여 계수 실패: %s", tbl, exc)
            continue
        if failed and not left:
            continue
        out["tables"] += 1
        if left:
            out["dropped"] += int(left)
            logger.warning("[game_match] %s — %d행은 유니크 충돌로 옮기지 못했다 "
                           "(CASCADE 로 사라진다) keep=%s", tbl, left, keep)
    return out


#: 🔴 [ELO-2 2026-09-09] **중복 그룹의 정의는 여기 하나뿐이다.**
#   종전에는 `backfill._DUP_GROUPS` 에 같은 뜻의 쿼리가 하나 더 있었고,
#   GM-3 이 창을 UTC 날짜 → ±2시간으로 바꿀 때 **그쪽은 따라오지 않았다.**
#   그래서 백필의 가드가 병합이 하지도 않을 일을 경고한다. 이 저장소가
#   네 번 데인 병이다(2026-09-02 워치독 오탐 4건) — 사본은 원본을 못 따라간다.
_GROUP_SQL = """
    SELECT g.id, g.sport, g.home, g.away,
           (SELECT min(g2.id) FROM games g2
             WHERE g2.sport = g.sport AND g2.home = g.home
               AND g2.away = g.away
               AND abs(extract(epoch FROM (g2.starts_at - g.starts_at)))
                   <= {win} * 3600) AS cid
      FROM games g {where}
"""


def _group_sql(where: str) -> str:
    return _GROUP_SQL.format(win=MERGE_WINDOW_HOURS, where=where)


async def duplicate_group_count(pool, sport: str | None = None) -> int:
    """지금 병합 대상이 되는 중복 그룹 수. **병합과 같은 정의를 쓴다.**

    적재 전후로 이 수를 재면 "내가 넣은 것이 다음 병합을 부르는가"를 알 수 있다.
    """
    where = "WHERE sport = $1" if sport else ""
    args = [sport] if sport else []
    try:
        return int(await pool.fetchval(
            f"SELECT count(*) FROM (SELECT 1 FROM ({_group_sql(where)}) t "
            f"GROUP BY sport, home, away, cid HAVING count(*) > 1) x", *args) or 0)
    except Exception as exc:
        logger.warning("[game_match] 중복 그룹 계수 실패: %s", exc)
        return 0


async def merge_duplicate_games(pool, sport: str | None = None) -> dict:
    """이미 갈라진 중복 행을 합친다. 반환: {"merged", "moved_predictions", ...}.

    유지할 행(**예측이 붙은 쪽**)에 점수를 옮기고, 나머지 행의 참조를 넘긴 뒤
    지운다. 예측이 없으면 더 오래된(먼저 만들어진) 행을 남긴다.

    ⚠️ 예측·전문가픽의 `game_id`를 먼저 옮긴 뒤에 지운다 — 순서를 바꾸면
       외래키가 깨지거나 예측이 조용히 사라진다.
    """
    where = "WHERE sport = $1" if sport else ""
    args = [sport] if sport else []
    # 🔴 [GM-3 2026-09-08] **UTC 날짜로 묶지 않는다 — 시각 근접으로 묶는다.**
    #    종전: `GROUP BY sport, home, away, date_trunc('day', starts_at AT TIME ZONE 'UTC')`
    #    바로 위 `apply_result` 는 그 함정을 이미 알고 시각 근접으로 찾는다 —
    #    "UTC 날짜로 맞추면 MLB 야간경기가 다음 날로 넘어가 못 찾는다."
    #    **같은 파일 안에서 한 함수는 알고 다른 함수는 몰랐다.**
    #
    #    실측 2026-09-08: MLB 2026 정규시즌 2,458경기를 적재하면
    #    `(홈·원정·UTC날짜)` 그룹이 **262개** 생긴다. 실제 더블헤더는 시즌당
    #    30~50건뿐이다 — 나머지는 **금요일 야간(토 00:05 UTC)과 토요일 낮
    #    (토 18:05 UTC)** 이 같은 UTC 날짜에 떨어진 것이다. 그대로 두면 매일
    #    13:00 `finals_job` 이 262쌍을 병합해 **각 쌍의 한 경기를 지운다.**
    #
    #    263쌍의 시간 간격 분포가 창을 정해 준다:
    #      0.0~0.5h    3건   ← 진짜 중복(같은 경기가 두 행)
    #      0.5~4.0h    0건   ← **빈 띠**
    #      4.0~6.0h   11건   ← 더블헤더
    #      6.0~9.0h    8건
    #      9.0~24.0h 241건   ← 서로 다른 날 경기
    #
    # ⚠️ `MATCH_WINDOW_HOURS`(20h)를 그대로 쓰지 않는다. 그것은 "결과를 붙일
    #    경기 찾기"용이고 여기는 "같은 경기인가"라 목적이 다르다.
    #    각 행을 **자기 근방에서 가장 작은 id** 에 붙여 묶는다(단일 연결).
    groups = await pool.fetch(
        f"""
        SELECT sport, home, away, cid, array_agg(id ORDER BY id) AS ids
          FROM ({_group_sql(where)}) t
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
            # ⚠️ [W3-2] `result_basis` 도 함께 살린다 — 병합으로 종료 근거가
            #    사라지면 연장 경기가 정규시간 승부로 둔갑한다.
            "SELECT status, home_score, away_score, result_basis FROM games "
            "WHERE id = ANY($1::int[]) AND home_score IS NOT NULL "
            "ORDER BY (status = 'final') DESC LIMIT 1", ids)
        if best:
            await pool.execute(_UPDATE, keep, best["status"],
                               best["home_score"], best["away_score"],
                               best["result_basis"])
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
