"""[v1.4 STEP 6] ⑤ 수집 — **가설이 정한 변수만** 찾는다.

🔴 목록 밖 항목은 요청하지 않는다. 딥서치 요약이 배당·H2H 를 끼워 넣는 것이
   이 저장소의 반복 결함이었다 — 화이트리스트로 막고, 밖의 키는 버린다.
🔴 **새 수집기를 만들지 않는다.** 이미 있는 것을 부른다:
     위성 추출  `satellite.read_extract`  (기사 → 8칸 JSON)
     공식 결장  `research["absences"]`     (statsapi IL + 확정 라인업)
     최근 3경기 `games` 표
🔴 원문 없는 evidence 는 폐기한다 — "수집했다"와 "봤다"는 다르다.
⚠️ 예산: 경기당·슬레이트 상한은 `flow.deepsearch_cap` 이 원본. 초과하면
   그 변수는 `unknown` 으로 남기고 **조용히 넘기지 않는다**.
"""
from __future__ import annotations

import logging

from app.collectors import absences as _ABS
from app.engine.performance import filter_by_roster
from app.flow import direction as DIR
from app.flow.labels import UNRUN

logger = logging.getLogger(__name__)

NODE = "n05_evidence"

_MAX_EXCERPT = 300

#: 변수 → 어느 수집물에서 찾나. 🔴 이름은 `flow.adjust_prior_pp` 가 원본이고
#  여기서는 **읽기만** 한다(키를 새로 짓지 않는다).
_FROM_EXTRACT = {"lineup_out": "out", "xi_confirmed": "out",
                 "form_recent5": "last3", "rotation_risk": "midweek"}

#: 🔴 [2026-09-19] **불펜 최근 3일.** 원본은 `pitcher_appearances` 다 —
#   이미 적재돼 있었다(실측: MLB 754행 · NPB 260행 · 최신 09-18).
#   핵심 변수인데 소스가 없어 언제나 `unknown` 이었다.
#   ⚠️ **선발은 제외한다**(`is_starter = false`) — 불펜 소모를 재는 값이다.
_BULLPEN_SQL = """
    SELECT pa.pitcher, pa.innings, (g.starts_at AT TIME ZONE 'Asia/Seoul')::date d
      FROM pitcher_appearances pa
      JOIN games g ON g.id = pa.game_id
     WHERE pa.team = $1
       AND pa.is_starter = false
       AND g.starts_at <  $2::timestamptz
       AND g.starts_at >= $2::timestamptz - interval '3 days'
     ORDER BY g.starts_at DESC
"""

#: 🔴 [2026-09-18 페이블 검토] 선발 변경 문장의 팀 접두사.
#   원본은 `pipeline.starter_change_notes` 의 f-string 이다 —
#   `f"{label} 선발 변경: {old} → {new}"`, label 은 "홈"|"원정".
#   ⚠️ 그 형식이 바뀌면 여기가 조용히 깨진다. 계약 테스트가 **그 함수의 실제
#      출력**으로 결합을 고정한다(WIR-1 의 `_describe` 와 같은 방식).
_SIDE_KR = {"홈": "home", "원정": "away"}


#: 🔴 [HYC-1 2026-09-20] `out_src` 가 이 값이면 **LLM 이 뽑은 것**이다.
#   원본은 `satellite._json_wins` 가 쓰는 문자열이다 — 여기서 목록을 만들지
#   않는다. 그 외 값(`fotmob` 등)은 **코드가 조회한 구조 소스**이고, 그때는
#   기사 URL 이 아니라 소스명 + 상자 조회 시각이 출처다.
_LLM_SRC = "llm"


def card_trust(box: dict | None, side_card: dict | None) -> tuple:
    """[HYC-1] 이 카드를 **증거로 쓸 수 있나.** `(가능?, 사유)`.

    🔴 **검증 근거는 코드가 쓴 것만 쓴다**(사용자 결정 2026-09-20).
         수집 시각 → 상자 최상위 `gathered_at` (위성이 코드로 쓴다)
         출처      → `sources_fed` (그 LLM 호출에 **실제로 넣은** 기사 URL)
         구조 소스 → `out_src != "llm"` 이면 소스명 + 조회 시각이 출처다
       LLM 이 채운 `llm_source`·`llm_fetched_at` 은 **보지 않는다.**
       모델이 만든 문자열이라 그것으로 검증하면 검증이 아니다.

    🔴 실측 2026-09-20 (운영 상자 42쪽): `fetched_at` 42/42 빈 칸 ·
       `source` 30/42 빈 칸 · `conflict` 17/42. 그런데 ⑤는 셋을 **하나도
       보지 않고** 값이 있으면 증거로 실었다.

    ⚠️ 충돌(`conflict`)은 다른 축이다 — 출처가 있어도 **두 소스가 다른 말**을
       하면 어느 쪽이 맞는지 판정할 수 없다(오늘 인천: 무고사가 결장 목록과
       선발 XI에 동시 존재).
    ⚠️ 이 함수는 **상자 카드만** 본다. 공식 결장(`_cache_absences`)은 판정
       캐시에서 오므로 여기 규칙과 무관하게 그대로 센다.
    """
    card = side_card or {}
    if not card:
        return False, "상자에 이 팀 카드가 없다"
    if card.get("conflict"):
        return False, "두 소스가 충돌한다 — 어느 쪽이 맞는지 판정 불가"
    if not str((box or {}).get("gathered_at") or "").strip():
        return False, "수집 시각(gathered_at)이 없다 — 언제 본 자료인지 모른다"
    if str(card.get("out_src") or _LLM_SRC) != _LLM_SRC:
        return True, ""                    # 구조 소스 — 코드가 조회했다
    if not [u for u in (card.get("sources_fed") or []) if str(u).strip()]:
        return False, "코드가 아는 출처(sources_fed)가 없다 — 검증 불가"
    return True, ""


def _B2B_HOURS() -> float:
    """[LOAD-1] 야구 연전 창(시간). 🔴 축구 96h 와 **다른 값**이다 —
    야구는 매일 경기라 96시간이면 전건이 연전으로 읽힌다."""
    from app.flow import rules as R

    return float(R.get("load.b2b_window_h", 26) or 26)


def _DEV_FULL() -> float:
    """[NWS-D] ⑦의 강도 기준값. 🔴 원본은 `config/rules.yaml` 하나다."""
    from app.flow import rules as R

    return float(R.get("direction.dev_full", 0.5))


def _row(var: str, value, *, source: str, url: str = "", excerpt: str = "",
         sides: dict | None = None, direction: dict | None = None,
         untrusted_reason: str = "", status: str = "",
         pitcher_il: list | None = None) -> dict:
    """증거 한 줄. 🔴 [FIX-1] `direction` 이 **부호의 원본**이다 —
    `sides`(항목 수)는 표시용으로만 남는다(⑦이 더 이상 읽지 않는다)."""
    return {"var": var, "value": value, "source": source, "source_url": url,
            "raw_excerpt": excerpt, "sides": sides or {},
            "direction": direction or {}, "fetched_at": None,
            # 🔴 [HYC-1] 비어 있으면 믿을 수 있는 카드다. 차 있으면 **왜 못
            #    믿는지**가 남는다 — 그래야 "안 찾았다"와 구분된다.
            "untrusted_reason": untrusted_reason,
            # 🔴 [HYC-3] 비어 있으면 **잴 수 있었다**는 뜻이다. `미실행` 이면
            #    ⑤에 그 변수를 찾을 길이 없었다는 뜻이고 ⑥이 분모에서 뺀다.
            "status": status,
            # 🔴 [PIPE-5 2026-09-25] `lineup_out` 에서 뺀 **투수 결장**.
            #    버리지 않고 여기 남긴다 — `starter_recent3`·`bullpen_3d`
            #    의 참고 칸이고, 서술·내보내기가 "결장 N명"에 세지 않는다.
            "pitcher_il": list(pitcher_il or [])}


