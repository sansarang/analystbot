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
    # 🔴 T-24h 선발 스냅샷 테이블이 없다(검색 결과 `odds_snapshots` 뿐).
    #    트리거 추가는 통합 지시문 Part A 의 몫이다 — 여기서 만들지 않는다.
    missing.append("starter_changed")

    if not gate(jg):
        jg["adj_pending"] = True
        jg["adj_missing"] = missing + ["out_starters"]
        jg["adj_inputs"] = inputs
        logger.info("[adjust] game=%s 타순 미확정(%s) — 결장 변수 미계산",
                    jg.get("game_id"), jg.get("lineup_status"))
        return

    sport = (jg.get("sport") or "").lower()
    starts = jg.get("starts_at")
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
    except Exception as exc:
        logger.warning("[adjust] game=%s 불펜 연투 실패: %s", jg.get("game_id"), exc)
        missing.append("bullpen_b2b")

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
    logger.info("[adjust] game=%s 입력=%s 미계산=%s",
                jg.get("game_id"), inputs, missing)
