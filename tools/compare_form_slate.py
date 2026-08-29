"""신·구 야구 파이프라인 병행 비교. 발송은 하지 않는다 (구버전 dry-run).

실행: PYTHONPATH=. uv run python tools/compare_form_slate.py --sport kbo
      PYTHONPATH=. uv run python tools/compare_form_slate.py --sport mlb

구 Judge는 --old 일 때만 호출한다. 기본은 캐시의 신 판정만 출력한다.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.engine.form_card import rec_label
from app.engine.matchup import clip_p_home
from app.pipeline import default_date, qualifies


def _row(jg: dict) -> dict:
    m = jg.get("matchup") or {}
    p = jg.get("p_claude")
    try:
        p = float(p) if p is not None else None
    except (TypeError, ValueError):
        p = None
    side = m.get("우세")
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
    return {
        "game_id": jg.get("game_id"),
        "matchup": f"{jg.get('away')} @ {jg.get('home')}",
        "p_home": p,
        "p_home_clipped": clip_p_home(p) if p is not None else None,
        "favored": side,
        "rec_label": rec,
        "qualifies": qualifies(pick, s) if p is not None else False,
        "form_unavailable": bool(jg.get("form_unavailable")),
        "judgement_void": bool(jg.get("judgement_void")),
        "npb_last3_verified": s.npb_last3_verified,
    }


async def from_cache(sport: str, date: str | None) -> list[dict]:
    import redis.asyncio as aioredis

    date = date or default_date(sport)
    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        raw = await r.get(f"analysis:{sport}:{date}")
    finally:
        await r.aclose()
    if not raw:
        return []
    analysis = json.loads(raw)
    return [_row(g) for g in analysis.get("games") or []
            if (g.get("sport") or sport) in ("kbo", "npb", "mlb")]


async def run_old_judge(sport: str, date: str | None) -> list[dict]:
    """구 Judge dry-run. 텔레그램은 보내지 않는다."""
    from app.engine.judge import Judge
    from app.pipeline import ensure_analysis_cache

    date = date or default_date(sport)
    analysis = await ensure_analysis_cache(sport, date)
    games = analysis.get("games") or []
    payload = {
        "date": date, "sport": sport, "games": games,
        "breaking_news": analysis.get("news") or "",
        "instruction": "dry-run 구버전 비교. 발송하지 마라.",
    }
    verdict = await Judge().judge(payload)
    by_id = {g.get("game_id"): g for g in verdict.get("games") or []}
    out = []
    for jg in games:
        v = by_id.get(jg.get("game_id")) or {}
        out.append({
            "game_id": jg.get("game_id"),
            "matchup": f"{jg.get('away')} @ {jg.get('home')}",
            "old_p_claude": v.get("p_claude"),
            "old_verdict": (v.get("verdict") or "")[:80],
        })
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="kbo", choices=("kbo", "mlb", "npb"))
    ap.add_argument("--date", default=None)
    ap.add_argument("--old", action="store_true",
                    help="구 Judge를 한 번 호출한다 (크레딧 사용, 발송 없음)")
    args = ap.parse_args()
    new_rows = await from_cache(args.sport, args.date)
    old_rows = await run_old_judge(args.sport, args.date) if args.old else []
    old_by = {r["game_id"]: r for r in old_rows}
    merged = []
    for r in new_rows:
        o = old_by.get(r["game_id"]) or {}
        merged.append({**r, **{k: v for k, v in o.items() if k != "game_id"}})
    print(json.dumps({
        "sport": args.sport,
        "n": len(merged),
        "games": merged,
        "old_ran": bool(args.old),
        "note": "발송은 이 스크립트가 하지 않는다",
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