async def _cache_doc(state, ctx) -> dict:
    """판정 캐시의 이 경기 항목. 🔴 **새로 수집하지 않는다** — 파이프라인이
    이미 만들어 둔 `analysis:{sport}:{date}` 를 읽는다(내보내기가 읽는 자리).

    🔴 **MLB 는 캐시 키가 미 동부 날짜다.** 실측 2026-09-19:
       `analysis:mlb:2026-09-19` 없음 · `analysis:mlb:2026-09-18` 있음.
       KST 날짜로만 찾으면 MLB 는 언제나 빈손이다.
       ⚠️ 규칙의 원본은 `pipeline.mlb_slate_date` 다 — 여기서 달력을 새로
          만들지 않고 **양쪽 날짜를 다 본다.**
    """
    if ctx.redis is None:
        return {}
    import json
    from datetime import date as _d
    from datetime import timedelta as _td

    sport = _sport_code(state)
    base = (state.kickoff_utc or "")[:10]
    days = [base]
    try:
        days.append((_d.fromisoformat(base) - _td(days=1)).isoformat())
    except ValueError:
        pass
    for day in days:
        try:
            raw = await ctx.redis.get(f"analysis:{sport}:{day}")
        except Exception as exc:
            logger.info("[flow:n05] 캐시 못 읽음 %s %s: %s", sport, day, exc)
            return {}
        if not raw:
            continue
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        for g in doc.get("games") or []:
            if str(g.get("game_id")) == str(state.game_id):
                return g
    return {}


async def _cache_absences(state, ctx) -> list:
    """결장 문장. 주입이 **먼저**다 — 픽스처·드라이런이 캐시에 덮이면 안 된다."""
    inj = (ctx.inject or {})
    if "absences" in inj:
        return list(inj["absences"] or [])
    g = await _cache_doc(state, ctx)
    got = list(((g.get("research") or {}).get("absences")) or [])
    logger.info("[flow:n05] game=%s 캐시 결장 %d건%s", state.game_id, len(got),
                "" if g else " (판정 캐시 없음)")
    return got


async def _cache_starter_notes(state, ctx) -> list:
    """선발 교체 메모. 감지는 이미 있었고(`pipeline.starter_change_notes`)
    ⑤가 그것을 보지 않았다 — WIR-1 과 같은 "만들어 놓고 안 이음"이다."""
    inj = (ctx.inject or {})
    if "starter_notes" in inj:
        return list(inj["starter_notes"] or [])
    g = await _cache_doc(state, ctx)
    notes = g.get("lineup_notes") or []
    if isinstance(notes, str):
        notes = [notes]
    return [n for n in notes if n]


async def _extract_box(state, ctx) -> dict:
    """위성 추출 **상자 전체** `{gathered_at, sources_fed?, teams:{...}}`.

    🔴 [HYC-1 2026-09-20] 종전에는 `teams` 만 돌려줬다. 그러면 ⑤가 **수집
       시각을 영영 볼 수 없다** — `gathered_at` 은 상자 최상위에 있고 그것이
       코드가 쓴 유일한 시각이기 때문이다(쪽 카드의 `fetched_at` 은 LLM 칸이라
       42/42 빈 칸이었다).
    ⚠️ 옛 모양(teams 만)으로 주입하는 자리가 있다 — `teams` 키가 없으면
       그것을 teams 로 읽고 메타는 없는 것으로 둔다(그때는 신뢰 검사가
       "수집 시각 없음"으로 떨어진다. 지어내지 않는다).
    """
    raw = None
    if "extract" in (ctx.inject or {}):
        raw = dict(ctx.inject["extract"] or {})
    elif ctx.redis is not None:
        try:
            from app.collectors.satellite import read_extract

            raw = await read_extract(ctx.redis, _sport_code(state),
                                     state.game_id)
        except Exception as exc:
            logger.info("[flow:n05] 위성 추출 없음 game=%s: %s",
                        state.game_id, exc)
    if not raw:
        return {}
    if "teams" in raw:
        return dict(raw)
    return {"teams": dict(raw)}


def _sport_code(state) -> str:
    """`games.sport` 코드. 🔴 [KEY-1 2026-09-24] **원본을 `labels` 로 옮겼다** —
    ②도 같은 코드가 필요한데 노드끼리 import 할 수 없기 때문이다(그 규약을
    피하려다 ②가 사본을 지었고 인자 순서를 틀려 기사 886건을 못 읽었다)."""
    from app.flow.labels import sport_code

    return sport_code(state)


def _split(state, absences: list) -> tuple:
    """결장 문장을 홈/원정으로 가른다.

    🔴 분리 규칙의 원본은 `performance._split_absences` 다 — 여기서 새로 짓지 않는다.
    """
    try:
        from app.engine.performance import _split_absences

        return _split_absences(list(absences),
                               {"home": state.home, "away": state.away})
    except Exception:
        return [], []


#: [W2] 로스터 — **이미 쌓인 출장 기록**에서 읽는다(새 수집기 0).
#  ⚠️ 창을 넓게 잡지 않는다. 트레이드가 있으면 옛 소속이 섞이고, 그러면
#     "두 팀"으로 보여 동명이인과 구분되지 않는다.
_ROSTER_SQL = """
    SELECT name, team FROM (
        SELECT ba.batter AS name, ba.team AS team
          FROM batter_appearances ba JOIN games g ON g.id = ba.game_id
         WHERE g.league = $1 AND g.starts_at > now() - interval '30 days'
        UNION
        SELECT pa.pitcher AS name, pa.team AS team
          FROM pitcher_appearances pa JOIN games g ON g.id = pa.game_id
         WHERE g.league = $1 AND g.starts_at > now() - interval '30 days'
    ) t
"""


async def _roster(state, ctx) -> dict:
    """`{이름: {팀, …}}`. 못 읽으면 **빈 dict** — 그때는 아무것도 걸러지지 않는다.

    🔴 [W2 2026-09-21] 이름이 두 팀으로 이어지면 그것은 **동명이인**이다
       (실측: 박건우 NC 26회 · 롯데 9회 · g1723 에 양 팀 동시 출전).
       거르는 판단은 `performance.filter_by_roster` 한 곳이 한다.
    ⚠️ 축구는 출장 기록이 없어 빈 dict 이고, 그건 정상이다 — 없는 자료로
       거르는 척하지 않는다.
    """
    if "roster" in (ctx.inject or {}):
        return dict(ctx.inject["roster"] or {})
    if ctx.pool is None:
        return {}
    try:
        rows = await ctx.pool.fetch(_ROSTER_SQL, state.league)
        out: dict = {}
        for r in rows:
            nm = str(r["name"] or "").strip()
            if nm:
                out.setdefault(nm, set()).add(str(r["team"] or "").strip())
        return out
    except Exception as exc:
        logger.info("[flow:n05] 로스터 조회 실패 game=%s: %s", state.game_id, exc)
        return {}


#: 선발 최근 등판 — 내보내기의 `_STARTER_SQL` 과 같은 표를 본다.
#  ⚠️ 창이 다르다: 내보내기는 "우리가 본 등판 전부", 여기는 **최근 3등판**이다.
_STARTER3_SQL = """
    SELECT pa.innings, pa.er, pa.k, pa.bb, pa.opponent,
           (g.starts_at AT TIME ZONE 'Asia/Seoul')::date d
      FROM pitcher_appearances pa
      JOIN games g ON g.id = pa.game_id
     WHERE pa.pitcher = $1 AND pa.is_starter = true
       AND g.starts_at < $2::timestamptz
     ORDER BY g.starts_at DESC
     LIMIT 3
"""


def era_of_rows(rows) -> float | None:
    """등판 행 → 방어율. 🔴 이닝이 0이면 **None** (0.00 은 완봉을 뜻한다)."""
    ip = sum(float(r.get("innings") or 0) for r in (rows or []))
    if ip <= 0:
        return None
    er = sum(int(r.get("er") or 0) for r in (rows or []))
    return round(9.0 * er / ip, 2)


def _league_era(state, ctx) -> float | None:
    """리그 평균 방어율. 🔴 **새 상수를 만들지 않는다** — settings 가 원본이다."""
    try:
        from app.config import get_settings

        s = ctx.settings or get_settings()
    except Exception:
        return None
    code = _sport_code(state)
    return {"kbo": getattr(s, "kbo_league_era", None),
            "npb": getattr(s, "npb_league_era", None)}.get(
        code, getattr(s, "league_era", None))


def opp_starter_of(state, starters: dict | None) -> str | None:
    """**상대** 선발. 🔴 조사 방향이 원정이면 홈 선발이 그것을 막는 쪽이다.

    ⚠️ [SIDE-2] `hyp_side` 다 — ⑤는 "누구를 조사하나"이지 "누구를 고르나"가
       아니다. 후자는 ⑧이 정한다.
    """
    opp = "home" if (state.hyp_side or "home") == "away" else "away"
    return (starters or {}).get(opp) or None


