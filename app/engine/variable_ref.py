"""[자료10] 변수 정량화 참조 — **"변수"가 인용할 답 데이터.**

🔴 왜 필요한가. 오늘 저녁 카드의 변수는 이렇게 나갔다:
     "원정 선발 이로운은 선발등판 기록이 0건이라 이닝 소화력 예측 불가"
   위험을 **말하기만** 하고 크기를 주지 않았다. 읽는 사람은 그게 3%p 인지
   15%p 인지 알 수 없고, 우리도 나중에 그 변수가 맞았는지 채점할 수 없다.
   판정이 숫자를 쓰려면 **인용할 숫자가 프롬프트에 있어야 한다.**

⚠️ **새 크롤 소스를 만들지 않는다.** 전부 `pitcher_appearances` 재사용이다.
⚠️ 리그 분기 없음 — 세 리그가 같은 스키마를 쓴다. 단, 1-b 는 **리그 간
   표본을 섞지 않는다** (KBO 부진 회귀를 NPB 에 적용하지 않는다).
⚠️ 해당 없으면 **빈 블록이 아니라 미포함**이다. 빈 칸도 프롬프트를 늘린다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _cfg():
    from app.config import get_settings

    return get_settings()


def quantiles(vals: list[float]) -> dict:
    """p25/p50/p75. **보간하지 않는다** — 실제 등판 값 중 하나를 고른다.

    ⚠️ 보간하면 "실제로 던진 적 없는 이닝"이 참조가 된다. L1 사실 감시가
       그 값을 원문에서 못 찾아 환각으로 찍을 것이고, 그게 맞다.
    """
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return {}
    def pick(q: float) -> float:
        i = min(int(q * (len(xs) - 1) + 0.5), len(xs) - 1)
        return round(float(xs[i]), 2)
    return {"p25": pick(0.25), "p50": pick(0.50), "p75": pick(0.75)}


# ══════════════ 1-a. 투수 이닝 분포 (표본 부재형 변수의 답) ══════════════

_APPEARANCES = """
    SELECT a.innings, a.r, a.is_starter, g.starts_at
      FROM pitcher_appearances a
      JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.pitcher = $2
       AND g.starts_at < $3 AND g.status = 'final'
     ORDER BY g.starts_at DESC
     LIMIT $4
