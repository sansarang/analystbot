"""신 야구 파이프라인 슬레이트 비교. 발송은 하지 않는다.

실행:
  PYTHONPATH=. uv run python tools/compare_form_slate.py
  PYTHONPATH=. uv run python tools/compare_form_slate.py --sport kbo

구 Judge(--old)는 다시 돌리지 않는다. KBO 대조는
tools/baselines/form_compare_old_kbo_2026-08-29.json 고정값.
400이 나면 남은 리그를 돌리지 않고 진행 지점을 보고한다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from app.collectors.base import ApiQuotaError
from app.config import get_settings
from app.engine.form_card import rec_label
from app.engine.matchup import clip_p_home
from app.engine.pregame_push import still_upcoming
from app.pipeline import default_date, qualifies


def live_games(analysis: dict) -> list[dict]:
    """비교 대상 = 아직 **시작하지 않은** 예정 경기.

    ⚠️ `status == "scheduled"` 만 보면 안 된다. 종료 점수 적재가 돌기 전까지
       진행 중인 경기도 DB에 scheduled 로 남아 있다 — 실측 2026-08-30 NPB
       드라이런에서 이미 1회초가 진행 중이던 니혼햄전이 '추천' 라벨을 받았다.
       실운영 발송은 `still_upcoming` 으로 막는데(pregame_push:87, :259) 검증
       도구만 안 막으면, 도구가 실운영과 다른 규칙으로 돌아 결과를 오염시킨다.
    """
    return [g for g in (analysis.get("games") or [])
            if g.get("status") == "scheduled"
            and still_upcoming(g.get("starts_at") or g.get("starts_at_kst"))]


BASELINE_PATH = (
    Path(__file__).resolve().parent / "baselines"
    / "form_compare_old_kbo_2026-08-29.json"
)


def _gid(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return x


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
        key("확신도"): m.get("확신도") or jg.get("judge_confidence"),
        "form_unavailable": bool(jg.get("form_unavailable")),
        "judgement_void": bool(jg.get("judgement_void")),
        "npb_last3_verified": s.npb_last3_verified,
        "pick_state": jg.get("pick_state"),
        "lineup_status": jg.get("lineup_status"),
        "away": jg.get("away"),
        "home": jg.get("home"),
        "sport": jg.get("sport"),
    }


def load_frozen_old_kbo(date: str) -> list[dict]:
    """구 Judge를 다시 부르지 않는다. 2026-08-29 KBO 5경기 고정값."""
    blob = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if blob.get("date") != date:
        return []
    out = []
    for g in blob.get("games") or []:
        out.append({
            "game_id": g["game_id"],
            "old_p_home": g.get("old_p_home"),
            "old_favored": g.get("old_favored"),
            "old_rec_label": None,
            "old_qualifies": None,
            "old_verdict": None,
            "old_근거": None,
            "old_source": "frozen",
        })
    return out


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
            live = live_games(analysis)
            if live and all(g.get("matchup") for g in live):
                return analysis
        analysis = await build_analysis(
            pool, sport, date, redis=r, sequential_research=True)
        await r.set(
            f"analysis:{sport}:{date}",
            json.dumps(analysis, ensure_ascii=False, default=str),
            ex=get_settings().report_cache_ttl,
        )
        return analysis
    finally:
        await r.aclose()


def merge_rows(new_games: list[dict], old_rows: list[dict]) -> list[dict]:
    old_by = {_gid(r["game_id"]): r for r in old_rows}
    merged = []
    for jg in new_games:
        if jg.get("status") not in (None, "scheduled"):
            continue
        if jg.get("starts_at") and not still_upcoming(jg["starts_at"]):
            continue          # 이미 시작한 경기는 비교 대상이 아니다
        n = _row(jg)
        o = old_by.get(_gid(jg.get("game_id"))) or {}
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
            "new_확신도": n.get("확신도"),
            "form_unavailable": n.get("form_unavailable"),
            "favored_flip": flip,
            "pick_state": n.get("pick_state"),
            "lineup_status": n.get("lineup_status"),
        }
        if flip:
            item["new_근거"] = n.get("근거")
            item["old_근거"] = o.get("old_근거") or o.get("old_verdict")
        merged.append(item)
    return merged


def clip_confidence_dist(rows: list[dict], live: list[dict]) -> dict:
    clips = Counter()
    conf = Counter()
    for r in rows:
        p = r.get("new_p_home")
        if p is None:
            clips["null"] += 1
        else:
            val = float(p)
            if val <= 0.3200001:
                clips["at_floor_0.32"] += 1
            elif val >= 0.6799999:
                clips["at_ceil_0.68"] += 1
            else:
                clips["interior"] += 1
    for jg in live:
        m = jg.get("matchup") or {}
        c = m.get("확신도") or jg.get("judge_confidence") or "none"
        conf[str(c)] += 1
    return {"clip": dict(clips), "confidence": dict(conf)}


async def inspect_redis(date: str) -> dict:
    import redis.asyncio as aioredis

    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    form_ok, form_fail, analysis = [], [], []
    try:
        async for key in r.scan_iter(match=f"form:*:{date}"):
            raw = await r.get(key)
            try:
                obj = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                obj = {}
            parts = key.split(":")
            league = parts[1] if len(parts) > 1 else "?"
            team = ":".join(parts[2:-1]) if len(parts) > 3 else "?"
            row = {
                "key": key, "league": league, "team": team,
                "model": obj.get("model"),
                "unavailable": bool(obj.get("unavailable")),
                "cause": obj.get("cause"),
            }
            if obj.get("unavailable"):
                form_fail.append(row)
            else:
                form_ok.append(row)
        async for key in r.scan_iter(match=f"analysis:*:*:{date}"):
            raw = await r.get(key)
            try:
                obj = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                obj = {}
            analysis.append({
                "key": key, "model": obj.get("model"),
                "p_home": obj.get("p_home"),
            })
    finally:
        await r.aclose()
    fail_by = {}
    for row in form_fail:
        k = f"{row['league']}:{row.get('cause') or 'unknown'}"
        fail_by[k] = fail_by.get(k, 0) + 1
    form_models = sorted({x["model"] for x in form_ok if x.get("model")})
    analysis_models = sorted({x["model"] for x in analysis if x.get("model")})
    return {
        "form_ok": len(form_ok),
        "form_fail": len(form_fail),
        "form_models": form_models,
        "analysis_n": len(analysis),
        "analysis_models": analysis_models,
        "fail_by_league_cause": fail_by,
        "form_fail_rows": form_fail,
        "form_ok_sample": [
            {"league": x["league"], "team": x["team"], "model": x["model"]}
            for x in form_ok
        ],
    }


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


async def run_sport(sport: str, date: str | None) -> dict:
    date = date or default_date(sport)
    analysis = await build_new_analysis(sport, date)
    live = live_games(analysis)
    old_rows = load_frozen_old_kbo(date) if sport == "kbo" else []
    old_source = "frozen_kbo" if old_rows else "none"
    merged = merge_rows(live, old_rows)
    flips = [r for r in merged if r.get("favored_flip")]
    return {
        "sport": sport,
        "date": date,
        "n": len(merged),
        "old_ran": False,
        "old_source": old_source,
        "favored_flips": len(flips),
        "dist": clip_confidence_dist(merged, live),
        "games": merged,
        "note": "발송은 이 스크립트가 하지 않는다. analysis 캐시는 신 판정만.",
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="all",
                    choices=("kbo", "mlb", "npb", "all"),
                    help="all = 오늘 슬레이트 KBO+NPB+MLB")
    ap.add_argument("--date", default=None)
    args = ap.parse_args()
    from app.engine.credit_guard import reset, stopped_at

    reset()
    sports = ("kbo", "npb", "mlb") if args.sport == "all" else (args.sport,)
    reports = []
    aborted = None
    date = args.date
    for sp in sports:
        try:
            reports.append(await run_sport(sp, args.date))
            if reports[-1].get("date"):
                date = reports[-1]["date"]
        except ApiQuotaError as exc:
            from app.engine.credit_guard import stopped_at as _at

            aborted = {
                "error": "ApiQuotaError",
                "at": _at() or stopped_at(),
                "sport": sp,
                "done_sports": [r["sport"] for r in reports],
                "detail": str(exc),
            }
            print(f"[credit] 즉시 중단 sport={sp} at={aborted['at']}: {exc}",
                  flush=True)
            break
    date = date or default_date("kbo")
    cache = await inspect_redis(date)
    out = {
        "sports": reports,
        "aborted": aborted,
        "redis": cache,
        "note": "발송 없음. 구 Judge 재호출 없음.",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print()
    for rep in reports:
        print(f"=== {rep['sport']} {rep['date']} n={rep['n']} "
              f"flips={rep['favored_flips']} old={rep.get('old_source')} ===")
        _print_table(rep["games"])
        print(f"clip/conf: {rep.get('dist')}")
        print()
    if aborted:
        print(f"=== ABORTED {aborted} ===")
    print(f"=== redis form_ok={cache['form_ok']} form_fail={cache['form_fail']} "
          f"form_models={cache['form_models']} "
          f"analysis_models={cache['analysis_models']} ===")
    print(f"fail_by: {cache['fail_by_league_cause']}")


if __name__ == "__main__":
    asyncio.run(main())
