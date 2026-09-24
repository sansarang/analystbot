"""[v1.4 STEP 13] 운영 경로 다리 — **스케줄러가 새 파이프라인을 부르는 자리.**

🔴 STEP 13 을 처음 붙일 때 기존 발송에 **배타 가드만** 걸고 `run_game` 호출을
   잇지 않았다. 그러면 `PIPELINE_V14=true` 가 "새 경로를 켠다"가 아니라
   "카드를 끈다"가 된다 — 관측할 것이 없다. 이 파일이 그 구멍을 메운다.

🔴 **기존 판정을 건드리지 않는다.** 새 경로는 같은 슬레이트를 **따로** 돌고
   자기 상태(`analysis_runs`)만 남긴다. 발송은 `PIPELINE_V14_SEND` 가 가른다.
⚠️ 한 경기 실패가 나머지를 막지 않는다 — 경기별 try 로 감싼다.
⚠️ 예산은 슬레이트 단위로 **한 번** 만들어 경기마다 차감한다(§3 상한).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date

from app.flow import watch as WATCH

logger = logging.getLogger(__name__)


def _sport_of(row: dict) -> str:
    """리그 코드 → `analysis_state.sport`(baseball|soccer) 규약."""
    sp = (row.get("sport") or "").lower()
    return "soccer" if sp == "soccer" else "baseball"


#: 우리 득점 분포 확률. 🔴 **원본은 `scoring.game_distribution`** 이고
#  `pipeline.py:4030` 이 원장에 싣는다 — 여기서는 **읽기만** 한다(재계산 금지).
#  ⚠️ 실측 2026-09-19: 이 칸이 **전건 NULL** 이다. 판정이 실패하면 그 뒤의 λ
#     산출 블록 자체가 안 돌기 때문이다(`lambda_missing` 도 None 이었다).
#     즉 LLM 사슬이 살아야 이 값이 찬다 — 배선은 그때를 위해 먼저 해 둔다.
_MODEL_SQL = """
    SELECT game_id, model_probs
      FROM pick_ledger
     WHERE is_final AND model_probs IS NOT NULL
       AND game_id = ANY($1::bigint[])
"""


#: 오늘 슬레이트. 🔴 **위성과 같은 조건**이다(`satellite._DUE_SQL`) — 그쪽이
#  원본이고 여기서는 같은 규칙을 쓴다: 예정 · 앞으로 N시간 안에 시작.
_SLATE_SQL = """
    SELECT id, sport, league, home, away, starts_at,
           -- 🔴 [LAM-2 2026-09-24] **선발 이름이 없으면 억제력 항이 통째로
           --    빠진다.** 실측: research.home_pitcher = None → λ 가 타선만으로
           --    선다. 이 칸은 D61-2 가 크롤러에서 채운다.
           home_pitcher, away_pitcher
      FROM games
     WHERE status = 'scheduled'
       AND starts_at BETWEEN now() AND now() + make_interval(hours => $1)
     ORDER BY starts_at
"""


#: [ELO-1] 사전값 레이팅을 만들 수 있는 종목. 🔴 축구는 뺐다 —
#  `team_elo.refresh` 는 `WHERE sport = $1` 로 긁는데 축구 캐시 키는 **리그
#  코드**라 종목으로 긁으면 리그 간 비교가 된다. `team_elo` 머리말이 금지한
#  것이다("리그 안에서만 의미가 있다"). 축구는 표본부터 재야 하고 별건이다.
ELO_SPORTS = ("mlb", "kbo", "npb")


#: [ELO-S] 캐시가 몇 경기로 만들어졌는지 대조할 DB 쪽 개수.
#  🔴 **조건이 `team_elo.refresh` 의 조회와 같아야** 한다 — 한쪽만 바뀌면
#     대조가 영원히 어긋나 매 슬레이트 재계산하거나(느슨) 낡은 값을 통과시킨다
#     (빡빡). `team_elo` 는 SQL 을 함수 안에 인라인으로 갖고 있어 읽어올 상수가
#     없다. 그래서 **사본이고**, 계약(`test_elos_freshness`)이 두 조건을 대조해
#     잠근다 — 사본을 남기려면 그것을 지키는 계약이 함께 있어야 한다.
_ELO_COUNT_SQL = """
    SELECT count(*) AS n FROM games
     WHERE sport = $1 AND status = 'final'
       AND home_score IS NOT NULL AND away_score IS NOT NULL
