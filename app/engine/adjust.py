"""[ADJ-1] 조정 변수를 **DB 원자료**에서 계산해 `jg` 에 키만 세팅한다.

사용자 결정 2026-09-13(2차 결정 A): `prob.py` 는 순수 함수로 유지하고,
이 모듈이 `_attach_market_spine` **직전**에 돈다. 수집기는 건드리지 않는다.

🔴 **왜 필요한가.** 실측 2026-09-13(결정 1 배포 직후, MLB 8경기):
   `adj_pp` 가 전부 `{}` 였고 `p_code == p_market` 이었다 — **코드가 시장을
   그대로 베꼈다.** 그 상태로 CLV 를 쌓으면 평균 0 이 나오는 것이 당연하다.

🔴 **0 과 미계산을 구분한다.** 0 은 "조사했는데 없었다", 미계산(`adj_missing`)은
   "원자료가 없어 못 쟀다"다. 섞으면 조정이 왜 안 붙었는지 영영 모른다.
⚠️ 타순이 official 이 아니면 결장·선발변경을 계산하지 않는다(`adj_pending`) —
   잠정으로 조정하면 확정 뒤 뒤집힌다.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

logger = logging.getLogger(__name__)

#: 🔴 임계값은 **여기 한 곳**에만 있다. 함수 안에 숫자를 흩어 적지 않는다.
ADJ_DEFS = {
    "starter_recent_n": 5,        # 선발 변경 비교용 최근 선발 수
    "regular_window": 10,         # 주전 판정 창(야구)
    "regular_min": 7,             # 그 창에서 선발 출장 최소 경기
    "pen_top_n": 3,               # 필승조로 볼 상위 인원
    "pen_window_days": 30,        # 등판 수를 세는 창
    "pen_b2b_days": 2,            # 직전 N일 연속이면 연투
    "trip_min": 3,                # 연속 원정 N경기 이상이면 이동연전
    "soccer_regular_window": 10,
    "soccer_regular_min": 8,
    "rest_days_max": 3,           # 직전 공식전 N일 이하면 짧은 휴식
    "midweek_days": 4,            # 직전 N일 내 대항전 원정
    # 🔴 [U8 2026-09-15] 9종으로. 종전 7종에는 핵심결장·직전대패가 없었다.
    "key_out_importance": 1.2,    # importance 가 이 값 이상이면 '핵심결장'
    "rout_margin": 3,             # 직전 경기 이 점수차 이상 패배면 '직전대패'
}


def gate(jg: dict) -> bool:
    """타순/라인업이 official 인가. 🔴 상태값을 손으로 적지 않는다."""
    from app.collectors.lineups import STATUS_CONFIRMED

    return (jg.get("lineup_status") or "") == STATUS_CONFIRMED


def count_out(regulars: set, today: list) -> int | None:
    """주전 중 오늘 명단에 없는 인원. 오늘 명단이 비면 **미계산**(None)."""
    if not today:
        return None
    present = {str(x).strip() for x in today if str(x).strip()}
    return sum(1 for r in regulars if r not in present)


def count_b2b(apps: dict, today: date) -> int:
    """직전 `pen_b2b_days` 일 **연속** 등판한 인원 수."""
    days = [today - timedelta(days=i + 1)
            for i in range(ADJ_DEFS["pen_b2b_days"])]
    return sum(1 for ds in apps.values() if all(d in set(ds) for d in days))


def trip_flag(streak: int) -> int:
    """연속 원정 경기 수 → 발생 여부(0/1)."""
    return 1 if (streak or 0) >= ADJ_DEFS["trip_min"] else 0


def short_rest(days) -> bool:
    """직전 공식전으로부터 `rest_days_max` 일 이하인가."""
    return days is not None and days <= ADJ_DEFS["rest_days_max"]


def midweek_away(jg: dict):
    """직전 `midweek_days` 일 내 대항전 **원정**.

    ⚠️ 대항전 일정 소스가 **없다** → 항상 미계산(None). 0 이 아니다.
    """
    return jg.get("midweek_away_known")


#: 🔴 [ADJ-4 2026-09-13] 타순 본문은 `lineups` 가 아니라 **`lineup_events`** 다.
#   실측: `lineups` 최근 5일에 kbo 0행 · npb 2행 · mlb 8~76행.
#         `lineup_events` 는 kbo 매일 8행/4경기 · npb 8~12행으로 꾸준하다.
#   🔴 그리고 **팀 기준**으로 조회한다. 종전 `side` 기준은 우리 팀이 원정이던
#      경기의 `side='home'` 행(= 상대 라인업)을 주전 집계에 섞어 넣었다.
_REGULARS = """
    SELECT le.batting_order
      FROM lineup_events le JOIN games g ON g.id = le.game_id
     WHERE le.team = $1 AND le.is_final AND g.sport = $2
       AND g.starts_at < $3
     ORDER BY g.starts_at DESC LIMIT $4
