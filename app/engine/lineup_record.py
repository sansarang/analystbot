"""[§9-라인업 전적] 확정 9명과 비슷한 과거 출전 → 그때의 경기 결과.

평소 타순(`usual`)은 "누가 자주 나오나"만 본다. 여기서는 **그 9명에 가까운
출전이 이겼는지**를 사실로 붙인다. 승률 계수는 만들지 않는다 — 표본이 얇고
측정된 `adj_*`가 없다(DISCIPLINE 5-1).

⚠️ 전적 기준은 `source='boxscore'`(실제 출전)만. 발표 라인업과 섞지 않는다.
⚠️ 오늘 경기(`starts_at` 이상)는 한 줄도 넣지 않는다 — 점수 누수.
⚠️ 표본 3경기 미만이면 승률을 산출하지 않는다. 나열만 한다.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.collectors.lineup_history import _as_dt
from app.engine.lineup_diff import TOP_ORDER, canon_name, parse_order

logger = logging.getLogger(__name__)

MIN_NAME_OVERLAP = 7       # 9명 중 교집합
MIN_CORE_OVERLAP = 4       # 1~5번 교집합 (폴백 때 n_shared와 함께)
MIN_SHARED_FALLBACK = 5    # 코어만으로 7명 미만을 통과시키려면 전체도 이 이상
MIN_RATE_GAMES = 3         # 이 미만이면 win_pct를 안 만든다
LOOKBACK = 40              # 유사 필터 전 박스스코어 상한
SOURCE_BOXSCORE = "boxscore"

_FETCH = """
    SELECT e.game_id, e.side, e.batting_order, e.source,
           g.home_score, g.away_score, g.starts_at,
           g.home AS home_team, g.away AS away_team
      FROM lineup_events e
      JOIN games g ON g.id = e.game_id
     WHERE g.sport = $1 AND e.team = $2
       AND g.starts_at < $3
       AND g.status = 'final'
       AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
       AND e.source = $4
     ORDER BY g.starts_at DESC
     LIMIT $5