async def _starter_recent3(state, ctx) -> dict:
    """**양 팀 선발**의 최근 3등판. 반환 `{side: (줄목록, 투수명, era3, 원행)}`.

    🔴 **교체 메모와 다른 사실이다.** 선발이 안 바뀌어도 그 선발이 최근 어떻게
       던졌는지는 득점 전망을 바꾼다.

    🔴 [UND-1 2026-09-23 사용자 결정 (가)] **양쪽을 본다.** 종전에는
       `opp_starter_of` 로 **상대 선발만** 봤고, 그래서 ⑪의 언더 조건
       ("양 팀 선발 모두 호재")이 구조적으로 성립하지 못했다:
```
최근 14일  starter_recent3 양쪽 다 +  0건 · 한쪽만 +  329건
           ⑤ 수집 쪽  sides=('away',) 758 · ('home',) 448 · 둘 다 0
```
       오버는 종전에도 동작했다(−1 403회) — 못 서던 것은 언더뿐이다.
    ⚠️ 유불리는 여기서 정하지 않는다 — 방향은 `direction.starter_direction`
       이 쪽별로 내고 `merge` 가 합친다(사본 금지).
    ⚠️ 예고 전이면 한쪽만 안다. 없는 쪽은 **넣지 않는다**(지어내지 않는다).
    """
    inj = (ctx.inject or {})
    starters = inj.get("starters")
    if starters is None:
        if ctx.pool is None:
            return {}
        try:
            row = await ctx.pool.fetchrow(
                "SELECT home_pitcher, away_pitcher FROM games WHERE id = $1",
                int(state.game_id))
        except Exception as exc:
            logger.warning("[flow:n05] 선발 조회 실패 game=%s: %s", state.game_id, exc)
            return {}
        starters = {"home": (row or {}).get("home_pitcher"),
                    "away": (row or {}).get("away_pitcher")}
    ko = _kickoff_dt(state.kickoff_utc)
    if ctx.pool is None or ko is None:
        return {}
    out: dict = {}
    for side in ("home", "away"):
        who = (starters or {}).get(side)
        if not who:
            continue
        try:
            rows = await ctx.pool.fetch(_STARTER3_SQL, who, ko)
        except Exception as exc:
            logger.warning("[flow:n05] 선발 최근3 조회 실패 game=%s %s: %s",
                           state.game_id, who, exc)
            continue
        if not rows:
            continue
        out[side] = ([f"{r['d']:%m-%d} vs {r['opponent']} "
                      f"{float(r['innings'] or 0):.1f}이닝 {r['er']}자책 {r['k']}K"
                      for r in rows], who, era_of_rows(rows),
                     [dict(r) for r in rows])
    return out


def _kickoff_dt(raw):
    """킥오프 → `datetime`. 🔴 못 읽으면 **None** 이다.

    🔴 asyncpg 는 `::timestamptz` 캐스트가 SQL 안에 있어도 **바인딩 단계에서**
       타입을 본다 — 문자열을 넘기면 `DataError` 다(실측 2026-09-20).
       그 예외를 호출부가 삼키면 조회가 영원히 빈손이 되고, ⑥은 그것을
       "자료 없음"으로 읽는다. 이 저장소는 같은 함정을 두 번째 겪었다.
    """
    from datetime import datetime

    if raw is None or isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


async def _bullpen3d(state, ctx, side: str) -> list:
    """그 팀 불펜의 최근 3일 등판. 🔴 기사에 묻지 않는다 — DB 에 있다."""
    if "bullpen" in (ctx.inject or {}):
        got = list((ctx.inject["bullpen"] or {}).get(side) or [])
        return got, []
    ko = _kickoff_dt(state.kickoff_utc)
    if ctx.pool is None or ko is None:
        return [], []      # 시각을 모르면 3일 창을 만들 수 없다 — 지어내지 않는다
    team = getattr(state, side, "")
    try:
        rows = await ctx.pool.fetch(_BULLPEN_SQL, team, ko)
    except Exception as exc:
        # 🔴 warning 이다. info 로 두면 정상 로그에 묻히고, 빈 목록이
        #    "자료 없음"과 구분되지 않는다(실측: 그래서 몇 주를 몰랐다).
        logger.warning("[flow:n05] 불펜 조회 실패 game=%s %s: %s",
                       state.game_id, side, exc)
        return [], []
    return ([f"{r['d']:%m-%d} {r['pitcher']} {float(r['innings'] or 0):.1f}이닝"
             for r in rows], [dict(x) for x in rows])


#: 🔴 [XI-1 2026-09-23] 축구 확정 선발 XI. **표에 이미 있다** — flashscore 가
#   킥오프 1시간 안에 전 리그 11명을 넣고 `satellite_soccer` 가 `lineups` 에
#   적는다(라리가·EPL·세리에A·분데스·J1·K리그1·덴마크·ACL 전부).
#   그런데 ⑤는 그 표를 **한 번도 읽지 않았다** — 위성 추출 상자(`out`)만
#   봤고, LLM 을 0 으로 만든 뒤로는 그 상자가 비어 영원히 미상이었다
#   (실측: 최근 3일 `xi_confirmed` 305건 전건 unknown).
# ⚠️ 최신 한 벌만 본다 — 같은 경기·같은 쪽에 예상/확정이 둘 다 있을 수 있다.
_XI_SQL = """
    SELECT l.side, l.status, l.source, l.starter, l.batting_order,
           l.scratches, l.captured_at
      FROM lineups l
     WHERE l.game_id = $1
     ORDER BY l.captured_at DESC
"""


async def _xi_rows(state, ctx) -> list:
    """이 경기의 라인업 행. 🔴 못 읽으면 **빈 목록**(미상) — 지어내지 않는다.

    🔴 [LOAD-1 2026-09-23] **한 번만 조회한다.** 부르는 곳이 셋이 됐다
       (확정 XI · 결장자 · 오늘 타순). 호출 수를 줄이는 대신 결과를 상태에
       기억해 **경기당 1질의**를 지킨다 — 종전 계약의 취지 그대로다.
    ⚠️ 빈 결과도 기억한다. 못 읽은 것을 매번 다시 때리면 실패가 3배가 된다.
    """
    memo = getattr(state, "_xi_memo", None)
    if memo is not None:
        return memo
    rows: list = []
    if ctx.pool is not None:
        try:
            gid = int(state.game_id)
        except (TypeError, ValueError):
            gid = None
        if gid is not None:
            try:
                rows = [dict(r) for r in await ctx.pool.fetch(_XI_SQL, gid)]
            except Exception as exc:
                logger.warning("[flow:n05] 라인업 조회 실패 game=%s: %s",
                               state.game_id, exc)
    try:
        state._xi_memo = rows
    except Exception:                      # 슬롯 있는 대역이면 못 붙는다
        pass
    return rows


def _order_by_side(rows) -> dict:
    """[LOAD-1] 쪽별 **오늘 타순 이름들**. 최신 한 벌만 본다.

    🔴 확정이 없으면 그 쪽은 **빈 값**이다 — 예상 타순으로 단정하지 않는다
       (`lineup_direction` 의 "미확정" 규약과 같다).
    """
    import json as _json

    out: dict = {}
    for r in rows or []:
        sd = str(r.get("side") or "")
        if sd not in ("home", "away") or sd in out:
            continue          # DESC 정렬이라 첫 행이 최신이다
        bo = r.get("batting_order")
        if isinstance(bo, str):
            try:
                bo = _json.loads(bo)
            except (TypeError, ValueError):
                bo = None
        if isinstance(bo, list) and bo:
            out[sd] = [str(x) for x in bo if x]
    return out


