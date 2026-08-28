"""8/27 KBO — 결과를 모른다고 가정하고 확정 타순으로 예측한 뒤 채점한다.

누수 방어:
  - 전적은 `starts_at` 이전 박스스코어만.
  - Judge 페이로드에서 점수·종료 상태·기존 판정을 제거.
  - 오늘 등판 선발의 시즌 ERA는 넣지 않는다.
  - 팀 OBP는 시즌 누적이라 1경기가 섞일 수 있다 — 보고에 적는다.

사용:
  PYTHONPATH=. uv run python tools/eval_kbo_lineup_blind.py --dump /tmp/kbo_827_dump.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _hit(pred_home: float, hs: int, aws: int) -> str | None:
    if hs == aws:
        return None
    if pred_home == 0.5:
        return "push"
    return "hit" if (pred_home > 0.5) == (hs > aws) else "miss"


def _rate(rows: list[str]) -> str:
    rows = [x for x in rows if x and x != "push"]
    h, m = rows.count("hit"), rows.count("miss")
    n = h + m
    return "n=0" if not n else f"{h}/{n} = {h / n:.1%}"


def _order(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            pass
    return raw if isinstance(raw, list) else []


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-08-27")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()

    from app.config import get_settings
    from app.collectors import kbo_stats
    from app.collectors.lineup_history import _as_dt
    from app.engine.lineup_diff import (diff_lineup, merge_absences_from_diff,
                                        parse_order, usual_from)
    from app.engine.lineup_record import (build_matchup, format_record,
                                          similar_from_rows,
                                          strip_outcome_for_judge)
    from app.engine.scoring import game_distribution

    blob = json.loads(Path(args.dump).read_text())
    games = [g for g in blob["games"]
             if g.get("home_score") is not None]
    history, today_ev = blob["history"], blob.get("today_events") or []
    print(f"날짜 {args.date} KBO 종료·점수 있는 경기 {len(games)}건")

    settings = get_settings()
    teams = await kbo_stats.fetch_team_stats()
    pitchers = await kbo_stats.fetch_pitcher_stats()

    payloads, actuals = [], []
    for g in games:
        gid, home, away = g["id"], g["home"], g["away"]
        hs, aws = int(g["home_score"]), int(g["away_score"])
        starts = g["starts_at"]
        actuals.append({"id": gid, "home": home, "away": away, "hs": hs, "aws": aws})

        def today(side):
            for e in today_ev:
                if e["game_id"] == gid and e["side"] == side:
                    return _order(e["batting_order"])
            return []

        ho, ao = today("home"), today("away")
        res = {"home_pitcher": {"name": g.get("home_pitcher") or ""},
               "away_pitcher": {"name": g.get("away_pitcher") or ""},
               "home_lineup": {"order": ho}, "away_lineup": {"order": ao}}
        kbo_stats.merge_into_research(res, {"home": home, "away": away},
                                      teams, pitchers)
        for side in ("home", "away"):
            blk = res.get(f"{side}_pitcher") or {}
            blk.pop("era_season", None)
            blk.pop("era_recent", None)
            blk.pop("whip", None)

        jg = {
            "game_id": gid, "sport": "kbo", "league": "KBO",
            "home": home, "away": away, "starts_at": str(starts),
            "status": "scheduled", "research": res,
            "lineup_intent": {"changes": {}, "items": {}, "headline": {}},
        }
        recs = {}
        for side, team, raw in (("home", home, ho), ("away", away, ao)):
            order = parse_order(raw)
            past, rows = [], []
            for e in history:
                if e.get("team") != team:
                    continue
                st, cut = _as_dt(e["starts_at"]), _as_dt(starts)
                if st is None or cut is None or st >= cut:
                    continue
                past.append(parse_order(e["batting_order"]))
                rows.append({
                    "game_id": e["game_id"], "side": e["side"],
                    "batting_order": _order(e["batting_order"]),
                    "source": e.get("source") or "boxscore",
                    "home_score": e.get("home_score"),
                    "away_score": e.get("away_score"),
                    "starts_at": e["starts_at"],
                })
            u = usual_from(past[:10])
            recs[side] = similar_from_rows(order, rows, starts)
            changes = diff_lineup(order, u) if (order and u) else []
            jg["lineup_intent"]["changes"][side] = changes
            jg["lineup_intent"]["headline"][side] = (
                f"평소 대비 변경 {len(changes)}건" if changes else "평소 대비 변경 없음")
            merge_absences_from_diff(res, team, changes, u)
        res["lineup_record"] = recs
        jg["lineup_matchup"] = build_matchup(jg)
        res["lineup_matchup"] = jg["lineup_matchup"]
        dist = game_distribution(jg, res, "kbo", settings)
        p_model = dist["probs"]["h2h"]["home"] if dist else None
        jg["p_model"] = p_model
        jg["model_valid"] = dist is not None
        if dist:
            jg["lam"] = {"home": dist["lam"].home, "away": dist["lam"].away}
        payloads.append(jg)
        mu = jg["lineup_matchup"]
        print(f"\n{away} @ {home}  실제 {aws}-{hs}  "
              f"{'홈승' if hs > aws else '원정승' if aws > hs else '무'}")
        print(f"  홈9 {len(ho)} · 원정9 {len(ao)} · {mu.get('gap') or mu.get('detail')}")
        print(f"  홈 {format_record(recs.get('home'))}")
        print(f"  원정 {format_record(recs.get('away'))}")
        print(f"  λ p_home={p_model}"
              + (f"  λ={jg['lam']}" if jg.get("lam") else ""))

    rec_marks, lam_marks = [], []
    for jg, act in zip(payloads, actuals):
        rec = (jg.get("research") or {}).get("lineup_record") or {}
        hp = (rec.get("home") or {}).get("win_pct")
        ap = (rec.get("away") or {}).get("win_pct")
        if hp is not None and ap is not None and hp != ap:
            rec_marks.append(_hit(0.51 if hp > ap else 0.49, act["hs"], act["aws"]))
        if jg.get("p_model") is not None:
            lam_marks.append(_hit(float(jg["p_model"]), act["hs"], act["aws"]))
    print("\n--- 채점 (무승부·p=0.5 제외) ---")
    print("타순 전적 대결(양쪽 승률 있을 때만):", _rate(rec_marks))
    print("λ p_model:", _rate(lam_marks))

    if args.no_judge:
        return 0

    from app.engine.judge import Judge
    inst = ("이 경기는 아직 시작하지 않았다. 입력에 없는 경기 결과를 떠올리거나 "
            "쓰지 마라. lineup_matchup과 lineup_record를 경기력으로 반영하라. "
            "표본 3경기 미만 전적은 승률 근거로 쓰지 마라.")
    judge_games = []
    for jg in payloads:
        p = strip_outcome_for_judge(jg)
        p["instruction"] = inst
        judge_games.append(p)
    verdict = await Judge().judge({
        "date": args.date, "sport": "kbo", "games": judge_games,
        "breaking_news": "", "instruction": inst,
    })
    by_id = {v["game_id"]: v for v in (verdict.get("games") or [])}
    claude_marks, final_marks = [], []
    print("\n--- Judge ---")
    for jg, act in zip(payloads, actuals):
        v = by_id.get(jg["game_id"]) or {}
        pc, pm = v.get("p_claude"), jg.get("p_model")
        pf = None
        if pc is not None and pm is not None:
            pf = 0.5 * float(pm) + 0.5 * float(pc)
        elif pc is not None:
            pf = float(pc)
        print(f"{act['away']} @ {act['home']}  p_claude={pc}  p_final={pf}  "
              f"{(v.get('verdict') or '')[:100]}")
        if pc is not None:
            claude_marks.append(_hit(float(pc), act["hs"], act["aws"]))
        if pf is not None:
            final_marks.append(_hit(float(pf), act["hs"], act["aws"]))
    print("p_claude:", _rate(claude_marks))
    print("p_final 0.5λ+0.5Claude:", _rate(final_marks))
    print("한계: 팀 OBP는 시즌 누적이라 해당일 1경기가 섞일 수 있다. "
          "선발 ERA는 뺐다. Claude가 그 날 결과를 기억하면 수치가 부풀 수 있다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
