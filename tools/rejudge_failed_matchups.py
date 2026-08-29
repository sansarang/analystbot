"""어제 매치업 JSON 실패 13경기만 재판정. 폼 캐시 재사용, Haiku 금지.

  PYTHONPATH=. uv run python tools/rejudge_failed_matchups.py
"""
from __future__ import annotations

import asyncio
import json

from app.config import get_settings
from app.engine.credit_guard import reset
from app.engine.team_form import LAST_USAGE, load_form

DATE = "2026-08-29"
FAILED = {
    "npb": [1605, 1606, 1608, 1609],
    "mlb": [1450, 1453, 1455, 1460, 1461, 1462, 1464, 1458, 1466],
}


async def _haiku_forbidden(*_a, **_k):
    raise AssertionError("폼 캐시 미스 — Haiku를 부르면 안 된다")


async def main() -> None:
    import redis.asyncio as aioredis

    from app.db import close_pool, get_pool
    from app.engine import team_form as tf
    from app.engine.matchup import judge_matchup
    from app.engine.starter_recent import attach_starter_recent

    reset()
    orig = tf.analyze_team
    tf.analyze_team = _haiku_forbidden
    pool = await get_pool()
    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    rows = []
    usages = []
    try:
        for sport, ids in FAILED.items():
            raw = await r.get(f"analysis:{sport}:{DATE}")
            games = (json.loads(raw).get("games") if raw else None) or []
            by_id = {int(g["game_id"]): g for g in games if g.get("game_id") is not None}
            for gid in ids:
                jg = by_id.get(gid)
                if not jg:
                    rows.append({"sport": sport, "game_id": gid, "error": "analysis 캐시 없음"})
                    continue
                home, away = jg.get("home") or "", jg.get("away") or ""
                hf = await load_form(r, sport, home, DATE)
                af = await load_form(r, sport, away, DATE)
                if not hf or not af:
                    rows.append({
                        "sport": sport, "game_id": gid,
                        "matchup": f"{away} @ {home}",
                        "error": "form 캐시 없음 — Haiku 건너뜀",
                    })
                    continue
                try:
                    await attach_starter_recent(jg, pool)
                except Exception as exc:
                    rows.append({"sport": sport, "game_id": gid, "error": f"등판: {exc}"})
                    continue
                jg.pop("form_unavailable", None)
                jg.pop("matchup", None)
                verdict = await judge_matchup(jg, r, DATE, mock=False)
                u = dict(LAST_USAGE)
                usages.append(u)
                rows.append({
                    "sport": sport,
                    "game_id": gid,
                    "matchup": f"{away} @ {home}",
                    "p_home": (verdict or {}).get("p_home") or jg.get("p_claude"),
                    "우세": (verdict or {}).get("우세"),
                    "확신도": (verdict or {}).get("확신도"),
                    "model": (verdict or {}).get("model") or jg.get("model"),
                    "form_unavailable": bool(jg.get("form_unavailable")),
                    "parse_fail": verdict is None,
                    "tokens": u,
                })
        # 28경기 전체 표: 캐시 analysis + 이번 재판정
        full = []
        for sport in ("kbo", "npb", "mlb"):
            raw = await r.get(f"analysis:{sport}:{DATE}")
            games = (json.loads(raw).get("games") if raw else None) or []
            patched = {x["game_id"]: x for x in rows if x.get("sport") == sport}
            for g in games:
                gid = g.get("game_id")
                if gid in patched and not patched[gid].get("parse_fail") \
                        and patched[gid].get("p_home") is not None:
                    p = patched[gid]
                    full.append({
                        "sport": sport, "game_id": gid,
                        "matchup": p.get("matchup") or f"{g.get('away')} @ {g.get('home')}",
                        "status": g.get("status"),
                        "p_home": p.get("p_home"),
                        "우세": p.get("우세"),
                        "확신도": p.get("확신도"),
                        "model": p.get("model"),
                        "source": "rejudge",
                    })
                else:
                    m = g.get("matchup") or {}
                    full.append({
                        "sport": sport, "game_id": gid,
                        "matchup": f"{g.get('away')} @ {g.get('home')}",
                        "status": g.get("status"),
                        "p_home": m.get("p_home") or g.get("p_claude"),
                        "우세": m.get("우세"),
                        "확신도": m.get("확신도"),
                        "model": m.get("model") or g.get("model"),
                        "source": "cache",
                    })
        ins = [u.get("input_tokens") for u in usages if u.get("input_tokens") is not None]
        outs = [u.get("output_tokens") for u in usages if u.get("output_tokens") is not None]
        out = {
            "rejudge": rows,
            "parse_fail_remaining": sum(1 for x in rows if x.get("parse_fail") or x.get("error")),
            "token_approx": {
                "n": len(usages),
                "input_sum": sum(ins) if ins else None,
                "output_sum": sum(outs) if outs else None,
                "input_avg": (sum(ins) / len(ins)) if ins else None,
                "output_avg": (sum(outs) / len(outs)) if outs else None,
            },
            "slate": full,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    finally:
        tf.analyze_team = orig
        await r.aclose()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