"""


def _cached_matches(got) -> int:
    """캐시된 레이팅이 **몇 경기**로 만들어졌나.

    `경기수` 는 팀당 출전 수라 합의 절반이 경기 수다.
    ⚠️ `MIN_GAMES` 미만으로 빠진 팀이 있으면 **작게** 나온다 — 시즌 초에는
       매 슬레이트 재계산이 되는데, 재계산은 조회 1회 + 메모리 replay 라
       그 편이 낡은 값을 쓰는 것보다 싸다.
    """
    n = 0
    for v in (got or {}).values():
        if isinstance(v, dict):
            try:
                n += int(v.get("경기수") or 0)
            except (TypeError, ValueError):
                continue
    return n // 2


async def ensure_elo(pool, redis, sport: str, date: str, *, refresh=None) -> bool:
    """그 (종목, 날짜) 레이팅이 **오늘 자료로** 캐시에 있게 한다.

    🔴 **슬레이트 앞에서 한 번** 부른다. 경기마다 부르면 재계산이 36배다.
    🔴 `team_elo` 에는 전용 갱신 잡이 없다 — 쓰는 곳이 옛 파이프라인의 게으른
       폴백 하나뿐인데(`app/pipeline.py:2915`) `PIPELINE_V14` 가 그 경로를
       지나친다. 그래서 새 경로가 같은 일을 해야 한다.

    🔴 [ELO-S 2026-09-23] **"있으면 쓴다"가 결함이었다.** 키가 `elo:{종목}:
       {날짜}` 인데 프리페치가 **내일 날짜를 하루 먼저** 만든다(실측:
       `elo:kbo:2026-09-24` 가 09-23 에 이미 있었다). 그러면 다음 날 이 함수가
       그것을 찾아 통과시켜 **어제 자료로 만든 레이팅**을 판정에 쓴다.
       ```
       실측 2026-09-23  elo:kbo:2026-09-23  팀당 53~56경기  ← 판정이 쓴 것
                        DB sport='kbo' 종료  팀당 93경기
       ```
       그래서 **캐시가 몇 경기로 만들어졌는지**를 DB 개수와 대조하고, 모자라면
       다시 만든다. 같으면 종전처럼 재계산하지 않는다.

    ⚠️ 풀이 없으면 대조할 수 없다 — 그때는 종전대로 "있으면 쓴다"다
       (드라이런·테스트에 DB 가 없다).
    ⚠️ 다시 만들다 실패해도 **있던 값을 버리지 않는다** — 낡아도 없느니 낫다.
    """
    if redis is None:
        return False
    try:
        from app.models import team_elo as TE

        got = await TE.load(redis, sport, date)
        if pool is None:
            return bool(got)
        fresh = True
        if got:
            try:
                row = await pool.fetchrow(_ELO_COUNT_SQL, sport)
                have = int((row or {}).get("n") or 0)
                fresh = _cached_matches(got) >= have
                if not fresh:
                    logger.info("[flow] elo 낡음 %s %s — 캐시 %d경기 < DB %d경기, 다시 만든다",
                                sport, date, _cached_matches(got), have)
            except Exception as exc:
                logger.warning("[flow] elo 신선도 대조 실패 %s: %s", sport, exc)
                fresh = True
        if got and fresh:
            return True
        fn = refresh or TE.refresh
        made = await fn(pool, redis, sport, date)
        return bool(made) or bool(got)
    except Exception as exc:
        logger.warning("[flow] elo 보장 실패 %s %s: %s", sport, date, exc)
        return False


async def ensure_soccer_elo(redis, league_days, *, pool=None) -> dict:
    """[SELO-1] 축구 리그별 레이팅을 캐시에 있게 한다. 반환 `{리그: 팀 수}`.

    🔴 **야구와 같은 자리**(`elo:{리그}:{날짜}`)에 싣는다 — `n01_prior` 가 이미
       그 키를 읽고 축구 3-way 분기도 갖고 있다. 읽는 쪽을 고치지 않는다.
    🔴 레이팅 원본은 `soccer_elo`(football-data.co.uk CSV 피팅)다.
       ⚠️ ClubElo API 는 **죽어 있다**(전 엔드포인트 502 · Fixtures
          deactivated · 실측 2026-09-20). 자체 Elo 는 표본이 팀당 2.5~5.1
          경기라 진폭이 안 난다. 남은 하나가 이것이다 → FORKS F-21.
    ⚠️ 이미 있는 (리그,날짜) 는 다시 만들지 않는다 — 주 1회 피팅이라 하루 안에
       값이 바뀌지 않는다.
    ⚠️ 실패해도 슬레이트를 멈추지 않는다. 없으면 그 리그는 사전값없음 경로다.
    """
    if redis is None:
        return {}
    out: dict = {}
    try:
        from app.models import soccer_elo as SE
        from app.models import team_elo as TE

        todo: dict = {}
        for lg, day in sorted(league_days or []):
            if await TE.load(redis, TE.code_for(lg), day):
                continue
            todo.setdefault(day, []).append(lg)
        for day, lgs in sorted(todo.items()):
            # 🔴 [ELO-N 2026-09-22] **pool 을 넘긴다.** 그래야 대조표에 없는
            #    팀을 DB 표기로 찾아 정규화 매칭을 할 수 있다 — 종전에는 그
            #    팀들이 통째로 빠져 축구 45경기 중 33건이 "사전값이 없다 —
            #    보드 고정"으로 멈췄다.
            got = await SE.publish_ratings(redis, lgs, day, pool=pool)
            out.update(got)
        if out:
            logger.info("[flow] 축구 elo 보장 — %s", out)
        elif todo:
            logger.info("[flow] 축구 elo 보장 — 대조 가능한 리그 0 (%s)",
                        sorted({lg for lgs in todo.values() for lg in lgs}))
    except Exception as exc:
        logger.warning("[flow] 축구 elo 보장 실패: %s", exc)
    return out


#: 선발 교체 메모의 표지. 🔴 `lineups.py` 가 `f"{side} 선발 변경: A → B"` 로
#  만든다 — 그 문구가 원본이고 여기서 새로 짓지 않는다.
STARTER_CHANGE_MARK = "선발 변경"


def rejudge_signals_of(cg: dict | None) -> dict:
    """판정 캐시 한 경기 → ⑩이 읽는 신호.

    🔴 `pipeline.starter_changed` 를 **쓰지 않는다.** 그 칸의 정의는
       `lineup_status == "conflict"` 이고 그건 *소스 불일치*이지 선발 교체가
       아니다. ⑩ 머리말은 트리거가 "`starter_change_notes` 가 낸 줄"이라고
       적고 있으므로 그 줄을 본다.
       ⚠️ 저 칸은 `deep.needs_refresh` 가 쓰고 있어 건드리지 않는다.
    ⚠️ `lineup_just_confirmed` 는 `lineup_confirmed_at` 에 의존한다 —
       LIN-1 전에는 KBO·NPB 가 그 칸을 안 적어 구조적으로 항상 False 였다.
    """
    cg = cg or {}
    notes = cg.get("lineup_notes") or []
    if isinstance(notes, str):
        notes = [notes]
    return {
        "lineup_confirmed": bool(cg.get("lineup_just_confirmed")),
        "starter_changed": any(STARTER_CHANGE_MARK in str(n) for n in notes),
    }


#: 🔴 [VAL-1 2026-09-23 사용자 지시 "11번 풀어라"] 한 슬레이트의 배당을
#   **한 번에** 읽는다 — 경기마다 물으면 질의가 N배가 된다.
_LINES_SQL = """
    SELECT o.game_id, o.market, o.side, o.line, o.odds
      FROM odds_snapshots o
     WHERE o.game_id = ANY($1::bigint[])
     ORDER BY o.captured_at DESC