"""


async def innings_profile(pool, sport: str, pitcher: str, before) -> dict:
    """그 투수의 최근 등판 이닝 분포. 없으면 빈 dict.

    선발이 얇은 투수를 **구원 기록까지 합쳐** 본다 — "몇 이닝 던지는
    사람인가"가 질문이고, 그건 선발/구원을 가리지 않는다.
    """
    if pool is None or not sport or not pitcher:
        return {}
    s = _cfg()
    try:
        rows = await pool.fetch(_APPEARANCES, sport, pitcher, before,
                                int(s.var_ref_appearances))
    except Exception as exc:
        logger.warning("[var-ref] %s %s 등판 조회 실패: %s", sport, pitcher, exc)
        return {}
    if not rows:
        logger.info("[var-ref] %s %s 등판 기록 0건 — 이닝 분포 없음",
                    sport, pitcher)
        return {}
    ip = [float(r["innings"]) for r in rows if r["innings"] is not None]
    if not ip:
        return {}
    starts = sum(1 for r in rows if r["is_starter"])
    out = {"n": len(rows), "이닝": [round(x, 2) for x in ip],
           "선발등판": starts, "구원등판": len(rows) - starts,
           "최장": round(max(ip), 2), **quantiles(ip)}
    logger.info("[var-ref] %s %s 이닝 분포 n=%d 선발%d p50=%s 최장=%s",
                sport, pitcher, out["n"], starts, out.get("p50"), out["최장"])
    return out


def needs_innings_profile(jg: dict, side: str) -> bool:
    """선발 등판이 `var_ref_low_start_max` **미만**이면 붙인다."""
    r = jg.get("research") or {}
    starts = len(r.get(f"{side}_starter_recent") or [])
    return starts < int(_cfg().var_ref_low_start_max)


# ══════════════ 1-b. 부진 후 회귀 참조 (최근 폼 괴리형) ══════════════

def form_gap(jg: dict, side: str) -> float | None:
    """최근 3등판 환산 실점률 − 시즌 ERA. 못 재면 None.

    ⚠️ 자책(ER)이 아니라 실점(R)으로 환산한다 — `pitcher_appearances` 가
       두 값을 다 갖고 있지만 최근 등판 블록(`slim_start`)이 `r` 만 싣는다.
       같은 자료에서 나온 값끼리 비교해야 한다.
    """
    r = jg.get("research") or {}
    recent = (r.get(f"{side}_starter_recent") or [])[:3]
    ip = sum(float(x.get("innings") or 0) for x in recent)
    runs = sum(float(x.get("r") or 0) for x in recent)
    if ip <= 0 or len(recent) < 3:
        return None
    season = ((r.get(f"{side}_starter_season") or {}).get("era"))
    if season is None:
        return None
    try:
        return round(runs * 9.0 / ip - float(season), 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


_REGRESSION = """
    WITH app AS (
        SELECT a.pitcher, a.innings, a.r, g.starts_at,
               row_number() OVER (PARTITION BY a.pitcher ORDER BY g.starts_at) AS seq
          FROM pitcher_appearances a
          JOIN games g ON g.id = a.game_id
         WHERE g.sport = $1 AND a.is_starter AND g.status = 'final'
           AND g.starts_at >= $2 AND a.innings > 0
    ), win AS (
        SELECT a.pitcher, a.seq, a.innings, a.r,
               sum(a.r) OVER w * 9.0 / NULLIF(sum(a.innings) OVER w, 0) AS prev3_ra,
               avg(a.r * 9.0 / NULLIF(a.innings, 0)) OVER (PARTITION BY a.pitcher)
                   AS season_ra
          FROM app a
        WINDOW w AS (PARTITION BY a.pitcher ORDER BY a.seq
                     ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING)
    )
    SELECT count(*) AS n, avg(innings) AS ip, avg(r) AS r
      FROM win
     WHERE prev3_ra IS NOT NULL AND season_ra IS NOT NULL
       AND prev3_ra - season_ra >= $3
"""


async def regression_reference(pool, redis, sport: str, season_start: str) -> dict:
    """그 리그에서 "직전 3등판이 부진했던 투수"의 **다음 등판** 분포.

    ⚠️ 표본이 `var_ref_min_sample` 미만이면 **"참조 불충분"으로 라벨**하고
       숫자 해석은 판정에 맡긴다. 적은 표본으로 단정하지 않는다.
    ⚠️ 리그를 섞지 않는다 — 인자로 받은 `sport` 안에서만 센다.
    """
    if pool is None or not sport:
        return {}
    s = _cfg()
    key = f"var_ref:regression:{sport}:{season_start}"
    if redis is not None:
        try:
            import json as _json

            raw = await redis.get(key)
            if raw:
                return _json.loads(raw)
        except Exception as exc:
            logger.debug("[var-ref] 회귀 캐시 읽기 실패: %s", exc)
    try:
        row = await pool.fetchrow(_REGRESSION, sport, season_start,
                                  float(s.var_ref_era_gap))
    except Exception as exc:
        logger.warning("[var-ref] %s 회귀 참조 조회 실패: %s", sport, exc)
        return {}
    n = int((row or {}).get("n") or 0)
    out = {"리그": sport.upper(), "표본": n,
           "기준": f"직전 3등판 실점률이 시즌 대비 +{s.var_ref_era_gap} 이상"}
    if n:
        out["다음등판_평균이닝"] = round(float(row["ip"] or 0), 2)
        out["다음등판_평균실점"] = round(float(row["r"] or 0), 2)
    if n < int(s.var_ref_min_sample):
        out["주의"] = f"참조 불충분, n={n}"
        logger.info("[var-ref] %s 회귀 참조 표본 부족 n=%d (<%d)",
                    sport, n, s.var_ref_min_sample)
    else:
        logger.info("[var-ref] %s 회귀 참조 n=%d 다음등판 %.2f이닝 %.2f실점",
                    sport, n, out["다음등판_평균이닝"], out["다음등판_평균실점"])
    if redis is not None:
        try:
            import json as _json

            await redis.set(key, _json.dumps(out, ensure_ascii=False),
                            ex=int(s.var_ref_cache_sec))
        except Exception as exc:
            logger.debug("[var-ref] 회귀 캐시 기록 실패: %s", exc)
    return out


# ══════════════ 1-c. 타선 침체 맥락 — 상대 선발 시즌 ERA ══════════════

#: 🔴 [2026-09-05] **외부 경기 ID 로 찾지 않는다. 날짜+팀으로 찾는다.**
#   ID 공간이 셋으로 갈려 있었다:
#     games.ext_id              "kbo:2026-09-04:18:30:KT Wiz:Kia Tigers"
#     usage.games[].game_id     "20260904HHLT02026"   ← 네이버 형식
#     pitcher_appearances.game_id  BIGINT (= games.id)
#   종전 코드는 `int(gid)` 로 네이버 문자열을 정수로 바꾸려 했고, KBO 전
#   경기에서 터졌다(운영 실측 2026-09-05):
#     [var-ref] 상대 선발 조회 실패 game=20260904HHLT02026:
#               invalid literal for int() with base 10
#   ⚠️ 캐스팅으로 못 고친다 — 설령 정수였어도 네이버 ID 로는 우리 games.id 를
#      찾을 수 없다. `ext_id` 형식이 아예 다르기 때문이다.
#   날짜+팀은 세 리그가 모두 갖고 있는 값이라 ID 공간에 의존하지 않는다.
_OPP_STARTER = """
    SELECT a.pitcher
      FROM pitcher_appearances a
      JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1
       AND (g.starts_at AT TIME ZONE 'Asia/Seoul')::date = $2::date
       AND a.team = $3 AND a.is_starter
     LIMIT 1
