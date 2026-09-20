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
from app.flow import direction as DIR

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


def _row(var: str, value, *, source: str, url: str = "", excerpt: str = "",
         sides: dict | None = None, direction: dict | None = None,
         untrusted_reason: str = "") -> dict:
    """증거 한 줄. 🔴 [FIX-1] `direction` 이 **부호의 원본**이다 —
    `sides`(항목 수)는 표시용으로만 남는다(⑦이 더 이상 읽지 않는다)."""
    return {"var": var, "value": value, "source": source, "source_url": url,
            "raw_excerpt": excerpt, "sides": sides or {},
            "direction": direction or {}, "fetched_at": None,
            # 🔴 [HYC-1] 비어 있으면 믿을 수 있는 카드다. 차 있으면 **왜 못
            #    믿는지**가 남는다 — 그래야 "안 찾았다"와 구분된다.
            "untrusted_reason": untrusted_reason}


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
    return (state.league or state.sport or "").lower()


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


def starter_side_of(*, era3, league_era, opp: str) -> dict:
    """상대 선발 최근 방어율 → **악재가 어느 쪽인가**.

    🔴 `sides` 는 "이 사실이 누구 얘기인가"가 아니라 **"악재의 주체가 누구인가"**
       다. ⑦(`n07._direction`)이 그 뜻으로 읽는다 — 상대 악재면 우리에게 유리.
       ⚠️ 이것을 `{opp: n}` 으로 고정했더니 잘 던진 선발과 무너진 선발에 같은
          `+3.0` 이 붙었다(실측 2026-09-20, 네 경기 전부).
    🔴 못 구하면 **빈 dict** 다. `_direction` 이 보수적으로 불리하게 읽는다 —
       유리하게 지어내지 않는다.
    """
    if era3 is None or league_era is None:
        return {}
    mine = "away" if opp == "home" else "home"
    return {opp: 1} if float(era3) > float(league_era) else {mine: 1}


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
    """**상대** 선발. 🔴 픽이 원정이면 홈 선발이 우리를 막는 쪽이다."""
    opp = "home" if (state.pick_side or "home") == "away" else "away"
    return (starters or {}).get(opp) or None


async def _starter_recent3(state, ctx) -> tuple:
    """상대 선발의 최근 3등판. 반환 `(줄 목록, 투수명)`.

    🔴 **교체 메모와 다른 사실이다.** 선발이 안 바뀌어도 그 선발이 최근 어떻게
       던졌는지는 우리 득점 전망을 바꾼다. 종전에는 교체가 없으면 증거가 0이라
       이 변수가 늘 `unknown` 이었다.
    ⚠️ 유불리는 여기서 정하지 않는다 — ⑦의 몫이다. 사실만 싣는다.
    """
    inj = (ctx.inject or {})
    starters = inj.get("starters")
    if starters is None:
        if ctx.pool is None:
            return [], None, None, []
        try:
            row = await ctx.pool.fetchrow(
                "SELECT home_pitcher, away_pitcher FROM games WHERE id = $1",
                int(state.game_id))
        except Exception as exc:
            logger.warning("[flow:n05] 선발 조회 실패 game=%s: %s", state.game_id, exc)
            return [], None, None, []
        starters = {"home": (row or {}).get("home_pitcher"),
                    "away": (row or {}).get("away_pitcher")}
    who = opp_starter_of(state, starters)
    ko = _kickoff_dt(state.kickoff_utc)
    if not who or ctx.pool is None or ko is None:
        return [], who, None, []
    try:
        rows = await ctx.pool.fetch(_STARTER3_SQL, who, ko)
    except Exception as exc:
        logger.warning("[flow:n05] 선발 최근3 조회 실패 game=%s %s: %s",
                       state.game_id, who, exc)
        return [], who, None, []
    return ([f"{r['d']:%m-%d} vs {r['opponent']} "
             f"{float(r['innings'] or 0):.1f}이닝 {r['er']}자책 {r['k']}K"
             for r in rows], who, era_of_rows(rows), [dict(r) for r in rows])


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
    out: list = []
    per_game_cap = 0
    try:
        from app.flow import rules as R

        per_game_cap = int(R.get("deepsearch_cap.per_game", 5) or 5)
    except Exception:
        per_game_cap = 5

    for var in wanted:
        if len(out) >= per_game_cap:
            logger.info("[flow:n05] game=%s 경기당 상한 %d 도달 — 나머지는 미상",
                        state.game_id, per_game_cap)
            break
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
            lines, who, era3, raw_rows = await _starter_recent3(state, ctx)
            if lines:
                opp = "home" if (state.pick_side or "home") == "away" else "away"
                d = DIR.starter_direction(raw_rows, league_era=_league_era(state, ctx),
                                          team=opp)
                # 🔴 [ADJ-1] `sides` 는 **악재의 주체**다. 상대 선발이 리그 평균
                #    보다 나쁘면 상대 악재(우리 유리), 좋으면 우리 악재.
                #    종전에 `{opp: n}` 으로 고정해 잘 던진 선발에도 +3.0 이
                #    붙었다(실측 네 경기 전부).
                out.append(_row(var, lines, source="db:pitcher_appearances",
                                excerpt=f"{who} · 최근3 방어율 {era3} · "
                                        + " · ".join(lines),
                                sides={opp: len(lines)}, direction=d))
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

        field = _FROM_EXTRACT.get(var)
        if var in ("form_recent5",) or var == "last3":
            side = state.pick_side or "home"
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
            for side in ("home", "away"):
                card = teams.get(side)
                if not card:
                    continue
                ok, why = card_trust(box, card)
                if not ok:
                    if why:
                        untrusted[side] = why
                    continue
                v = (teams.get(side) or {}).get(field)
                if v:
                    per_side[side] = list(v) if isinstance(v, (list, tuple)) else [v]
            # 🔴 공식 결장을 **합친다**(FORKS F-2: 충돌 시 공식이 이긴다).
            # ⚠️ [HYC-1] 공식 결장은 **판정 캐시**에서 온다 — 상자 카드가 못
            #    믿을 것이어도 그대로 센다. 상자를 막느라 공식까지 버리면
            #    그것이 더 큰 결함이다(반대 위험 · 계약 테스트가 잠근다).
            if var in ("lineup_out", "xi_confirmed") and absences:
                h_out, a_out = _split(state, absences)
                for side, extra in (("home", h_out), ("away", a_out)):
                    if extra:
                        per_side[side] = list(dict.fromkeys(
                            (per_side.get(side) or []) + extra))
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
                                excerpt=f"결장 수집 {len(absences)}건 조회 · "
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
                                excerpt=" · ".join(map(str, got)),
                                sides={k: len(v) for k, v in per_side.items()},
                                direction=d))
            continue

        # 그 밖의 변수는 아직 소스가 없다. **지어내지 않는다** — 없으면 없는 것이다.
        logger.debug("[flow:n05] game=%s var=%s 소스 없음", state.game_id, var)

    # 🔴 원문 없는 것은 버린다.
    out = [e for e in out if e.get("raw_excerpt")]
    state.n05_evidence = out
    logger.info("[flow:n05] game=%s 요청 %d개 → evidence %d건",
                state.game_id, len(wanted), len(out))
    return state