"""


def book_lines(rows, *, home: str, away: str) -> dict:
    """북이 실제로 건 **라인 숫자들** `{"totals": [...], "spreads": [...],
    "team_totals": [...]}`. 없으면 빈 dict.

    🔴 **가격을 넘기는 것이 아니다.** 넘기는 것은 "어느 라인에서 평가할지"
       뿐이고 확률은 λ 포아송에서 나온다. `h2h`(승패)는 바뀌지 않는다 —
       계약이 그것을 잠근다.
    🔴 라인을 고르는 규칙은 `n02_market._derivatives` 가 **원본**이다.
       여기서 market/side 문자열을 다시 해석하지 않는다(사본 금지).
    ⚠️ 빈 dict 를 주면 `mlb_market_probs` 가 기본 라인으로 돌아간다 —
       지어내지 않고 종전과 같아진다.
    """
    from app.flow.nodes.n02_market import _derivatives

    der = _derivatives(rows or [], home or "", away or "")
    out: dict = {}
    tl = (der.get("total") or {}).get("line")
    if tl is not None:
        out["totals"] = [float(tl)]
    sp = sorted({float(a["line"]) for a in (der.get("ah") or [])
                 if a.get("line") is not None})
    if sp:
        out["spreads"] = sp
    tt = sorted({float(v["line"]) for k in ("team_total_home", "team_total_away")
                 for v in ((der.get(k) or {}),) if v.get("line") is not None})
    if tt:
        out["team_totals"] = tt
    return out


async def lines_by_game(pool, game_ids) -> dict:
    """`{game_id(int): book_lines}`. 🔴 못 읽으면 **빈 dict** — 종전과 같다.

    ⚠️ 팀 이름은 `_derivatives` 의 팀토탈 판정에만 쓰인다. 여기서는 모르므로
       빈 문자열로 넘기고, 팀토탈 라인은 홈/원정 구분 없이 모은다.
    """
    ids = [int(g) for g in (game_ids or []) if str(g).isdigit()]
    if not ids or pool is None:
        return {}
    try:
        rows = [dict(r) for r in await pool.fetch(_LINES_SQL, ids)]
    except Exception as exc:
        logger.warning("[flow] 라인 조회 실패: %s", exc)
        return {}
    by: dict = {}
    for r in rows:
        by.setdefault(int(r["game_id"]), []).append(r)
    return {gid: book_lines(rs, home="", away="") for gid, rs in by.items()}


def _day_of(row: dict) -> str:
    """행의 KST 날짜(YYYY-MM-DD). 캐시 키가 그 날짜로 쓰인다."""
    from datetime import UTC, datetime

    from app.pipeline import KST

    v = row.get("kickoff_utc") or row.get("starts_at")
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            v = None
    if v is None:
        from app.pipeline import today_kst

        return today_kst()
    # ⚠️ 시차를 숫자로 적지 않는다 — `test_time_discipline` 이 잡는다.
    #    표준 시간대는 `KST` 하나다(`pipeline.today_kst` 와 같은 규약).
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    return v.astimezone(KST).date().isoformat()


async def research_from_collectors(redis, row: dict, day: str) -> dict | None:
    """[LAM-1] 판정 캐시가 없는 야구 경기의 `research` 를 **이미 있는 수집기
    캐시**로 만든다. 못 만들면 `None`.

    사용자 2026-09-24: "1,2번 해라"

    🔴 **왜 필요한가.** 흐름의 λ 는 구경로가 쓰는 슬레이트 캐시
       (`analysis:{sport}:{date}`)에 매달려 있었다. 그런데 실측:
```
analysis:mlb:2026-09-23   경기 13 · weather 12 · park_factor 10   ← λ 돈다
analysis:kbo:2026-09-24   **없음**      analysis:npb:2026-09-24  **없음**
```
       KBO·NPB 는 그 문서를 쓰는 쪽(구경로 파이프라인)이 저녁에야 돈다.
       그래서 두 리그는 λ 가 통째로 없었다 — 파크팩터도 날씨도 안 닿았다.

    🔴 **자료는 이미 있었다**(딥서치 2026-09-24, 운영 캐시 실측):
```
kbo_stats:teams:2026-09-24   10팀  KT  obp 0.364 · slg 0.405 · 득점/경기 5.649 · ERA 4.25
npb_stats:teams:2026-09-24   12팀  DeNA obp 0.309 · slg 0.377 · ERA 3.26
```
       `_offense` 는 wOBA 가 없으면 **OBP+ISO** 로 간다. 리그 분모도
       `kbo_stats.league_baselines` 가 팀 표에서 직접 만든다 — MLB 상수를
       KBO 에 쓰던 사고(2026-08-26)를 그 함수가 이미 막고 있다.

    🔴 **옮기는 규약을 다시 짓지 않는다(사본 금지).** 캐시→research 변환은
       각 수집기의 `merge_into_research` 가 원본이고 여기서는 부르기만 한다.
    ⚠️ 선발 **이름**은 `games.{side}_pitcher` 에서 심는다 — 공식 기록실에
       '오늘 선발' 칸이 없어 `merge_into_research` 가 이름을 보고 찾는다.
       그 칸은 D61-2 가 크롤러에서 채운다.
    ⚠️ 한 조각이 실패해도 나머지는 얹는다. λ 는 있는 재료로 세운다.
    """
    sport = _sport_of_row_sport(row)
    if sport not in ("kbo", "npb"):
        return None
    jg = {"sport": sport, "game_id": row.get("game_id") or row.get("id"),
          "home": row.get("home"), "away": row.get("away"),
          "starts_at": row.get("kickoff_utc") or row.get("starts_at")}
    research: dict = {}
    for side in ("home", "away"):
        who = str(row.get(f"{side}_pitcher") or "").strip()
        if who:
            research[f"{side}_pitcher"] = {"name": who}

    # ⚠️ [LAM-2] **내일 경기는 오늘 캐시를 쓴다.** 팀 시즌 지표는 하루에
    #    거의 안 움직이는데, 날짜가 정확히 맞는 캐시만 보면 내일 경기가
    #    통째로 λ 없이 남는다(실측: g1778·1779·1780 전부 "핵심 지표 부족").
    #    ⚠️ 새 규약이 아니다 — 바로 위 판정 캐시 조회가 이미 `(day, day-1)`
    #       로 내려간다. 같은 규약을 쓴다.
    days = [day]
    try:
        from datetime import date as _d
        from datetime import timedelta as _td

        days.append((_d.fromisoformat(day) - _td(days=1)).isoformat())
    except ValueError:
        pass
    try:
        if sport == "kbo":
            from app.collectors.kbo_stats import load as load_kbo
            from app.collectors.kbo_stats import merge_into_research as merge_kbo

            for d in days:
                teams, pitchers = await load_kbo(redis, d)
                if teams:
                    merge_kbo(research, jg, teams, pitchers or {})
                    break
        else:
            from app.collectors.npb_stats import load as load_npb
            from app.collectors.npb_stats import merge_into_research as merge_npb

            for d in days:
                teams = await load_npb(redis, d)
                if teams:
                    merge_npb(research, jg, teams)
                    break
    except Exception as exc:
        logger.warning("[flow] 팀 지표 조립 실패 game=%s: %s", jg["game_id"], exc)

    if sport == "kbo":
        try:
            from app.collectors.kbo_park import load as load_park
            from app.collectors.kbo_park import merge_into_research as merge_park

            table = await load_park(redis)
            if table:
                merge_park(research, jg, table)
        except Exception as exc:
            logger.warning("[flow] 파크팩터 조립 실패 game=%s: %s", jg["game_id"], exc)

    try:
        from app.collectors.weather import fetch_for_games
        from app.collectors.weather import merge_into_research as merge_wx

        wx = await fetch_for_games([jg])
        if wx:
            merge_wx(research, jg, wx)
    except Exception as exc:
        logger.warning("[flow] 날씨 조립 실패 game=%s: %s", jg["game_id"], exc)

    if not research:
        return None
    return {**jg, "research": research}


def _sport_of_row_sport(row: dict) -> str:
    """행의 **리그 코드**(kbo·npb·mlb). 🔴 `_sport_of` 는 `baseball|soccer` 를
    내므로 여기서 쓸 수 없다 — 두 가지를 섞지 않는다."""
    from app.flow.labels import sport_code

    class _S:
        sport = (row.get("sport") or "")
        league = (row.get("league") or "")

    return sport_code(_S())


def model_probs_from_cache(jg: dict | None, *, lines: dict | None = None,
                           settings=None) -> dict | None:
    """판정 캐시의 `research` 로 λ 를 세우고 전 마켓 확률을 만든다.

    🔴 **왜 여기서 만드나.** 옛 파이프라인은 야구에서 λ 경로를 통째로 건너뛴다
       (`pipeline.py:3763` · SEND-1 결정 B-1 2026-09-13). 그래서
       `pick_ledger.model_probs` 가 1,382행 전건 NULL 이고 ⑪의 구조 후보가
       0 이었다. **그 결정을 되돌리지 않는다** — 옛 발송 경로의 확률이 바뀐다.
       v1.4 흐름은 별도 경로이므로 여기서 따로 계산한다.
    🔴 계수를 만지지 않는다 — 30건 채점 전 동결(지시문 3-4 교정 원칙).
    ⚠️ 재료가 없으면 **None** 이다. "모델이 없다"와 "안 불렀다"는 다르다.
    """
    if not jg:
        return None
    sport = (jg.get("sport") or "").lower()
    if sport not in ("mlb", "kbo", "npb"):
        return None
    try:
        from app.engine.scoring import mlb_lambdas, mlb_market_probs

        lam = mlb_lambdas(jg, jg.get("research") or {}, settings, sport=sport)
        if not lam.home or not lam.away:
            logger.info("[flow] λ 못 세움 game=%s missing=%s",
                        jg.get("game_id"), lam.missing)
            return None
        return mlb_market_probs(lam.home, lam.away, lines=lines, settings=settings)
    except Exception as exc:
        logger.warning("[flow] 파생 확률 계산 실패 game=%s: %s", jg.get("game_id"), exc)
        return None


async def run_today(pool, redis, *, lookahead_h: int = 24, settings=None) -> dict:
    """오늘 슬레이트 전체를 섀도로 돌린다.

    🔴 **창(window)에 매이지 않는다.** 실사고 2026-09-19: `run_slate` 을
       `mlb_pregame_poll` 안에 넣었더니 그 함수가 폴링 창 밖에서 조기 반환해
       **한 번도 돌지 않았다**. 관측은 창과 무관해야 한다.
    """
    if pool is None:
        return {"games": 0, "stopped": {}, "sent": 0, "why": "풀 없음"}
    try:
        rows = [dict(r) for r in await pool.fetch(_SLATE_SQL, int(lookahead_h))]
    except Exception as exc:
        logger.warning("[flow] 슬레이트 조회 실패: %s", exc)
        return {"games": 0, "stopped": {}, "sent": 0, "why": "조회 실패"}
    return await run_slate(pool, redis, rows, settings=settings)


async def run_slate(pool, redis, rows: list, *, settings=None) -> dict:
    """슬레이트 1회. 반환 `{"games", "stopped": {사유: 수}, "sent"}`.

    🔴 **조용한 0 금지** — 어디서 몇 건이 멈췄는지 사유별로 센다. 그 분포가
       24h 섀도 관측의 보고 대상이다(지시문 §7).
    """
    from app.config import get_settings
    from app.flow.ctx import Ctx
    from app.flow.rules import get as rget
    from app.flow.run import run_game

    s = settings or get_settings()
    if not getattr(s, "pipeline_v14", False):
        return {"games": 0, "stopped": {}, "sent": 0, "why": "스위치 꺼짐"}

    # §3 예산 — 슬레이트 30% · 경기당 상한은 ⑤가 따로 본다.
    ratio = float(rget("deepsearch_cap.slate_ratio", 0.30) or 0.30)
    per_game = int(rget("deepsearch_cap.per_game", 5) or 5)
    cap = max(per_game, int(round(len(rows) * ratio)) * per_game)
    ctx = Ctx(pool=pool, redis=redis, settings=s,
              budget={"searches": 0, "slate_cap": cap})

    # 🔴 [ELO-1] **슬레이트 앞에서 사전값 재료를 보장한다.** 이게 없으면
    #    ①이 `p_home=None` 을 내고 ③이 전건 보드고정으로 읽는다
    #    (실측 2026-09-19: 36경기 전건).
    #    ⚠️ 키는 **킥오프 UTC 날짜**다 — `n01_prior._load_elo` 와 같은 기준을
    #       쓴다. 여기서 KST 를 쓰면 하루 어긋나 보장이 헛돈다.
    want: set = set()
    soccer_want: set = set()
    for r in rows:
        sp = (r.get("sport") or "").lower()
        if r.get("starts_at") is None:
            continue
        day = r["starts_at"].astimezone(UTC).date().isoformat()
        if sp in ELO_SPORTS:
            want.add((sp, day))
        elif sp == "soccer" and r.get("league"):
            # 🔴 [SELO-1 2026-09-20] 축구는 **리그별**이다. 종목으로 긁으면
            #    리그 간 비교가 되고, 그게 종전에 축구를 뺀 이유였다.
            soccer_want.add((r["league"], day))
    for sp, day in sorted(want):
        ok = await ensure_elo(pool, redis, sp, day)
        logger.info("[flow] elo 보장 %s %s — %s", sp, day, "있음" if ok else "없음")
    if soccer_want:
        await ensure_soccer_elo(redis, soccer_want, pool=pool)


    # 🔴 [2026-09-19] **파생 확률을 슬레이트 단위로 한 번 읽는다.**
    #    없으면 ⑪의 구조 후보가 0 이고, `동의` 라벨이 만든 파생 가설이 쓰일
    #    자리가 없다. 경기마다 조회하면 질의가 N배가 되므로 한 번에 읽는다.
    model_by_game: dict = {}
    if pool is not None:
        try:
            ids = [int(r["id"]) for r in rows if str(r.get("id") or "").isdigit()]
            if ids:
                for m in await pool.fetch(_MODEL_SQL, ids):
                    raw = m["model_probs"]
                    model_by_game[int(m["game_id"])] = (
                        json.loads(raw) if isinstance(raw, str) else raw)
        except Exception as exc:
            logger.warning("[flow] 파생 확률 조회 실패: %s", exc)
    # 🔴 [MOD-1] 판정 캐시를 **슬레이트마다 한 번** 읽는다 — 경기마다 읽으면
    #    같은 문서를 N번 파싱한다. 파생 확률의 재료(`research`)가 여기 있다.
    cache_by_game: dict = {}
    if redis is not None:
        from datetime import timedelta as _td
        for sp, day in sorted(want):
            for d in (day, (date.fromisoformat(day) - _td(days=1)).isoformat()):
                try:
                    raw = await redis.get(f"analysis:{sp}:{d}")
                except Exception:
                    raw = None
                if not raw:
                    continue
                try:
                    doc = json.loads(raw)
                except ValueError:
                    continue
                for cg in doc.get("games") or []:
                    cache_by_game.setdefault(str(cg.get("game_id")), cg)
                break
        made = 0
        # 🔴 [VAL-1] **북이 건 라인에서 확률을 낸다.** 종전에는 `lines` 를 안
        #    넘겨 λ 기준 기본 3개만 냈고, 북 라인과 3/8 만 맞았다. 안 맞으면
        #    ⑪의 `_structure_candidates` 가 그 마켓을 건너뛰어 후보가 0 이
        #    된다 — 실측 분포에서 `지정 마켓 total 후보 0` 이 8건이었다.
        #    ⚠️ 가격이 아니라 **라인 숫자**만 넘긴다(`h2h` 는 안 바뀐다).
        line_map = await lines_by_game(
            pool, [int(g) for g in cache_by_game if str(g).isdigit()])
        # 🔴 [LAM-1 2026-09-24] **캐시가 없는 야구 경기를 여기서 세운다.**
        #    구경로 슬레이트 문서는 KBO·NPB 에서 저녁에야 생긴다(실측:
        #    analysis:kbo:2026-09-24 없음). 그래서 두 리그는 λ 가 통째로
        #    없었다 — 파크팩터도 날씨도 안 닿았다. 재료는 이미 캐시에 있다.
        #    ⚠️ 캐시에 있는 경기는 **건드리지 않는다** — 구경로가 만든 것이
        #       더 풍부하다(딥서치·스탯캐스트).
        for row in rows:
            # 🔴 [LAM-1 정정 2026-09-24] `_SLATE_SQL` 은 **`id`** 를 준다 —
            #    `game_id` 가 아니다. 그걸 읽어 `"None"` 이 되면 아래에서
            #    `int("None")` 으로 **슬레이트 전체가 죽는다.** 내가 넣은
            #    결함이고, 계약이 `run_slate` 를 실제 행 모양으로 돌려보지
            #    않아 초록이었다(거짓 통과).
            gid = str(row.get("game_id") or row.get("id") or "")
            if not gid.isdigit():
                continue
            if gid in cache_by_game or gid in {str(k) for k in model_by_game}:
                continue
            try:
                built = await research_from_collectors(
                    redis, dict(row), _day_of(row))
            except Exception as exc:
                logger.warning("[flow] research 조립 실패 game=%s: %s", gid, exc)
                built = None
            if built:
                cache_by_game[gid] = built
        for gid, cg in cache_by_game.items():
            if gid in {str(k) for k in model_by_game}:
                continue          # 원장에 있으면 그것이 먼저다
            got = model_probs_from_cache(
                cg, lines=line_map.get(int(gid)) if str(gid).isdigit() else None,
                settings=s)
            if got:
                model_by_game[int(gid)] = got
                made += 1
        logger.info("[flow] 파생 확률 — 원장 %d건 · 캐시에서 계산 %d건",
                    len(model_by_game) - made, made)

    if rows and not model_by_game:
        # 🔴 조용한 0 금지 — "모델이 없다"와 "안 읽었다"는 다르다.
        logger.info("[flow] 파생 확률 0건 — 구조 픽 후보가 서지 않는다 "
                    "(판정이 실패하면 λ 산출 블록이 안 돈다)")

    out: dict = {"games": 0, "stopped": {}, "sent": 0}
    for r in rows:
        game = {"game_id": r.get("id") or r.get("game_id"),
                "sport": _sport_of(r), "league": r.get("league") or "",
                "home": r.get("home") or "", "away": r.get("away") or "",
                "kickoff_utc": r.get("starts_at")}
        # 🔴 경기마다 주입을 갈아끼운다. 예산(`ctx.budget`)은 **슬레이트 단위로
        #    유지**된다 — 그래서 `inject` 만 바꾸고 ctx 를 새로 만들지 않는다.
        gid = game["game_id"]
        # 🔴 [REJ-1] ⑩ 재판정 신호도 함께 준다. 종전에는 `model_probs` 하나만
        #    줘서 `rejudge_signals` 가 영원히 빈 dict 였고 `n10_rejudge` 행이
        #    0건이었다(Phase 0 D-7).
        ctx.inject = {"model_probs": model_by_game.get(
            int(gid) if str(gid).isdigit() else -1),
            "rejudge_signals": rejudge_signals_of(cache_by_game.get(str(gid)))}
        try:
            st = await run_game(game, ctx)
        except Exception as exc:
            logger.warning("[flow] game=%s 실행 실패: %s", game["game_id"], exc)
            out["stopped"]["error"] = out["stopped"].get("error", 0) + 1
            continue
        out["games"] += 1
        key = st.stop_reason or "완주"
        out["stopped"][key] = out["stopped"].get(key, 0) + 1
        if (st.n13_send or {}).get("sent"):
            out["sent"] += 1
        # 🔴 [OBS-2 2026-09-20] **관측 상태를 남긴다.** 종전에는 상태기계가
        #    두 모듈(`watch_state`·`observer`)에 있었는데 **둘 다 호출부가
        #    0건**이었고 `pick_ledger` 1,393행이 전건 NULL 이었다.
        #    ⚠️ 흐름이 아는 것만 올린다 — `추천대기` 는 조건 A 가 분석 LLM
        #       판단(`market_view`)과 `swap_agree` 를 요구하고 v1.4 에 그 값이
        #       없다. 없는 값을 지어내 상태를 올리지 않는다.
        #    ⚠️ 전이는 반드시 허용표를 지난다 — 역방향이면 그대로 둔다.
        try:
            want = WATCH.state_of(gate=(st.n03_gate or {}).get("gate"),
                                  sent=bool((st.n13_send or {}).get("sent")),
                                  started=_already_started(game))
            moved = await _write_watch(pool, game.get("game_id"), want)
            out.setdefault("watch", {})
            out["watch"][moved] = out["watch"].get(moved, 0) + 1
        except Exception as exc:
            logger.warning("[flow] game=%s 관측 상태 기록 실패: %s",
                           game.get("game_id"), exc)
    logger.info("[flow] 슬레이트 %d경기 · 멈춤 %s · 발송 %d · 관측 %s (예산 %d/%d)",
                out["games"], out["stopped"], out["sent"],
                out.get("watch") or {}, ctx.budget["searches"], cap)
    return out


def _already_started(game: dict) -> bool:
    """킥오프가 지났나. ⚠️ `starts_at` 이 없으면 **모른다 → False** 다."""
    ko = game.get("starts_at")
    if ko is None:
        return False
    try:
        from datetime import datetime as _dt

        return ko.astimezone(UTC) <= _dt.now(UTC)
    except Exception:
        return False


async def _write_watch(pool, game_id, want: str) -> str:
    """`games.watch_state` 를 허용표를 지나 갱신한다. 반환: **실제 상태**.

    🔴 거부된 전이는 현재 상태를 그대로 돌려준다 — 조용히 덮지 않는다.
    """
    if pool is None or game_id is None:
        return want
    gid = int(game_id) if str(game_id).isdigit() else None
    if gid is None:
        return want
    row = await pool.fetchrow("SELECT watch_state FROM games WHERE id = $1", gid)
    cur = (row or {}).get("watch_state") if row else None
    nxt = WATCH.advance(cur, want)
    if nxt != cur:
        await pool.execute("UPDATE games SET watch_state = $2 WHERE id = $1", gid, nxt)
    return nxt