"""


def _aware(v) -> datetime | None:
    dt = _as_dt(v)
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def names_of(order: list[tuple[str, str]]) -> list[str]:
    return [canon_name(n) for n, _ in order if canon_name(n)]


def overlap(today: list[tuple[str, str]], past: list[tuple[str, str]]) -> dict:
    """오늘 9명 vs 과거 9명. 비교는 정규화 이름만."""
    a, b = set(names_of(today)), set(names_of(past))
    shared = a & b
    core = set(names_of(today)[:TOP_ORDER]) & set(names_of(past)[:TOP_ORDER])
    n_shared, n_core = len(shared), len(core)
    primary = n_shared >= MIN_NAME_OVERLAP
    fallback = (not primary and n_core >= MIN_CORE_OVERLAP
                and n_shared >= MIN_SHARED_FALLBACK)
    return {"n_shared": n_shared, "n_core": n_core,
            "qualifies": primary or fallback}


def team_result(side: str, home_score, away_score) -> str | None:
    """그 팀 기준 W/L/D. 점수 없으면 None. KBO 무승부는 D."""
    if home_score is None or away_score is None:
        return None
    try:
        hs, aws = int(home_score), int(away_score)
    except (TypeError, ValueError):
        return None
    if hs == aws:
        return "D"
    home_won = hs > aws
    won = home_won if side == "home" else (not home_won)
    return "W" if won else "L"


def _empty(note: str) -> dict:
    return {"n": 0, "w": 0, "l": 0, "d": 0, "win_pct": None,
            "games": [], "note": note, "source": SOURCE_BOXSCORE}


def format_record(rec: dict | None) -> str:
    """카드·판정용 한 줄. 표본 부족이면 승률을 쓰지 않는다."""
    rec = rec or {}
    n = int(rec.get("n") or 0)
    if n <= 0:
        return rec.get("note") or "유사 타순 전적 없음"
    wl = f"{rec.get('w', 0)}승 {rec.get('l', 0)}패 {rec.get('d', 0)}무"
    if rec.get("win_pct") is None:
        return (f"유사 타순 {n}경기 ({wl}) — 표본 부족, 승률 미산출"
                f" · {rec.get('source_note') or '실제 출전 기록'}")
    return (f"유사 타순 {n}경기 {wl} (승률 {float(rec['win_pct']):.0%})"
            f" · {rec.get('source_note') or '실제 출전 기록'}")


def similar_from_rows(today: list[tuple[str, str]], rows: list[dict],
                      before) -> dict:
    """조회 결과를 전적 dict로. DB 없이 테스트한다.

    각 row: batting_order, starts_at, home_score, away_score, side, source, game_id
    """
    cutoff = _aware(before)
    if cutoff is None:
        return _empty("경기 시각 없음 — 전적 조회 안 함")
    today = [x for x in (today or []) if x]
    if len(today) < 9:
        return _empty("오늘 확정 9명이 없어 전적 조회 안 함")

    seen: set = set()
    matched: list[dict] = []
    for row in rows or []:
        if (row.get("source") or "") != SOURCE_BOXSCORE:
            continue
        start = _aware(row.get("starts_at"))
        if start is None or start >= cutoff:
            continue
        gid = row.get("game_id")
        if gid in seen:
            continue
        past = parse_order(row.get("batting_order"))
        ov = overlap(today, past)
        if not ov["qualifies"]:
            continue
        seen.add(gid)
        side = row.get("side") or "home"
        res = team_result(side, row.get("home_score"), row.get("away_score"))
        if res is None:
            continue
        matched.append({
            "game_id": gid, "result": res,
            "n_shared": ov["n_shared"], "n_core": ov["n_core"],
            "score": f"{row.get('away_score')}-{row.get('home_score')}",
        })

    w = sum(1 for g in matched if g["result"] == "W")
    l = sum(1 for g in matched if g["result"] == "L")
    d = sum(1 for g in matched if g["result"] == "D")
    decided = w + l
    win_pct = round(w / decided, 4) if decided >= MIN_RATE_GAMES else None
    note = ("실제 출전 기록 기준"
            if matched else "비슷한 출전 9명 없음 (교집합 7 또는 코어 4+전체 5)")
    return {
        "n": len(matched), "w": w, "l": l, "d": d, "win_pct": win_pct,
        "games": matched[:12], "note": note, "source": SOURCE_BOXSCORE,
        "source_note": "실제 출전 기록",
    }


def _parse_today(today_order) -> list[tuple[str, str]]:
    """이미 (이름, 포지션)이면 그대로. str(tuple)로 깨지지 않게."""
    if isinstance(today_order, list) and today_order \
            and isinstance(today_order[0], tuple):
        return list(today_order)
    return parse_order(today_order)


async def lookup(pool, sport: str, team: str | None, today_order,
                 before) -> dict:
    """그 팀의 오늘 9명과 비슷한 과거 박스스코어 전적."""
    parsed = _parse_today(today_order)
    cutoff = _aware(before)
    if not pool or not team or cutoff is None:
        return _empty("이력 조회 불가")
    if len(parsed) < 9:
        return _empty("오늘 확정 9명이 없어 전적 조회 안 함")
    try:
        rows = await pool.fetch(
            _FETCH, sport, team, cutoff, SOURCE_BOXSCORE, LOOKBACK)
    except Exception as exc:
        logger.warning("[라인업전적] 조회 실패 %s/%s: %s", sport, team, exc)
        return _empty("이력 조회 실패")
    as_dicts = []
    for r in rows:
        raw = r["batting_order"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                pass
        as_dicts.append({
            "game_id": r["game_id"], "side": r["side"],
            "batting_order": raw, "source": r["source"],
            "home_score": r["home_score"], "away_score": r["away_score"],
            "starts_at": r["starts_at"],
        })
    return similar_from_rows(parsed, as_dicts, cutoff)


def build_matchup(jg: dict) -> dict:
    """양 팀 확정 타순을 맞댄 사실. 승률·favored를 만들지 않는다."""
    res = jg.get("research") or {}
    intent = jg.get("lineup_intent") or {}
    rec = res.get("lineup_record") or {}

    def _n9(side: str) -> int:
        order = parse_order((res.get(f"{side}_lineup") or {}).get("order"))
        return len(order)

    if _n9("home") < 9 or _n9("away") < 9:
        return {"comparable": False,
                "detail": "양 팀 확정 9명이 없어 타순 대결 불가"}

    def _count(side: str, typ: str) -> int:
        return sum(1 for c in (intent.get("changes") or {}).get(side) or []
                   if c.get("type") == typ)

    def _symbols(side: str) -> dict:
        out = {"▲": 0, "▼": 0, "=": 0, "보류": 0}
        for it in (intent.get("items") or {}).get(side) or []:
            s = it.get("symbol")
            if s in out:
                out[s] += 1
        return out

    h_out, a_out = _count("home", "regular_out"), _count("away", "regular_out")
    if h_out and not a_out:
        gap = f"홈만 주전 이탈 {h_out}건"
    elif a_out and not h_out:
        gap = f"원정만 주전 이탈 {a_out}건"
    elif h_out and a_out:
        gap = f"양 팀 주전 이탈 (홈 {h_out}·원정 {a_out})"
    else:
        gap = "주전 이탈 없음"

    return {
        "comparable": True,
        "home_regular_out": h_out,
        "away_regular_out": a_out,
        "home_symbols": _symbols("home"),
        "away_symbols": _symbols("away"),
        "gap": gap,
        "home_record_line": format_record(rec.get("home")),
        "away_record_line": format_record(rec.get("away")),
        "scoring": intent.get("scoring") or {},
        "handicap": intent.get("handicap") or {},
    }


async def attach(pool, jg: dict, sport: str) -> None:
    """research.lineup_record + lineup_matchup을 얹는다. 실패해도 분석은 산다."""
    res = jg.setdefault("research", {})
    before = jg.get("starts_at")
    records: dict[str, dict] = {}
    for side in ("home", "away"):
        order = (res.get(f"{side}_lineup") or {}).get("order")
        records[side] = await lookup(pool, sport, jg.get(side), order, before)
    res["lineup_record"] = records
    matchup = build_matchup(jg)
    res["lineup_matchup"] = matchup
    jg["lineup_matchup"] = matchup


# Judge 블라인드 평가용 — 점수·종료 상태를 판정 입력에서 뺀다.
_LEAK_KEYS = (
    "home_score", "away_score", "status_label", "picks", "market_board",
    "pick_summary", "breaking_changes", "p_final", "p_legacy", "verdict",
    "combos", "parlays",
)


def strip_outcome_for_judge(jg: dict) -> dict:
    """종료 경기 JSON에서 결과 누수를 제거. 원본은 건드리지 않는다."""
    out = {k: v for k, v in jg.items() if k not in _LEAK_KEYS}
    out["status"] = "scheduled"
    out.pop("home_score", None)
    out.pop("away_score", None)
    return out