async def _park_of(state, ctx) -> tuple:
    """[VEN-1] 홈 구장 파크팩터 `(이름, 값, 출처)`. 모르면 `(None, None, "")`.

    🔴 **모르는 것을 1.0 으로 채우지 않는다.** "측정했는데 중립"과 "못 쟀다"가
       구분되지 않는다(`kbo_park.merge_into_research` 와 같은 규약).
    ⚠️ NPB 는 산출 모듈이 **없다** — 미상이 정상이다.
    ⚠️ 팀→구장 대조표를 여기서 만들지 않는다. `kbo_park.STADIUM_OF_TEAM` 이
       원본이다(사본 금지).
    """
    if ctx.redis is None:
        return (None, None, "")
    code = _sport_code(state)
    home = getattr(state, "home", "") or ""
    try:
        if code == "kbo":
            from app.collectors.kbo_park import STADIUM_OF_TEAM, load

            park = STADIUM_OF_TEAM.get(home)
            table = await load(ctx.redis) or {}
            row = table.get(park) if park else None
            pf = (row or {}).get("pf") if isinstance(row, dict) else row
            return (park, pf, "kbo_park") if (park and pf) else (None, None, "")
        if code == "mlb":
            from app.collectors.park import load

            table = await load(ctx.redis) or {}
            pf = table.get(home)
            return (home, pf, "park") if pf else (None, None, "")
    except Exception as exc:
        logger.warning("[flow:n05] 파크팩터 조회 실패 game=%s: %s",
                       state.game_id, exc)
        return (None, None, "")
    # 🔴 [HYC-3] 여기까지 오면 **그 종목에 산출 모듈이 없다**(NPB·축구).
    #    "못 쟀다"가 아니라 "잴 수 없다" — ⑥이 분모에서 뺀다.
    return (None, None, UNRUN)


#: 🔴 [ROT-1] 직전 경기. **일정 표에 이미 있다** — 기사에 묻지 않는다.
#   ⚠️ `starts_at <` 로 **킥오프 이전**만 센다. 자기 자신을 세면 전건이
#      confirmed 가 된다.
#   ⚠️ 취소·연기는 뛴 경기가 아니다 — `status` 로 거른다.
# ── [LOAD-2 2026-09-24] 출전 부하 조회 — **원본은 여기 하나다** ─────────
#
# 🔴 종전에는 `tools/backtest_sep.py` 안에만 있었다. 그래서 `play_load` 가
#    **백테스트에서만** 돌고 운영은 5/5 `미실행` 이었다(D61 §②). 자료는
#    있었다 — `batter_appearances` mlb 9,747 · npb 5,292 · kbo 4,599.
# ⚠️ `app/flow/load.py` 에 두지 않는다 — 그 모듈은 스스로 "순수 함수다,
#    DB 0건"이라 적고 있다. 질의는 ⑤가 이미 넷을 갖고 있는 이 자리다.
_APPS_SQL = """
    SELECT b.batter, b.slot, b.team, g.starts_at
      FROM batter_appearances b JOIN games g ON g.id = b.game_id
     WHERE b.sport = $1 AND b.team = $2 AND g.starts_at < $3
       AND g.starts_at >= $3 - ($4 || ' days')::interval
     ORDER BY g.starts_at DESC
"""

_USUAL_SQL = """
    SELECT b.batter, b.slot, g.starts_at
      FROM batter_appearances b JOIN games g ON g.id = b.game_id
     WHERE b.sport = $1 AND b.team = $2 AND g.starts_at < $3
     ORDER BY g.starts_at DESC, b.slot
     LIMIT 200
"""


async def usual_of(pool, sport: str, team: str, at) -> dict:
    """그 경기 **이전** 기록으로 만든 '평소 모습'.

    🔴 주전 판정은 `lineup_diff.usual_from` 이 한다 — 여기서 다시 짓지 않는다.
    ⚠️ `at` 이전만 본다. 백테스트에서 미래를 보지 않기 위한 조건이고,
       운영에서는 킥오프가 `at` 이라 사실상 전부다.
    """
    from app.engine.lineup_diff import usual_from

    rows = [dict(r) for r in await pool.fetch(_USUAL_SQL, sport, team, at)]
    by: dict = {}
    for r in rows:
        by.setdefault(r["starts_at"], []).append(r)
    history = []
    for _ts, group in sorted(by.items(), reverse=True):
        order = [(str(x["batter"]), "") for x in
                 sorted(group, key=lambda x: (x["slot"] or 99))]
        if order:
            history.append(order)
    return usual_from(history)


async def play_rows(pool, sport: str, team: str, at, *, days=None) -> dict:
    """한 팀의 출전 기록 — `{"apps": [...], "usual": {...}}`.

    ⚠️ 창은 `load.window_d` 가 원본이다(사본 금지).
    """
    from app.flow import rules as R

    if days is None:
        days = R.get("load.window_d", 7)
    apps = [dict(r) for r in await pool.fetch(_APPS_SQL, sport, team, at,
                                              str(int(days)))]
    return {"apps": apps, "usual": await usual_of(pool, sport, team, at)}


async def _news_rss_dir(state, ctx) -> dict | None:
    """[NWS-S] **팀별 구글 뉴스**에서 호재·악재 방향을 받는다.

    🔴 **새로 만들지 않는다.** 긁기는 `news_rss.by_side`(구경로가 쓰던 것),
       방향은 `attribution.news_dir_sided` 가 한다. 여기는 잇기만 한다.
    ⚠️ 리그 로케일이 없는 종목(축구 등)은 `news_rss.LOCALE` 이 거른다 —
       여기서 종목 목록을 손으로 적지 않는다(사본 금지).
    ⚠️ 실패·무응답은 `None` 이고 호출부가 종전대로 `미실행`/미상으로 적는다.
    ⚠️ 캐시는 `news_rss` 안에 있다(팀별 TTL) — 슬레이트에서 같은 팀을
       두 번 긁지 않는다.
    """
    from app.collectors import news_rss as NR
    from app.flow.attribution import news_dir_sided

    sport = _sport_code(state)
    league = str(getattr(state, "league", "") or "")
    # 🔴 [NWS-A] 야구는 종목으로, 축구는 **리그로** 로케일이 정해진다.
    #    종목 목록을 손으로 적지 않는다 — `news_rss.locale_for` 가 원본이다.
    if NR.locale_for(sport, league) is None:
        return None
    jg = {"sport": sport, "league": league,
          "home": getattr(state, "home", ""), "away": getattr(state, "away", "")}
    if not (jg["home"] and jg["away"]):
        return None
    try:
        table = await NR.by_side(jg, getattr(ctx, "redis", None))
    except Exception as exc:
        logger.warning("[flow:n05] 팀 뉴스 조회 실패 game=%s: %s",
                       state.game_id, exc)
        return None
    rosters, starters = await _core_members(state, ctx)
    return news_dir_sided(table, rosters=rosters, starters=starters)


async def _core_members(state, ctx) -> tuple:
    """[NWS-C] 쪽별 **핵심 인물** — `(평소 명단, 추가 이름)`.

    사용자 2026-09-24: "무조건 부상이라고 -1을 하면 안된다…기사에 난 인물이
    기존 라인업 **핵심 멤버**인지 확인해야 한다" ·
    "모든 경기에 적용되어야 한다…꼭 야구만 하지 말고"

    🔴 **종목마다 '명단'의 모양이 다르다.** 흐름 밖에서 종목을 거르지 않고
       노드 **안에서** 갈린다(CLAUDE.md §모든 종목).
         야구  평소 타순표(`usual_of`) + **오늘 예고 선발**(투수는 타순에 없다)
         축구  확정 XI(`lineups.batting_order`) — 평소 타순이라는 것이 없다
    🔴 **주전 판정을 여기서 짓지 않는다** — `load.player_weight` 와
       `lineup_diff.usual_from` 이 원본이다(`attribution.core_name_in`).
    ⚠️ 못 읽으면 **빈 것**을 준다. 그러면 뉴스가 확률을 안 움직인다 —
       "모른다"를 "없다"로 바꾸지 않는다.
    """
    rosters: dict = {}
    starters: dict = {}
    if ctx.pool is None:
        return rosters, starters
    sport = _sport_code(state)
    if sport == "soccer":
        rows = await _xi_rows(state, ctx)
        for sd in ("home", "away"):
            names = (_order_by_side(rows) or {}).get(sd) or []
            if names:
                starters[sd] = [str(x) for x in names]
        return rosters, starters
    kick = _kickoff_dt(state.kickoff_utc)
    for sd in ("home", "away"):
        team = getattr(state, sd, "")
        if not team or kick is None:
            continue
        try:
            rosters[sd] = await usual_of(ctx.pool, sport, str(team), kick)
        except Exception as exc:
            logger.warning("[flow:n05] 평소 명단 조회 실패 game=%s %s: %s",
                           state.game_id, sd, exc)
    try:
        row = await ctx.pool.fetchrow(
            "SELECT home_pitcher, away_pitcher FROM games WHERE id = $1",
            int(state.game_id))
    except Exception:
        row = None
    for sd in ("home", "away"):
        who = str((row or {}).get(f"{sd}_pitcher") or "").strip()
        if who:
            starters[sd] = [who]
    return rosters, starters


