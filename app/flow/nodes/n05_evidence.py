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


def _row(var: str, value, *, source: str, url: str = "", excerpt: str = "",
         sides: dict | None = None) -> dict:
    """evidence 한 줄.

    🔴 `sides` 는 **어느 팀 이야기인가**다. ⑦ 조정의 부호가 여기서 나온다 —
       우리 픽 쪽 악재는 불리(−), 상대 쪽 악재는 유리(+)다. 이 칸이 없으면
       부호를 한쪽으로 고정하게 되고, 그러면 근거와 반대로 확률이 움직인다.
    """
    return {"var": var, "value": value, "source": source, "source_url": url,
            "raw_excerpt": str(excerpt or "")[:_MAX_EXCERPT],
            "sides": sides or {}, "fetched_at": None}


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
    """위성 추출 `{side: {칸: 값}}`. 없으면 빈 dict."""
    if "extract" in (ctx.inject or {}):
        return dict(ctx.inject["extract"] or {})
    if ctx.redis is None:
        return {}
    try:
        from app.collectors.satellite import read_extract

        got = await read_extract(ctx.redis, _sport_code(state), state.game_id)
        return (got or {}).get("teams") or {}
    except Exception as exc:
        logger.info("[flow:n05] 위성 추출 없음 game=%s: %s", state.game_id, exc)
        return {}


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
            return [], None, None
        try:
            row = await ctx.pool.fetchrow(
                "SELECT home_pitcher, away_pitcher FROM games WHERE id = $1",
                int(state.game_id))
        except Exception as exc:
            logger.warning("[flow:n05] 선발 조회 실패 game=%s: %s", state.game_id, exc)
            return [], None, None
        starters = {"home": (row or {}).get("home_pitcher"),
                    "away": (row or {}).get("away_pitcher")}
    who = opp_starter_of(state, starters)
    ko = _kickoff_dt(state.kickoff_utc)
    if not who or ctx.pool is None or ko is None:
        return [], who, None
    try:
        rows = await ctx.pool.fetch(_STARTER3_SQL, who, ko)
    except Exception as exc:
        logger.warning("[flow:n05] 선발 최근3 조회 실패 game=%s %s: %s",
                       state.game_id, who, exc)
        return [], who, None
    return ([f"{r['d']:%m-%d} vs {r['opponent']} "
             f"{float(r['innings'] or 0):.1f}이닝 {r['er']}자책 {r['k']}K"
             for r in rows], who, era_of_rows(rows))


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
        return list((ctx.inject["bullpen"] or {}).get(side) or [])
    ko = _kickoff_dt(state.kickoff_utc)
    if ctx.pool is None or ko is None:
        return []          # 시각을 모르면 3일 창을 만들 수 없다 — 지어내지 않는다
    team = getattr(state, side, "")
    try:
        rows = await ctx.pool.fetch(_BULLPEN_SQL, team, ko)
    except Exception as exc:
        # 🔴 warning 이다. info 로 두면 정상 로그에 묻히고, 빈 목록이
        #    "자료 없음"과 구분되지 않는다(실측: 그래서 몇 주를 몰랐다).
        logger.warning("[flow:n05] 불펜 조회 실패 game=%s %s: %s",
                       state.game_id, side, exc)
        return []
    return [f"{r['d']:%m-%d} {r['pitcher']} {float(r['innings'] or 0):.1f}이닝"
            for r in rows]


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
        if not ctx.take_search(1):
            logger.info("[flow:n05] game=%s 슬레이트 예산 소진 — 나머지는 미상",
                        state.game_id)
            break

        # 🔴 [2026-09-18] **선발 축.** 딥서치가 야구에서 가장 큰 단일 변수라고
        #    말한 자리다(선발 교체 = 머니라인 40~60센트 · FORKS F-16).
        #    감지는 이미 있었고(`pipeline.starter_change_notes`) 가설·채점이
        #    그것을 보지 않았다 — WIR-1 과 같은 "만들어 놓고 안 이음"이다.
        if var == "starter_recent3":
            # 🔴 [STR-2] **상대 선발의 최근 3등판**이 이 변수의 본뜻이다.
            #    교체 메모는 다른 사실이라 둘 다 싣는다.
            lines, who, era3 = await _starter_recent3(state, ctx)
            if lines:
                opp = "home" if (state.pick_side or "home") == "away" else "away"
                # 🔴 [ADJ-1] `sides` 는 **악재의 주체**다. 상대 선발이 리그 평균
                #    보다 나쁘면 상대 악재(우리 유리), 좋으면 우리 악재.
                #    종전에 `{opp: n}` 으로 고정해 잘 던진 선발에도 +3.0 이
                #    붙었다(실측 네 경기 전부).
                out.append(_row(var, lines, source="db:pitcher_appearances",
                                excerpt=f"{who} · 최근3 방어율 {era3} · "
                                        + " · ".join(lines),
                                sides=starter_side_of(
                                    era3=era3, league_era=_league_era(state, ctx),
                                    opp=opp)))
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
            per_side = {}
            for sd in ("home", "away"):
                got = await _bullpen3d(state, ctx, sd)
                if got:
                    per_side[sd] = got
            flat = [x for v in per_side.values() for x in v]
            if flat:
                out.append(_row(var, flat, source="db:pitcher_appearances",
                                excerpt=" · ".join(flat[:12]),
                                sides={k: len(v) for k, v in per_side.items()}))
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
            for side in ("home", "away"):
                v = (box.get(side) or {}).get(field)
                if v:
                    per_side[side] = list(v) if isinstance(v, (list, tuple)) else [v]
            # 🔴 공식 결장을 **합친다**(FORKS F-2: 충돌 시 공식이 이긴다).
            if var in ("lineup_out", "xi_confirmed") and absences:
                h_out, a_out = _split(state, absences)
                for side, extra in (("home", h_out), ("away", a_out)):
                    if extra:
                        per_side[side] = list(dict.fromkeys(
                            (per_side.get(side) or []) + extra))
            got = [x for v in per_side.values() for x in v]
            if got:
                out.append(_row(var, got, source="satellite+official",
                                excerpt=" · ".join(map(str, got)),
                                sides={k: len(v) for k, v in per_side.items()}))
            continue

        # 그 밖의 변수는 아직 소스가 없다. **지어내지 않는다** — 없으면 없는 것이다.
        logger.debug("[flow:n05] game=%s var=%s 소스 없음", state.game_id, var)

    # 🔴 원문 없는 것은 버린다.
    out = [e for e in out if e.get("raw_excerpt")]
    state.n05_evidence = out
    logger.info("[flow:n05] game=%s 요청 %d개 → evidence %d건",
                state.game_id, len(wanted), len(out))
    return state