"""

_TODAY_ORDER = """
    SELECT batting_order FROM lineup_events
     WHERE game_id = $1 AND side = $2 AND is_final
     ORDER BY observed_at DESC LIMIT 1
"""

_PEN = """
    SELECT pa.pitcher, g.starts_at::date AS d
      FROM pitcher_appearances pa JOIN games g ON g.id = pa.game_id
     WHERE pa.team = $1 AND pa.is_starter = false
       AND g.starts_at >= $2 AND g.starts_at < $3
"""

#: 🔴 [ADJ-2 2026-09-13] **오늘 경기를 뺀다**(`<`). 종전 `<=` 는 오늘 경기
#   자신을 첫 행으로 잡았고, 홈팀은 오늘 홈경기라 첫 바퀴에서 break —
#   `연속원정` 이 **항상 0** 이었다. 실측: 9/9 경기 0.
_TRIP = """
    SELECT g.home, g.away FROM games g
     WHERE g.sport = $1 AND (g.home = $2 OR g.away = $2) AND g.starts_at < $3
     ORDER BY g.starts_at DESC LIMIT 8
"""


#: 🔴 [ADJ-4] 타순 원소는 `"양의지(포수)"` 처럼 **포지션이 붙어 온다**.
#   실측 2026-09-13(14일): 포지션이 2가지 이상인 선수가 KBO 30% · NPB 18%.
#   떼지 않으면 (a) 주전 판정에서 분산돼 누락되고(67명 → 78명)
#   (b) 오늘 포지션이 바뀐 주전이 **결장으로 오인된다** ← 반대 위험.
_POS = re.compile(r"\s*\([^)]*\)\s*$")


def _name(x) -> str:
    s = x.get("이름") if isinstance(x, dict) else x
    return _POS.sub("", str(s or "")).strip()


def _arr(v) -> list:
    if isinstance(v, list):
        out = v
    else:
        try:
            out = json.loads(v or "[]")
        except (TypeError, ValueError):
            return []
        if not isinstance(out, list):
            return []
    return [n for n in (_name(x) for x in out) if n]


async def attach(jg: dict, pool) -> None:
    """조정 입력 키를 `jg` 에 세팅한다. 실패는 **미계산**으로 남긴다."""
    missing: list[str] = []
    inputs: dict = {}
    # 🔴 [PA-23 · 지시문 5단계] 변수마다 **근거**를 함께 남긴다.
    #    `adj_pp` 는 delta 만 들고 있어 "이 −2%p 가 어디서 왔나"를 원장만 보고
    #    답할 수 없었다 — 10단계 변수별 채점이 무엇을 채점하는지 모른다.
    #    ⚠️ `adj_pp` 모양은 **안 바꾼다**(소비자 다섯). 별도 칸으로 남긴다.
    ev: dict = {}

    def _ev(name: str, value, source: str, evidence: str) -> None:
        """변수 하나의 근거. 값이 없으면 남기지 않는다(지어내지 않는다)."""
        if value is None:
            return
        ev[name] = {"value": value, "source": source, "evidence": evidence}
    # 🔴 T-24h 선발 스냅샷 테이블이 없다(검색 결과 `odds_snapshots` 뿐).
    #    트리거 추가는 통합 지시문 Part A 의 몫이다 — 여기서 만들지 않는다.
    missing.append("starter_changed")

    if not gate(jg):
        jg["adj_pending"] = True
        jg["adj_missing"] = missing + ["out_starters"]
        jg["adj_inputs"] = inputs
        jg["adj_evidence"] = ev
        logger.info("[adjust] game=%s 타순 미확정(%s) — 결장 변수 미계산",
                    jg.get("game_id"), jg.get("lineup_status"))
        return

    sport = (jg.get("sport") or "").lower()
    # 🔴 [PA-1 2026-09-16] **문자열을 datetime 으로 연다.** 파이프라인이 넣는
    #    `starts_at` 은 ISO 문자열이라 asyncpg 의 TIMESTAMPTZ 파라미터에 못
    #    들어가고, 아래 `starts.date()`·`starts - timedelta(...)` 도 터진다.
    #    실측 2026-09-16 PART A: 경기당 4건 × 2경기 = **8건 전건 실패**
    #      invalid input for query argument $3: '2026-09-16T01:38:00+00:00'
    #      (expected a datetime.date or datetime.datetime instance, got 'str')
    #    그래서 주전결장·필승조연투·이동연전이 통째로 빠지고, 결정축은 뽑을
    #    것이 없어진다.
    # 🔴 **파서를 다시 만들지 않는다** — `starter_recent._aware` 가 원본이고
    #    다른 엔진 모듈 셋이 이미 같은 자리에서 쓴다. 여기만 안 쓰고 있었다.
    #    (어느 셋인지는 docs/maps/PA-1.md 에 적었다 — 이 파일에 모듈 이름을
    #     적으면 `test_수집기를_건드리지_않는다` 가 호출로 오인한다.)
    # 🔴 못 읽으면 **None 그대로** 둔다. "지금"으로 채우면 과거 경기를 미래로
    #    읽는다 — 아래 분기가 None 을 미계산으로 처리한다.
    from app.engine.starter_recent import _aware

    starts = _aware(jg.get("starts_at"))
    soccer = sport == "soccer"
    win = ADJ_DEFS["soccer_regular_window"] if soccer else ADJ_DEFS["regular_window"]
    need = ADJ_DEFS["soccer_regular_min"] if soccer else ADJ_DEFS["regular_min"]

    # ── 주전 결장 (양 팀 합산이 아니라 **홈 기준 부호**를 위해 각각 센다)
    outs = {}
    for side in ("home", "away"):
        team = jg.get(side) or ""
        try:
            rows = await pool.fetch(_REGULARS, team, sport, starts, win)
            cnt: dict[str, int] = {}
            for r in rows:
                for nm in _arr(r["batting_order"]):
                    if nm:
                        cnt[nm] = cnt.get(nm, 0) + 1
            regulars = {k for k, v in cnt.items() if v >= need}
            cur = await pool.fetchval(_TODAY_ORDER, jg.get("game_id"), side)
            n = count_out(regulars, _arr(cur))
        except Exception as exc:
            logger.warning("[adjust] game=%s %s 주전결장 실패: %s",
                           jg.get("game_id"), side, exc)
            n = None
        outs[side] = n
        if n is not None:
            inputs.setdefault("주전결장", {})[side] = n
            _ev("주전결장", inputs["주전결장"], "lineup_events",
                f"창 {win}경기 중 {need}회 이상 선발한 주전 기준 · "
                + " · ".join(f"{k} {v}명" for k, v in inputs["주전결장"].items()))
    if outs["home"] is None or outs["away"] is None:
        missing.append("out_starters")
    else:
        # 🔴 [ADJ-4] **부호를 연다.** 종전 `max(0, …)` 은 원정 결장을 언제나
        #    0 으로 만들었고(ADJ-3 과 같은 결함), 대신 두던 `out_starters_away`
        #    는 `ADJ_RULES` 에 없어 **아무도 읽지 않는 죽은 키**였다.
        #    홈이 더 빠지면 양수(홈에 불리) · 원정이 더 빠지면 음수(홈에 유리).
        jg["out_starters"] = outs["home"] - outs["away"]

    # ── 불펜 연투
    try:
        today = starts.date() if starts else None
        lo = (starts - timedelta(days=ADJ_DEFS["pen_window_days"])) if starts else None
        b2b = {}
        for side in ("home", "away"):
            rows = await pool.fetch(_PEN, jg.get(side) or "", lo, starts)
            by: dict[str, list] = {}
            for r in rows:
                by.setdefault(r["pitcher"], []).append(r["d"])
            top = sorted(by, key=lambda k: len(by[k]), reverse=True)[:ADJ_DEFS["pen_top_n"]]
            b2b[side] = count_b2b({k: by[k] for k in top}, today) if today else None
        if b2b["home"] is None or b2b["away"] is None:
            missing.append("bullpen_b2b")
        else:
            # 🔴 [ADJ-3 2026-09-13] **부호를 연다.** 종전 `max(0, …)` 은
            #    원정이 더 지친 경우를 언제나 0 으로 만들었다 —
            #    실측 롯데@KT 원정 3명 · 홈 1명인데 조정 0 이었다.
            #    음수면 원정이 더 지친 것이고, 홈에 유리로 읽힌다.
            jg["bullpen_b2b"] = b2b["home"] - b2b["away"]
            inputs["필승조연투"] = b2b
            _ev("필승조연투", b2b, "pitcher_appearances",
                f"직전 {ADJ_DEFS['pen_b2b_days']}일 연속 등판 · "
                + " · ".join(f"{k} {v}명" for k, v in b2b.items()))
    except Exception as exc:
        logger.warning("[adjust] game=%s 불펜 연투 실패: %s", jg.get("game_id"), exc)
        missing.append("bullpen_b2b")

    # ── 구속 하락 (D2 · PA-18)
    # 🔴 **새 HTTP 를 켜지 않는다.** 위성이 이미 재서 redis 에 남긴 값을 읽는다.
    #    판정 경로에서 Savant 를 치면 느리고 실패한다.
    # 🔴 **홈 기준 부호**다 — 홈이 떨어졌으면 음수(홈에 불리), 원정이
    #    떨어졌으면 양수. 결장·연투와 같은 규약(ADJ-3/ADJ-4).
    try:
        from app.collectors.satellite import read_velo

        velo = await read_velo(jg.get("_redis"), sport, jg.get("game_id"))
        dh, da = velo.get(jg.get("home")), velo.get(jg.get("away"))
        if dh is None and da is None:
            missing.append("velo_drop")
        else:
            # 떨어진 쪽만 센다. 오른 것은 신호가 아니다(D2 는 하락만 말한다).
            drop_h = 1 if (dh is not None and dh <= -VELO_MIN) else 0
            drop_a = 1 if (da is not None and da <= -VELO_MIN) else 0
            jg["velo_drop"] = drop_h - drop_a
            inputs["구속하락"] = {"home": dh, "away": da}
            _ev("구속하락", {"home": dh, "away": da}, "statcast",
                f"시즌 평균 대비 홈 {dh}mph · 원정 {da}mph "
                f"(문턱 {VELO_MIN}mph)")
    except Exception as exc:
        logger.warning("[adjust] game=%s 구속 하락 실패: %s", jg.get("game_id"), exc)
        missing.append("velo_drop")

    # ── 이동 연전 (홈 팀 기준)
    try:
        rows = await pool.fetch(_TRIP, sport, jg.get("home") or "", starts)
        streak = 0
        for r in rows:
            if r["away"] == jg.get("home"):
                streak += 1
            else:
                break
        jg["trip_day"] = trip_flag(streak)
        inputs["이동연전"] = {"연속원정": streak}
        _ev("이동연전", {"연속원정": streak}, "games",
            f"홈팀 직전 연속 원정 {streak}경기 "
            f"(문턱 {ADJ_DEFS['trip_min']})")
    except Exception as exc:
        logger.warning("[adjust] game=%s 이동연전 실패: %s", jg.get("game_id"), exc)
        missing.append("trip_day")

    if soccer:
        # 대항전 일정 소스가 없다 → 미계산
        if midweek_away(jg) is None:
            missing.append("midweek_away")
        if jg.get("rest_days") is None:
            missing.append("rest_days")

    jg["adj_missing"] = missing
    jg["adj_inputs"] = inputs
    jg["adj_evidence"] = ev
    logger.info("[adjust] game=%s 입력=%s 미계산=%s",
                jg.get("game_id"), inputs, missing)


# ═══════════════ [U8 2026-09-15] 가중 · 결정축
#
# 🔴 왜: 지금은 주전 3명 결장과 후보 3명 결장이 **같은 −3** 이다. 결장이
#    **이름 수**로 세어진다. U6 가 시장가치를 저장했는데 쓰는 곳이 없었다.
# 🔴 그리고 `main_axis` 를 **미배선 analyze(LLM)** 가 채우게 돼 있었다.
#    코드가 정한다 — 그래야 LLM 이 없어도 결정축이 선다.
# 🔴 [U13] 값은 `config/rules.yaml` 이 원본이다. 여기에 숫자를 **다시
#    적지 마라** — 두 곳에 적으면 사본이 되고, 사본은 원본이 바뀔 때
#    따라가지 않는다(실사고 2026-09-02 워치독 오탐 4건).
from app.engine import rules as _R


#: 결장 배율·상한. 🔴 `prob.ADJ_SUM_CAP`(±6) 과 **다른 층**이다 —
#  이건 결장 항목 **안쪽** 상한이고, 그건 조정 **전체** 상한이다.
OUT_MULT = _R.get("adjust.out_mult")
OUT_CAP = _R.get("adjust.out_cap")
#: 복귀는 결장의 1.5배로 되돌린다(예상 결장이 실제 출전).
RETURN_MULT = _R.get("adjust.return_mult")

#: 기여가 이 값(%p) 미만이면 조정에서 뺀다. 잡음이 결정축에 끼는 것을 막는다.
MIN_CONTRIB_PP = _R.get("adjust.min_contrib_pp")

#: 🔴 구속 하락 문턱(mph). **원본은 `statcast_velo.VELO_DELTA_MIN`** 이다 —
#   여기서 숫자를 다시 적지 않는다.
from app.collectors.statcast_velo import VELO_DELTA_MIN as VELO_MIN  # noqa: E402

#: 최근 N경기 선발 창(출장률 분모).
RECENT_STARTS_N = _R.get("adjust.recent_starts_n")

#: 무조건 최소 1.0 인 자리. GK·주장·득점 1위.
MIN_IMPORTANCE_ROLES = ("gk", "captain", "top_scorer")


def importance(player: dict, *, team_total_value=None, n_starters: int = 11,
               recent_starts: int | None = None) -> float:
    """선수 한 명의 중요도. 1.0 이 '평균 주전'이다.

        0.5·(최근10 선발/10) + 0.5·(시장가치 / (팀 선발 총가치/11))

    🔴 출장 이력이 없으면 **시장가치 단독**이다. 0 으로 읽으면 신입·이적생이
       전부 0.5 가 된다 — 안 본 것과 안 뛴 것은 다르다.
    🔴 팀 총가치가 없으면 **출장률 단독**이다. 둘 다 없으면 1.0(중립) —
       지어내지 않는다.
    🔴 GK·주장·득점 1위는 **최소 1.0**. 시장가치가 낮아도 빠지면 아프다.
    """
    p = player or {}
    parts = []
    if recent_starts is not None:
        parts.append(max(0.0, min(1.0, float(recent_starts) / RECENT_STARTS_N)))
    mv = p.get("market_value")
    if mv and team_total_value:
        avg = float(team_total_value) / max(1, int(n_starters))
        if avg > 0:
            parts.append(float(mv) / avg)
    if not parts:
        base = 1.0
    elif len(parts) == 1:
        base = parts[0]
    else:
        base = 0.5 * parts[0] + 0.5 * parts[1]
    if any(bool(p.get(r)) for r in MIN_IMPORTANCE_ROLES):
        base = max(base, 1.0)
    return round(float(base), 3)


def contrib_out(players: list, **kw) -> float:
    """결장 기여(%p). 음수다. 🔴 상한 −6 — 여기서만 자른다."""
    total = sum(importance(p, **kw) for p in (players or []))
    return round(max(-OUT_CAP, -total * OUT_MULT), 2)


def contrib_return(players: list, **kw) -> float:
    """복귀 기여(%p). 양수이고 결장의 1.5배로 되돌린다."""
    total = sum(importance(p, **kw) for p in (players or []))
    return round(min(OUT_CAP, total * OUT_MULT * RETURN_MULT), 2)


def drop_small(adj: dict | None) -> tuple:
    """`(남긴 것, 뺀 것)`. |기여| < 2%p 는 뺀다.

    🔴 **축소(`prob.shrink_and_cap`) 앞에서** 한다. 뒤에서 빼면 축소된 값으로
       2%p 를 재게 되어 기준이 달라진다.
    """
    keep, dropped = {}, {}
    for k, v in (adj or {}).items():
        (keep if abs(float(v)) >= MIN_CONTRIB_PP else dropped)[k] = v
    return keep, dropped


def axes(adj: dict | None) -> dict:
    """결정축·반대축을 **코드가** 고른다.

    `main_axis` = |기여| 상위 2 · `counter_axis` = **반대 방향 최대 1개**.

    🔴 반대축을 같은 방향에서 고르면 "반대 근거"가 아니라 "약한 같은 근거"가
       된다. 방향이 갈리는 것이 없으면 **없는 것**이다(지어내지 않는다).
    """
    items = [(k, float(v)) for k, v in (adj or {}).items() if v]
    if not items:
        return {"main_axis": [], "counter_axis": None, "direction": None}
    items.sort(key=lambda kv: abs(kv[1]), reverse=True)
    main = items[:2]
    sign = 1 if main[0][1] > 0 else -1
    counter = next((k for k, v in items
                    if (1 if v > 0 else -1) != sign), None)
    return {"main_axis": [k for k, _ in main],
            "counter_axis": counter,
            "direction": "home" if sign > 0 else "away"}