async def _play_load_of(state, ctx) -> dict | None:
    """양 팀의 출전 기록. 🔴 **배선의 끝** — ⑤가 직접 DB 를 읽는다.

    🔴 못 읽으면 `None` 이고 호출부가 `미실행` 으로 적는다. 0 으로 채우지
       않는다 — "안 봤다"와 "봤는데 없다"는 다른 말이다.
    """
    if ctx.pool is None:
        return None
    sp = _sport_code(state)
    # ⚠️ `batter_appearances` 는 야구뿐이다(축구는 `lineup_history.minutes` 가
    #    전 리그 0건 — `app/flow/load.py` 머리말).
    if sp not in ("mlb", "npb", "kbo"):
        return None
    kick = _kickoff_dt(state.kickoff_utc)
    if kick is None:
        return None
    out: dict = {}
    for sd in ("home", "away"):
        team = getattr(state, sd, "")
        if not team:
            return None
        try:
            out[sd] = await play_rows(ctx.pool, sp, str(team), kick)
        except Exception as exc:
            logger.warning("[flow:n05] 출전 기록 조회 실패 game=%s: %s",
                           state.game_id, exc)
            return None
    return out


_RECENT_SQL = """
    SELECT home, away, starts_at, league
      FROM games
     WHERE sport = $1
       AND $2 IN (home, away)
       AND starts_at < $3::timestamptz
       AND starts_at >= $3::timestamptz - make_interval(hours => $4)
       AND status NOT IN ('cancelled', 'postponed')
     ORDER BY starts_at DESC
"""


async def _recent_match(state, ctx, side: str, *, hours: float | None = None) -> list:
    """창 안에 뛴 경기. 🔴 **없으면 빈 목록**(=봤는데 없다)이고, 못 보면 None."""
    from app.flow import rules as R

    if ctx.pool is None:
        return None
    kick = _kickoff_dt(state.kickoff_utc)
    team = getattr(state, side, "")
    if kick is None or not team:
        return None
    # ⚠️ [LOAD-1] 창을 인자로 받을 수 있게 했다 — 야구 연전은 축구 96h 와
    #    다른 값이다. **안 넘기면 종전 그대로**(축구 rotation_window_h).
    if hours is None:
        try:
            hours = float(R.get("rotation_window_h", 96) or 96)
        except (TypeError, ValueError):
            hours = 96.0
    hours = float(hours)
    try:
        rows = await ctx.pool.fetch(_RECENT_SQL, _sport_code(state), team,
                                    kick, hours)
    except Exception as exc:
        logger.warning("[flow:n05] 직전 경기 조회 실패 game=%s: %s",
                       state.game_id, exc)
        return None
    out = []
    for r in rows:
        opp = r["away"] if r["home"] == team else r["home"]
        when = r["starts_at"]
        gap = (kick - when).total_seconds() / 3600.0 if when else None
        out.append(f"{when:%m-%d} vs {opp}"
                   + (f" ({gap:.0f}시간 전)" if gap is not None else ""))
    return out


def _as_list(raw) -> list:
    """jsonb 칸을 목록으로. ⚠️ asyncpg 가 문자열로 줄 때가 있다."""
    if isinstance(raw, str):
        import json as _j

        try:
            raw = _j.loads(raw)
        except ValueError:
            return []
    return list(raw or [])


def _scratches_of(rows: list, side: str) -> list:
    """[OUT-S] 우리 쪽 결장자. 🔴 **같은 조회**(`_XI_SQL`)를 쓴다 — 경기당
    질의 하나다.

    🔴 **빈 목록은 돌려주지 않는다.** ⑥ 규약상 빈 목록은 `refuted`("봤는데
       없다")인데, transfermarkt 가 빈손인 것과 결장자가 정말 0명인 것을
       우리는 구분할 수 없다. 구분 못 하면 미상이다.
    ⚠️ 상대 쪽 행은 쓰지 않는다 — 상대 결장은 우리에게 **호재**이고, 우리 칸에
       실으면 방향이 뒤집힌다.
    """
    for r in rows:
        if str(r.get("side") or "") != side:
            continue
        names = _as_list(r.get("scratches"))
        if names:
            return names
    return []


def _confirmed_xi(rows: list, side: str) -> dict | None:
    """우리 쪽 **확정** XI 한 벌. 없으면 None.

    🔴 **"예상을 확정으로 취급 금지"**(CLAUDE.md 발송 규율). 예상 명단은
       싣지 않는다 — 실으면 ⑦이 `confirmed` 로 읽고 확률을 움직인다.
    🔴 예상뿐일 때 `None`(=⑥에서 `unknown`)이지 **빈 목록이 아니다.**
       빈 목록은 ⑥ 규약상 `refuted`("봤는데 없다")이고, 핵심 변수가 반증으로
       잡히면 픽이 철회된다. 공식 XI 는 **아직 안 나왔을 뿐**이다.
    ⚠️ 상태의 원본은 `lineups.xi_status_of` 가 적어 둔 `status` 열이다 —
       여기서 다시 판정하지 않는다(사본 금지).
    """
    from app.collectors.lineups import STATUS_CONFIRMED

    for r in rows:
        if str(r.get("side") or "") != side:
            continue
        if str(r.get("status") or "") != STATUS_CONFIRMED:
            continue
        names = r.get("batting_order") or []
        if isinstance(names, str):
            import json as _j

            try:
                names = _j.loads(names)
            except ValueError:
                continue
        if not names:
            continue
        return {"names": list(names), "formation": r.get("starter") or "",
                "source": r.get("source") or "", "at": r.get("captured_at")}
    return None


async def _last3(state, ctx, side: str) -> list:
    """직전 3경기 결과. 🔴 기사에 묻지 않는다 — DB 에 있다(FORKS F-11)."""
    if "last3" in (ctx.inject or {}):
        return list((ctx.inject["last3"] or {}).get(side) or [])
    if ctx.pool is None:
        return []
    team = getattr(state, side, "")
    try:
        from app.engine.pick_ledger import _LAST3_SQL, _last3_line

        rows = await ctx.pool.fetch(_LAST3_SQL, _sport_code(state), team,
                                    _kickoff_dt(state.kickoff_utc))
        return [_last3_line(r, team) for r in rows]
    except Exception as exc:
        logger.warning("[flow:n05] 최근3 조회 실패 game=%s %s: %s",
                       state.game_id, side, exc)
        return []