"""


async def attach_opp_starter_era(pool, jg: dict, redis=None) -> int:
    """자료1 각 경기에 **그때 상대 선발의 시즌 ERA** 를 붙인다. 반환 채운 수.

    🔴 "최근 3경기 2득점"이 타선 침체인지 상대 에이스를 만난 것인지,
       지금 프롬프트로는 구분할 수 없다. 상대 순위·승률은 팀 얘기이지
       **그날 마운드에 선 사람** 얘기가 아니다.

    ⚠️ 새 크롤 없음 — `pitcher_appearances`(그 경기 상대 선발)와
       `starter_season`(시즌 라인)을 그대로 쓴다.
    ⚠️ 이름 매칭 실패는 **null + 로그 1줄**이다. 조용히 지나가지 않는다.
    """
    if pool is None:
        return 0
    from datetime import UTC, datetime

    from app.collectors.starter_season import fetch_asia, fetch_mlb, lookup_asia

    sport = (jg.get("sport") or "").lower()
    research = jg.get("research") or {}
    rows: list[tuple[dict, str]] = []
    for side in ("home", "away"):
        for g in ((research.get(f"{side}_usage") or {}).get("games") or []):
            gid, opp = g.get("game_id"), g.get("opponent")
            gdate = g.get("date")
            if not gdate or not opp or "opp_starter_season_era" in g:
                continue
            try:
                name = await pool.fetchval(_OPP_STARTER, sport, str(gdate), opp)
            except Exception as exc:
                logger.warning("[var-ref] 상대 선발 조회 실패 %s %s vs %s: %s",
                               sport, gdate, opp, exc)
                continue
            if not name:
                g["opp_starter_season_era"] = None
                logger.info("[var-ref] 상대 선발 미상 game=%s opp=%s — null", gid, opp)
                continue
            rows.append((g, str(name)))
    if not rows:
        return 0
    season = datetime.now(UTC).year
    names = sorted({n for _, n in rows})
    try:
        if sport == "mlb":
            table = await fetch_mlb(names, season, redis)
            get = table.get
        else:
            table = await fetch_asia(sport, season, redis)
            def get(n):
                return lookup_asia(table, sport, n)
    except Exception as exc:
        logger.warning("[var-ref] %s 시즌 라인 조회 실패 — ERA 없이 간다: %s",
                       sport, exc)
        for g, _ in rows:
            g["opp_starter_season_era"] = None
        return 0
    n = 0
    for g, name in rows:
        era = (get(name) or {}).get("era")
        g["opp_starter_season_era"] = era
        if era is None:
            logger.info("[var-ref] 상대 선발 시즌 라인 미매칭 %s %s — null",
                        sport, name)
        else:
            n += 1
    logger.info("[var-ref] %s 상대 선발 시즌 ERA %d/%d 부착", sport, n, len(rows))
    return n


# ══════════════ 자료10 조립 ══════════════

#: 자료10 상태 3값 — 로그·계측이 이 값을 그대로 쓴다.
M10_YES, M10_MISSING, M10_NA = "Y", "N", "해당없음"


async def attach_material10(pool, redis, jg: dict) -> str:
    """`jg["material10"]` 과 상태를 채운다. 반환 상태 3값.

    🔴 **해당 없으면 빈 블록이 아니라 미포함**이다. 빈 칸도 프롬프트를
       늘리고, 판정은 빈 칸을 "자료가 없다"는 신호로 읽는다.
    ⚠️ I/O 는 여기서 끝낸다 — 판정 경로(`matchup.py`)는 이미 채워진 값을
       읽기만 한다. 판정 시점에 DB 를 때리면 T-차감 시간이 늘어난다.
    """
    needed = any(needs_innings_profile(jg, sd) for sd in ("home", "away"))
    gaps = [form_gap(jg, sd) for sd in ("home", "away")]
    thr = float(_cfg().var_ref_era_gap)
    needed = needed or any(g is not None and g >= thr for g in gaps)
    if not needed:
        jg["material10"] = {}
        jg["material10_status"] = M10_NA
        return M10_NA
    try:
        blk = await build_material10(pool, redis, jg)
    except Exception as exc:
        logger.warning("[var-ref] 자료10 조립 실패 game=%s: %s",
                       jg.get("game_id"), exc)
        blk = {}
    jg["material10"] = blk
    jg["material10_status"] = M10_YES if blk else M10_MISSING
    if not blk:
        logger.warning("[var-ref] 🔴 자료10 대상인데 비었다 game=%s — "
                       "변수가 인용할 숫자가 없다", jg.get("game_id"))
    return jg["material10_status"]


async def build_material10(pool, redis, jg: dict) -> dict:
    """자료10 블록. **해당 없으면 빈 dict** — 호출부가 아예 안 싣는다."""
    from datetime import UTC, datetime

    out: dict = {}
    sport = (jg.get("sport") or "").lower()
    # 🔴 [2026-09-04] `starts_at` 은 분석 캐시(JSON)를 거치면 **문자열**이다.
    #    날것으로 넘기면 asyncpg 가 timestamptz 파라미터로 거부하고, 그 예외가
    #    `자료10=N` 으로 나타난다 — 실측: Jake Bennett·Kade Anderson·
    #    Jack Perkins 3경기. **자료10 이 겨냥한 바로 그 투수들**(등판 기록이
    #    얇은 신인)이 통째로 빠졌다.
    #    `starter_recent._aware` 가 이미 같은 문제를 풀어 놨다 — 그걸 쓴다.
    from app.engine.starter_recent import _aware

    before = _aware(jg.get("starts_at")) or datetime.now(UTC)
    from app.engine.starter_recent import pitcher_name

    for side in ("home", "away"):
        blk: dict = {}
        if needs_innings_profile(jg, side):
            prof = await innings_profile(pool, sport, pitcher_name(jg, side), before)
            if prof:
                blk["이닝분포"] = prof
        gap = form_gap(jg, side)
        if gap is not None and gap >= float(_cfg().var_ref_era_gap):
            ref = await regression_reference(
                pool, redis, sport, f"{datetime.now(UTC).year}-01-01")
            if ref:
                blk["부진후회귀"] = {"최근3등판_시즌대비": gap, **ref}
        if blk:
            out[side] = blk
    return out
