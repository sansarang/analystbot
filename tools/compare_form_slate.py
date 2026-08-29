"""신·구 야구 파이프라인 병행 비교. 발송은 하지 않는다 (구버전 dry-run).

실행:
  PYTHONPATH=. uv run python tools/compare_form_slate.py --old
  PYTHONPATH=. uv run python tools/compare_form_slate.py --sport kbo --old

기본 종목은 오늘 슬레이트 KBO+MLB. 구 Judge는 --old 일 때만 호출한다.
신 판정(matchup)만 analysis 캐시에 남긴다 — 구 Judge 결과를 캐시에 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json

from app.config import get_settings
from app.engine.form_card import rec_label
from app.engine.matchup import clip_p_home
from app.pipeline import default_date, qualifies


STRIP_FOR_OLD = (
    "p_claude", "matchup", "verdict", "judge_pass", "judge_confidence",
    "excluded_picks", "form_unavailable",
)


def _favored(side, p) -> str | None:
    if side in ("home", "away"):
        return side
    if p is None:
        return None
    try:
        return "home" if float(p) >= 0.5 else "away"
    except (TypeError, ValueError):
        return None


def _row(jg: dict, *, prefix: str = "") -> dict:
    m = jg.get("matchup") or {}
    p = m.get("p_home")
    if p is None:
        p = jg.get("p_claude")
    try:
        p = float(p) if p is not None else None
    except (TypeError, ValueError):
        p = None
    side = _favored(m.get("우세"), p)
    rec = rec_label(jg)
    pick = {
        "p": (1 - p) if side == "away" and p is not None else p,
        "sport": jg.get("sport"),
        "pick_state": jg.get("pick_state"),
        "lineup_status": jg.get("lineup_status"),
        "form_unavailable": jg.get("form_unavailable"),
        "required_prob": None,
    }
    s = get_settings()
    if side == "away":
        pick["required_prob"] = s.min_win_prob + s.away_prob_penalty
    key = lambda k: f"{prefix}{k}" if prefix else k
    return {
        key("game_id"): jg.get("game_id"),
        key("matchup"): f"{jg.get('away')} @ {jg.get('home')}",
        key("p_home"): p,
        key("p_home_clipped"): clip_p_home(p) if p is not None else None,
        key("favored"): side,
        key("rec_label"): rec,
        key("qualifies"): qualifies(pick, s) if p is not None else False,
        key("근거"): list(m.get("근거") or []) or None,
        key("verdict"): (jg.get("verdict") or "")[:400] or None,
        key("model"): m.get("model") or jg.get("model"),
        "form_unavailable": bool(jg.get("form_unavailable")),
        "judgement_void": bool(jg.get("judgement_void")),
        "npb_last3_verified": s.npb_last3_verified,
        "pick_state": jg.get("pick_state"),
        "lineup_status": jg.get("lineup_status"),
        "away": jg.get("away"),
        "home": jg.get("home"),
        "sport": jg.get("sport"),
    }


def _games_for_old_judge(games: list[dict]) -> list[dict]:
    out = []
    for g in games:
        c = copy.deepcopy(g)
        for k in STRIP_FOR_OLD:
            c.pop(k, None)
        out.append(c)
    return out


def _old_as_jg(base: dict, verdict: dict) -> dict:
    p = verdict.get("p_claude")
    try:
        p = float(p) if p is not None else None
    except (TypeError, ValueError):
        p = None
    conf = verdict.get("confidence") or "medium"
    return {
        **base,
        "p_claude": p,
        "matchup": {
            "p_home": p,
            "우세": _favored(None, p),
            "근거": [verdict.get("verdict")] if verdict.get("verdict") else [],
        },
        "verdict": verdict.get("verdict") or "",
        "judge_confidence": conf,
        "judge_pass": bool(verdict.get("pass_recommended")),
        "form_unavailable": False,
    }


async def build_new_analysis(sport: str, date: str) -> dict:
    import redis.asyncio as aioredis

    from app.db import get_pool
    from app.pipeline import analysis_cache_ready, build_analysis

    date = date or default_date(sport)
    pool = await get_pool()
    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        raw = await r.get(f"analysis:{sport}:{date}")
        if analysis_cache_ready(raw, date):
            analysis = json.loads(raw)
            live = [g for g in (analysis.get("games") or [])
                    if g.get("status") == "scheduled"]
            if live and all(g.get("matchup") for g in live):
                return analysis
        analysis = await build_analysis(
            pool, sport, date, redis=r, sequential_research=True)
        # 신 판정만 analysis 캐시에 남긴다. card 키는 덮지 않는다(발송 문구 오염 금지).
        await r.set(
            f"analysis:{sport}:{date}",
            json.dumps(analysis, ensure_ascii=False, default=str),
            ex=get_settings().report_cache_ttl,
        )
        return analysis
    finally:
        await r.aclose()


async def run_old_judge(sport: str, date: str, analysis: dict) -> list[dict]:
    """구 Judge dry-run. 텔레그램·캐시 쓰기는 하지 않는다."""
    from app.engine.judge import Judge
    from app.pipeline import _prepare_games_for_judge

    games = [g for g in (analysis.get("games") or [])
             if g.get("status") == "scheduled"]
    payload_games = _games_for_old_judge(games)
    _prepare_games_for_judge(payload_games, sport)
    payload = {
        "date": date, "sport": sport, "games": payload_games,
        "breaking_news": analysis.get("news") or "",
        "instruction": "dry-run 구버전 비교. 발송하지 마라.",
    }
    verdict = await Judge().judge(payload)
    by_id = {g.get("game_id"): g for g in verdict.get("games") or []}
    out = []
    for jg in games:
        v = by_id.get(jg.get("game_id")) or {}
        old_jg = _old_as_jg(jg, v)
        row = _row(old_jg)
        out.append({
            "game_id": jg.get("game_id"),
            "old_p_home": row["p_home"],
            "old_favored": row["favored"],
            "old_rec_label": row["rec_label"],
            "old_qualifies": row["qualifies"],
            "old_verdict": row["verdict"],
            "old_근거": row["근거"],
        })
    return out


def merge_rows(new_games: list[dict], old_rows: list[dict]) -> list[dict]:
    old_by = {r["game_id"]: r for r in old_rows}
    merged = []
    for jg in new_games:
        if jg.get("status") not in (None, "scheduled"):
            continue
        n = _row(jg)
        o = old_by.get(jg.get("game_id")) or {}
        new_f, old_f = n.get("favored"), o.get("old_favored")
        flip = bool(new_f and old_f and new_f != old_f)
        item = {
            "game_id": n["game_id"],
            "sport": n.get("sport"),
            "matchup": n["matchup"],
            "new_p_home": n["p_home"],
            "old_p_home": o.get("old_p_home"),
            "new_favored": new_f,
            "old_favored": old_f,
            "new_rec": n["rec_label"],
            "old_rec": o.get("old_rec_label"),
            "new_model": n.get("model"),
            "favored_flip": flip,
            "pick_state": n.get("pick_state"),
            "lineup_status": n.get("lineup_status"),
        }
        if flip:
            item["new_근거"] = n.get("근거")
            item["old_근거"] = o.get("old_근거") or o.get("old_verdict")
        merged.append(item)
    return merged


def _print_table(rows: list[dict]) -> None:
    print(f"{'경기':<42} {'신 p':>6} {'구 p':>6} {'신우세':>6} {'구우세':>6} "
          f"{'신추천':<8} {'구추천':<8} 뒤집힘")
    for r in rows:
        np_ = r.get("new_p_home")
        op_ = r.get("old_p_home")
        np_s = f"{np_:.3f}" if isinstance(np_, (int, float)) else "-"
        op_s = f"{op_:.3f}" if isinstance(op_, (int, float)) else "-"
        print(f"{(r.get('matchup') or '')[:42]:<42} {np_s:>6} {op_s:>6} "
              f"{str(r.get('new_favored') or '-'):>6} "
              f"{str(r.get('old_favored') or '-'):>6} "
              f"{str(r.get('new_rec') or '-'):<8} "
              f"{str(r.get('old_rec') or '-'):<8} "
              f"{'YES' if r.get('favored_flip') else ''}")


async def run_sport(sport: str, date: str | None, old: bool) -> dict:
    date = date or default_date(sport)
    analysis = await build_new_analysis(sport, date)
    live = [g for g in (analysis.get("games") or [])
            if g.get("status") == "scheduled"]
    old_rows = await run_old_judge(sport, date, analysis) if old else []
    merged = merge_rows(live, old_rows)
    flips = [r for r in merged if r.get("favored_flip")]
    return {
        "sport": sport,
        "date": date,
        "n": len(merged),
        "old_ran": bool(old),
        "favored_flips": len(flips),
        "games": merged,
        "note": "발송은 이 스크립트가 하지 않는다. analysis 캐시는 신 판정만.",
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="all",
                    choices=("kbo", "mlb", "npb", "all"),
                    help="all = 오늘 슬레이트 KBO+NPB+MLB")
    ap.add_argument("--date", default=None)
    ap.add_argument("--old", action="store_true",
                    help="구 Judge를 한 번 호출한다 (크레딧 사용, 발송 없음)")
    args = ap.parse_args()
    sports = ("kbo", "npb", "mlb") if args.sport == "all" else (args.sport,)
    reports = []
    for sp in sports:
        reports.append(await run_sport(sp, args.date, args.old))
    out = {"sports": reports} if len(reports) > 1 else reports[0]
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print()
    for rep in reports:
        print(f"=== {rep['sport']} {rep['date']} n={rep['n']} "
              f"flips={rep['favored_flips']} old_ran={rep['old_ran']} ===")
        _print_table(rep["games"])
        print()


if __name__ == "__main__":
    asyncio.run(main())