async def run(state, ctx):
    """⑤ 수집."""
    hyp = (state.n04_hyp or [{}])[0]
    wanted = [v["var"] for v in (hyp.get("vars") or [])]
    if not wanted:
        state.n05_evidence = []
        return state

    # 🔴 드라이런·픽스처 주입구. 운영에서는 비어 있다 — 그때는 아래 수집이 돈다.
    #    ⚠️ 주입값도 **화이트리스트를 통과해야** 한다(목록 밖은 버린다).
    direct = (ctx.inject or {}).get("evidence")
    if direct is not None:
        rows = [dict(e) for e in direct if e.get("var") in wanted]
        rows = [e for e in rows if e.get("raw_excerpt")]
        state.n05_evidence = rows
        logger.info("[flow:n05] game=%s 주입 evidence %d건", state.game_id, len(rows))
        return state

    box = await _extract_box(state, ctx)
    # 🔴 [WIR-2] 주입에만 매달리지 않는다. 운영에서는 `bridge` 가 `model_probs`
    #    하나만 주입해서 이 목록이 **영원히 비어 있었다**(실측: 게이트를 통과한
    #    7경기 전부 evidence=[] · 여섯 변수 전건 unknown).
    absences = await _cache_absences(state, ctx)
    # 🔴 [W2] 로스터는 **한 번만** 읽는다 — 변수마다 다시 물으면 같은 질의가
    #    경기당 여러 번 돈다. 축구는 출장 기록이 없어 빈 dict 이고 정상이다.
    roster = await _roster(state, ctx) if absences else {}
    out: list = []
    # 🔴 [CAP5 2026-09-23] **경기당 상한으로 조사를 끊지 않는다.**
    #    종전에는 `deepsearch_cap.per_game`(5)로 `out` 길이를 세어 끊었는데,
    #    F-17 로 야구가 6변수를 묻게 되자 **언제나 마지막 하나가 잘렸다**
    #    (실측: 4경기 전부 정확히 5행 · 롯데@한화는 `weather` 가 잘림).
    #    끊긴 자리는 `unknown` 이 되어 ⑥의 분모에 들어간다 — "안 봤다"가
    #    아니라 **"못 보게 막았다"**이고, 그건 채점을 거짓으로 만든다.
    #
    #    🔴 바로 아래 BUD-1 주석이 이미 모순을 적고 있었다: "여기서 예산을
    #       차감하지 않는다 — 이 노드에는 **기사 fetch 가 없다**". 예산을
    #       안 쓰는 노드가 예산 상한으로 끊고 있었다.
    #    ⚠️ `Ctx.take_search` 는 그대로 둔다 — 기사 수집이 ⑤에 붙는 날
    #       (STEP 7-4) 그 자리에서 쓰고 경기별 예약도 그때 만든다.
    for var in wanted:
        # 🔴 [BUD-1 / STEP 1-a 2026-09-20] **여기서 예산을 차감하지 않는다.**
        #    종전에는 변수마다 `ctx.take_search(1)` 을 불렀는데, 이 노드에는
        #    **기사 fetch 가 없다** — 바깥 호출이 Redis 읽기(판정 캐시·위성
        #    추출)와 DB 조회뿐이고 httpx/aiohttp/requests 가 0건이다.
        #    기사는 별도 잡 `satellite_15m` 이 긁고 ⑤는 읽기만 한다.
        #    실측 2026-09-20 KBO: 앞 두 경기가 DB 조회로 예산 10 을 다 써서
        #    두산@KT 가 **캐시 결장 3건을 손에 쥐고도** 한 변수도 못 열었다
        #    ("여섯 변수 전부 미상"은 자료가 없어서가 아니라 예산이 없어서였다).
        # ⚠️ `Ctx.take_search` 는 **남겨 둔다.** 기사 수집이 ⑤에 붙을 때
        #    (STEP 7-4) 그 자리에서만 쓰고, 그때 경기별 예약도 함께 만든다.
        # 🔴 [2026-09-18] **선발 축.** 딥서치가 야구에서 가장 큰 단일 변수라고
        #    말한 자리다(선발 교체 = 머니라인 40~60센트 · FORKS F-16).
        #    감지는 이미 있었고(`pipeline.starter_change_notes`) 가설·채점이
        #    그것을 보지 않았다 — WIR-1 과 같은 "만들어 놓고 안 이음"이다.
        if var == "starter_recent3":
            # 🔴 [STR-2] **상대 선발의 최근 3등판**이 이 변수의 본뜻이다.
            #    교체 메모는 다른 사실이라 둘 다 싣는다.
            # 🔴 [UND-1] **양 팀 선발**을 본다. 종전에는 상대만 봐서 ⑪의
            #    언더 조건("양 팀 모두 호재")이 구조적으로 못 섰다(14일 0건).
            by_side = await _starter_recent3(state, ctx)
            if by_side:
                lg = _league_era(state, ctx)
                # 🔴 [ADJ-1] `sides` 는 **악재의 주체**다. 선발이 리그 평균보다
                #    나쁘면 그 팀 악재, 좋으면 호재 — 쪽별로 따로 낸다.
                #    종전에 `{opp: n}` 으로 고정해 잘 던진 선발에도 +3.0 이
                #    붙었다(실측 네 경기 전부).
                # ⚠️ 방향은 `direction.py` 가 원본이다 — 여기서 합치기만 한다.
                d = DIR.merge(*[
                    DIR.starter_direction(rows, league_era=lg, team=side)
                    for side, (_l, _w, _e, rows) in by_side.items()])
                # ⚠️ 원문은 **상대 선발을 앞에** 둔다 — 우리 득점 전망의
                #    주체라 서술에서 먼저 읽혀야 한다(종전 순서 유지).
                opp = "home" if (state.hyp_side or "home") == "away" else "away"
                order = [opp] + [x for x in ("home", "away") if x != opp]
                parts, lines = [], []
                for side in order:
                    if side not in by_side:
                        continue
                    ls, who, era3, _ = by_side[side]
                    lines.extend(ls)
                    parts.append(f"{who} · 최근3 방어율 {era3} · " + " · ".join(ls))
                out.append(_row(var, lines, source="db:pitcher_appearances",
                                excerpt=" || ".join(parts),
                                sides={k: len(v[0]) for k, v in by_side.items()},
                                direction=d))
            notes = await _cache_starter_notes(state, ctx)
            if notes:
                sides: dict = {}
                for n in notes:
                    for ko, en in _SIDE_KR.items():
                        if str(n).startswith(ko):
                            sides[en] = sides.get(en, 0) + 1
                            break
                out.append(_row(var, notes, source="starter_change",
                                excerpt=" · ".join(map(str, notes)),
                                sides=sides))
            continue

        # 🔴 [2026-09-19] **불펜 축.** 핵심 변수인데 소스가 없어 언제나
        #    `unknown` 이었다(실측 0건). `pitcher_appearances` 에 이미 있다.
        if var == "bullpen_3d":
            per_side, raw_side = {}, {}
            for sd in ("home", "away"):
                got, raw = await _bullpen3d(state, ctx, sd)
                if got:
                    per_side[sd], raw_side[sd] = got, raw
            flat = [x for v in per_side.values() for x in v]
            if flat:
                # 🔴 [FIX-1] 쪽별로 따로 판정한 뒤 합친다 — 한쪽만 과소모인
                #    경우와 양쪽 다인 경우를 구분해야 부호가 맞는다.
                d = DIR.merge(*[DIR.bullpen_direction(raw_side.get(sd) or [], team=sd)
                                for sd in ("home", "away") if sd in raw_side])
                out.append(_row(var, flat, source="db:pitcher_appearances",
                                excerpt=" · ".join(flat[:12]),
                                sides={k: len(v) for k, v in per_side.items()},
                                direction=d))
            continue

        # 🔴 [VEN-1] 파크팩터는 **이미 산출돼 있다.** 방향은 붙이지 않는다 —
        #    "타자 구장이 우리에게 유리"는 팀 성향에 달렸고 미검증이다.
        #    ⑦은 방향이 없으면 행을 만들지 않으므로 조정은 0 이고, 바뀌는
        #    것은 "쟀다/못 쟀다"뿐이다.
        if var == "park_factor":
            name, pf, src = await _park_of(state, ctx)
            if src == UNRUN:
                out.append(_row(var, None, source="",
                                excerpt="이 종목은 파크팩터 산출 모듈이 없다 — 미실행",
                                status=UNRUN))
                continue
            if name and pf:
                out.append(_row(var, [f"{name} {float(pf):.3f}"],
                                source=f"db:{src}",
                                excerpt=f"{name} 파크팩터 {float(pf):.3f}"))
            continue

        # 🔴 [LOAD-1 2026-09-23 사용자 지시] **일정 부하 — 연전.**
        #    ⚠️ `_recent_match()` 는 이미 있었다. 축구 `rotation_risk` 가
        #       쓰는데 야구 `travel_backtoback` 은 **한 번도 안 불렀다** —
        #       그래서 "수집 경로가 없다 — 미실행"으로 나갔다. 경로는 있었다.
        if var == "travel_backtoback":
            got = (ctx.inject or {}).get("recent_match")
            if got is None:
                got = {}
                for sd in ("home", "away"):
                    got[sd] = await _recent_match(state, ctx, sd,
                                                  hours=_B2B_HOURS())
            if all(v is None for v in got.values()):
                out.append(_row(var, [], source="", status=UNRUN,
                                excerpt="일정을 못 읽었다 — 미실행"))
                continue
            d = {}
            for sd in ("home", "away"):
                v = got.get(sd)
                d[sd] = -1 if v else 0
            lines = [f"{sd}: {len(got.get(sd) or [])}경기" for sd in ("home", "away")]
            out.append(_row(var, lines, source="db:games",
                            excerpt=" · ".join(lines),
                            direction={**d, "dev": _DEV_FULL(),
                                       "basis": " · ".join(lines)}))
            continue

        # 🔴 [LOAD-1] **출전 부하 — 주전/후보로 무게를 나눈다.**
        #    사용자: "후배선수인지 메인선수인지 확인해서 숫자를 바꿔야 한다"
        #    ⚠️ 주전 판정은 `lineup_diff.usual_from` 이 원본이다(사본 금지).
        if var == "play_load":
            from app.flow import load as _LOAD

            got = (ctx.inject or {}).get("play_load")
            # 🔴 [LOAD-2 2026-09-24] **주입이 없으면 직접 읽는다.** 종전에는
            #    여기서 끝나 운영이 5/5 `미실행` 이었다 — 넣는 곳이
            #    `tools/backtest_sep.py` 하나뿐이었다(D61 §②).
            if not got:
                got = await _play_load_of(state, ctx)
            if not got:
                out.append(_row(var, [], source="", status=UNRUN,
                                excerpt="출전 기록이 없다 — 미실행"))
                continue
            kick = _kickoff_dt(state.kickoff_utc)
            # 🔴 [2026-09-23 사용자 지시] **오늘 선발인 선수의 부하만 센다.**
            #    많이 뛴 선수가 오늘 안 나오면 그 피로는 이 경기에 없다.
            today = (ctx.inject or {}).get("today_order")
            if today is None:
                today = _order_by_side(await _xi_rows(state, ctx))
            bag, d = {}, {}
            for sd in ("home", "away"):
                one = got.get(sd) or {}
                bag[sd] = _LOAD.play_load(one.get("apps"), one.get("usual") or {},
                                          today=(today or {}).get(sd), at=kick)
            if all(v is None for v in bag.values()):
                out.append(_row(var, [], source="", status=UNRUN,
                                excerpt="출전 기록이 없다 — 미실행"))
                continue
            from app.flow import rules as _R

            thr = float(_R.get("load.heavy_score", 3.0))
            # 🔴 [PIPE-4 2026-09-25] **방향 판정을 `direction` 으로 옮겼다.**
            #    종전에는 "더 높은 쪽이 thr 이상이면 −1" 이라 47.3 vs 52.9 처럼
            #    근소해도 ±1.0 만점이 들어갔고, `dev` 도 기준값을 그대로 실어
            #    강도가 언제나 1.0 이었다. 판정 규칙의 원본은 한 곳이다(사본 금지).
            d = DIR.load_direction(score_home=(bag["home"] or {}).get("score"),
                                   score_away=(bag["away"] or {}).get("score"),
                                   thr=thr)
            lines = [f"{sd}: 부하 {(bag[sd] or {}).get('score')}"
                     f"({(bag[sd] or {}).get('n')}경기)" for sd in ("home", "away")]
            out.append(_row(var, lines, source="db:batter_appearances",
                            excerpt=" · ".join(lines), direction=d))
            continue

        # 🔴 [NWS-D 2026-09-23 사용자 지시] **기사의 부상·복귀 소식.**
        #    "부상이나 다른 문제가 있으면 예측에 무조건 좌우되어야 한다"
        #    ②가 제목에서 방향을 이미 정해 뒀다(`move["news_dir"]`) — 여기서는
        #    증거 한 줄로 **옮기기만** 한다. 자료를 다시 긁지 않는다.
        #    🔴 방향이 없으면 **행을 만들지 않는다**(⑥이 unknown 으로 센다).
        #       기사 소스 자체가 없으면 `미실행` 이라 ⑥ 분모에서 빠진다 —
        #       "안 찾았다"와 "찾았는데 없다"는 다른 말이다.
        if var == "news_injury":
            nd = ((state.n02_market or {}).get("move") or {}).get("news_dir")
            src = "news"
            # 🔴 [NWS-S 2026-09-24 사용자 지적] "기존에 rss로 모으는거 있지
            #    않았니?" — 있었다. `news_rss` 가 **팀별 구글 뉴스**를 긁고
            #    구경로(`pipeline`)만 쓰고 있었다. 흐름은 크롤러의 **리그
            #    Bing 검색**만 봤고 그쪽은 기사가 6~9일 전이라 창과 겹치지
            #    않았다(실측 news_dir 8/8 = 0).
            #      크롤러 Bing 리그 검색   6~9일 전
            #      news_rss 팀별 질의      **0.3h ~ 5.6h** (실측 KBO 3경기)
            #    ⚠️ 먼저 ②를 쓰고, 방향이 없을 때만 내려간다 — 종전 경로를
            #       치우지 않는다(배당 이동과 시각을 맞춘 것은 ②뿐이다).
            if not nd or not (nd.get("home") or nd.get("away")):
                got = await _news_rss_dir(state, ctx)
                if got:
                    nd, src = got, "news_rss"
            if not nd:
                out.append(_row(var, [], source="", status=UNRUN,
                                excerpt="기사 소스가 없다 — 미실행"))
                continue
            if not (nd.get("home") or nd.get("away")):
                continue          # 기사는 있었는데 방향이 없다 → 미상
            out.append(_row(var, [nd.get("basis") or ""], source=src,
                            excerpt=nd.get("basis") or "",
                            direction={"home": int(nd.get("home") or 0),
                                       "away": int(nd.get("away") or 0),
                                       # ⚠️ 편차는 ⑦의 강도다. 제목만 보고
                                       #    세기를 가늠할 수 없으니 표의
                                       #    기준값을 그대로 쓴다.
                                       "dev": _DEV_FULL(),
                                       "basis": nd.get("basis") or ""}))
            continue

        # 🔴 [ROT-1] 로테이션 위험은 **일정에서 센다.** 기사·LLM 0.
        #    ⚠️ "쉬어서 유리하다"는 적지 않는다 — 미검증이다. 확인되는 것은
        #       "직전에 뛰었다"(피로)뿐이고, 없으면 방향 없이 빈 목록이다.
        if var == "rotation_risk":
            side = state.hyp_side or "home"
            played = await _recent_match(state, ctx, side)
            if played is not None:
                if played:
                    out.append(_row(var, played, source="db:games",
                                    excerpt=" · ".join(played[:3]),
                                    sides={side: len(played)}, direction=-1))
                else:
                    out.append(_row(var, [], source="db:games",
                                    excerpt="창 안 직전 경기 없음",
                                    sides={side: 0}))
            continue

        # 🔴 [OUT-S] 축구 결장자는 **표에서 읽는다**(transfermarkt →
        #    `lineups.scratches`). 야구는 종전 경로(위성+공식)가 낸다 —
        #    여기로 내려보내지 않는다.
        if var == "lineup_out" and _sport_code(state) == "soccer":
            side = state.hyp_side or "home"
            names = _scratches_of(await _xi_rows(state, ctx), side)
            if names:
                out.append(_row(var, names, source="db:lineups",
                                excerpt=" · ".join(map(str, names[:3])),
                                sides={side: len(names)}, direction=-1))
                continue

        # 🔴 [XI-1] 확정 XI 는 **표에서 읽는다.** 기사·LLM 에 묻지 않는다.
        # ⚠️ 표에서 못 얻으면 `continue` 하지 **않는다** — 아래 추출 경로로
        #    내려가야 HYC-1("못 믿을 카드는 값을 싣지 않고 사유를 남긴다")이
        #    산다. 처음에 여기서 끊었다가 그 계약을 깼다.
        if var == "xi_confirmed":
            side = state.hyp_side or "home"
            got = _confirmed_xi(await _xi_rows(state, ctx), side)
            if got:
                names = got["names"]
                head = " · ".join(map(str, names[:4]))
                out.append(_row(var, names, source="db:lineups",
                                excerpt=f"{got['formation']} {head} 외 "
                                        f"{max(0, len(names) - 4)}명".strip(),
                                sides={side: len(names)}))
                continue

        field = _FROM_EXTRACT.get(var)
        if var in ("form_recent5",) or var == "last3":
            side = state.hyp_side or "home"
            vals = await _last3(state, ctx, side)
            if vals:
                out.append(_row(var, vals, source="db:games",
                                excerpt=" · ".join(map(str, vals)),
                                sides={side: len(vals)}))
            continue

        if field:
            per_side: dict = {}
            teams = (box.get("teams") or {})
            # 🔴 [HYC-1 2026-09-20] **못 믿을 카드는 값을 싣지 않는다.**
            #    사유는 버리지 않는다 — 아래에서 `untrusted_reason` 으로 남겨
            #    "안 찾았다"와 "찾았는데 검증할 수 없다"를 구분한다.
            # ⚠️ **카드가 없는 것**과 **카드를 못 믿는 것**은 다르다. 없는 것은
            #    종전 그대로 조용히 빈손이고(그래야 공식 0명 행 CNF-2 가 산다),
            #    있는데 검증이 안 되는 것만 사유를 남긴다.
            untrusted: dict = {}
            _pit: list = []
            _bat: list = list(absences or [])
            for side in ("home", "away"):
                card = teams.get(side)
                if not card:
                    continue
                ok, why = card_trust(box, card)
                if not ok:
                    if why:
                        untrusted[side] = why
                    continue
                # 🔴 [HYC-2 2026-09-23] **예상 XI 를 확정으로 취급하지 않는다.**
                #    상자의 `xi_status` 가 `predicted`·`lastStarting11` 이면
                #    오늘 확정 XI 가 아니다 — 값을 싣지 않고 사유를 남긴다.
                #    ⚠️ 확정 판정의 원본은 `scout_config.xi_is_confirmed` 다
                #       (사본 금지). `lineups` 표 경로는 XI-1 이 이미 막는다.
                if var == "xi_confirmed":
                    from app.engine.scout_config import xi_is_confirmed

                    st_xi = card.get("xi_status")
                    if not xi_is_confirmed(st_xi):
                        untrusted[side] = (f"확정 XI 가 아니다(xi_status="
                                           f"{st_xi or '없음'})")
                        continue
                v = (teams.get(side) or {}).get(field)
                if v:
                    per_side[side] = list(v) if isinstance(v, (list, tuple)) else [v]
            # 🔴 공식 결장을 **합친다**(FORKS F-2: 충돌 시 공식이 이긴다).
            # ⚠️ [HYC-1] 공식 결장은 **판정 캐시**에서 온다 — 상자 카드가 못
            #    믿을 것이어도 그대로 센다. 상자를 막느라 공식까지 버리면
            #    그것이 더 큰 결함이다(반대 위험 · 계약 테스트가 잠근다).
            if var in ("lineup_out", "xi_confirmed") and absences:
                # 🔴 [PIPE-5 2026-09-25] **투수 결장은 타순 결장이 아니다.**
                #    `from_injured` 는 IL 투수도 결장 문장으로 만든다. 그것을
                #    `lineup_out` 에 세면 "결장 18명"(실측 TB@NYY, 9건이 투수)
                #    이 서술·내보내기로 나가고, ⑥이 목록 길이로 confirmed 를
                #    만든다. 투수는 `starter_recent3`·`bullpen_3d` 가 본다.
                #    ⚠️ 버리지 않는다 — `pitcher_il` 로 따로 남긴다.
                #    ⚠️ 판정은 `absences.is_pitcher_line` 이 원본이다(사본 금지).
                #    ⚠️ 바깥 `absences` 를 다시 묶지 않는다 — 다음 변수가 본다.
                _pit = [x for x in absences if _ABS.is_pitcher_line(str(x))]
                _bat = [x for x in absences if not _ABS.is_pitcher_line(str(x))]
                if _pit:
                    logger.info("[flow:n05] game=%s %s — 투수 결장 %d건을 "
                                "lineup_out 에서 뺐다", state.game_id, var, len(_pit))
                h_out, a_out = _split(state, _bat)
                # 🔴 [W2 2026-09-21] **그 팀 선수가 아닌 이름은 뺀다.**
                #    판정은 `performance.filter_by_roster` 한 곳이 한다 —
                #    이름이 **정확히 한 팀**으로만 이어질 때만 거른다.
                #    ⚠️ 동명이인(박건우 NC/롯데)은 건드리지 않는다. 이름으로
                #       지우면 진짜 그 팀 선수가 사라진다.
                #    ⚠️ 로스터가 비면(축구·자료 없음) 아무것도 걸러지지 않는다.
                for side, extra in (("home", h_out), ("away", a_out)):
                    if not extra:
                        continue
                    kept, cut = filter_by_roster(
                        extra, team=getattr(state, side, ""), roster=roster)
                    if cut:
                        logger.info("[flow:n05] game=%s %s 결장 %d명 제외 — %s",
                                    state.game_id, side, len(cut),
                                    " · ".join(f"{c['name']}({c['owner']})"
                                               for c in cut))
                    if kept:
                        per_side[side] = list(dict.fromkeys(
                            (per_side.get(side) or []) + kept))
            got = [x for v in per_side.values() for x in v]
            # 🔴 [HYC-1 2026-09-20] **검증 불가를 "없다"로 만들지 않는다.**
            #    믿을 수 있는 값이 하나도 없고 막힌 이유가 있으면 그 사유를
            #    실은 행을 남긴다 — `value=None` 이므로 ⑥은 `_judge` 의 기존
            #    규칙 그대로 `unknown` 으로 읽는다(채점 쪽에 조건을 다시 적지
            #    않는다 · 사본 금지).
            # ⚠️ 아래 CNF-2 의 "확정적으로 0명"보다 **먼저** 본다. 못 믿을
            #    카드를 지나서 빈손이 된 것을 "없음이 확인됐다"로 적으면
            #    검증 실패가 반증으로 둔갑한다.
            if not got and untrusted:
                why = " · ".join(f"{sd}: {msg}" for sd, msg in untrusted.items())
                out.append(_row(var, None, source="satellite",
                                excerpt=f"추출 카드를 쓰지 못했다 — {why}",
                                untrusted_reason=why))
                logger.info("[flow:n05] game=%s %s — 카드 신뢰 불가 (%s)",
                            state.game_id, var, why)
                continue
            # 🔴 [CNF-2 2026-09-20] **"찾아봤는데 없다"를 남긴다.** 종전에는
            #    값이 없으면 행 자체를 안 만들었고, 그래서 ⑥의 `refuted` 가
            #    구조적으로 **불가능**했다(실측: 최근 2h 반증 0건 · 미상 496).
            # ⚠️ 모름을 반증으로 둔갑시키지 않는다 — 결장 수집이 **아예 안
            #    돌았으면**(absences 0건) 행을 만들지 않는다. 소스가 응답했고
            #    (1건 이상) 이 경기 두 팀 몫이 0명일 때만 "확정적으로 0명"이다.
            if not got and var == "lineup_out" and absences:
                out.append(_row(var, [], source="satellite+official",
                                pitcher_il=_pit,
                                excerpt=f"결장 수집 {len(_bat)}건 조회(투수 {len(_pit)}건 제외) · "
                                        "이 경기 두 팀 해당 0명",
                                sides={},
                                direction=DIR.merge(
                                    *[DIR.lineup_direction(excluded=0, confirmed=True,
                                                           team=sd)
                                      for sd in ("home", "away")])))
                continue
            if got:
                # 🔴 [FIX-1] `lineup_out` 의 방향은 **확정 타순에서 빠진 수**로
                #    정한다. IL 목록 길이가 아니다 — 근거 표지의 원본은
                #    `absences.classify` 이고 여기서 정규식을 새로 짓지 않는다.
                # ⚠️ `confirmed` 를 **라인업 표지의 유무**로 대신한다. 타순 확정
                #    여부를 그대로 담은 칸이 이 경로에 없기 때문이다. 확정인데
                #    제외자가 0명이면 "미확정"으로 적히지만 **부호는 둘 다 0**
                #    이라 판정은 같다 — 라벨만 보수적으로 나간다.
                d = None
                if var == "lineup_out":
                    d = DIR.merge(*[
                        DIR.lineup_direction(
                            excluded=sum(1 for x in (per_side.get(sd) or [])
                                         if _ABS.classify(str(x)) == _ABS.BASIS_LINEUP),
                            confirmed=any(_ABS.classify(str(x)) == _ABS.BASIS_LINEUP
                                          for x in (per_side.get(sd) or [])),
                            team=sd)
                        for sd in ("home", "away") if per_side.get(sd)])
                out.append(_row(var, got, source="satellite+official",
                                pitcher_il=_pit,
                                excerpt=" · ".join(map(str, got)),
                                sides={k: len(v) for k, v in per_side.items()},
                                direction=d))
            continue

        # 그 밖의 변수는 아직 소스가 없다. **지어내지 않는다** — 없으면 없는 것이다.
        # 🔴 [HYC-3] 다만 **"안 봤다"와 "볼 방법이 없다"는 다르다.** 여기까지
        #    내려온 변수는 ⑤에 분기가 **아예 없는** 것이라 미상이 아니라
        #    미실행이다. ⑥이 이것을 분모에서 뺀다.
        #    ⚠️ 목록을 어디에도 적지 않는다 — 못 찾는 것을 아는 쪽이 여기다.
        logger.debug("[flow:n05] game=%s var=%s 소스 없음", state.game_id, var)
        out.append(_row(var, None, source="",
                        excerpt="이 변수는 아직 수집 경로가 없다 — 미실행",
                        status=UNRUN))

    # 🔴 원문 없는 것은 버린다.
    out = [e for e in out if e.get("raw_excerpt")]
    state.n05_evidence = out
    logger.info("[flow:n05] game=%s 요청 %d개 → evidence %d건",
                state.game_id, len(wanted), len(out))
    return state
