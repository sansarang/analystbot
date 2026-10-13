"""🔴🔴 **§1 판정 — 폼 창 컵 제외**(지시서 2026-10-13 밤 셋째).

```
PYTHONPATH=. python tools/cup_trial.py           # 재생 + 판정
PYTHONPATH=. python tools/cup_trial.py --load    # 적어 둔 재생으로 판정만
```

🔴🔴 **왜 새 재생이 필요한가** — 백필(`replay_big2`)의 폼 목록은 **리그 경기만**
   이다. 그래서 거기서는 *"컵 제외"* 가 **아무 것도 바꾸지 않는다**(no-op).
   운영이 실제로 받는 목록은 **팀 일정**이고 거기에는 **컵·대륙 대회가 섞인다**
   (실측: 창 5경기 중 J1 **0.84** · K1 0.21). 🔴 그래서 **컵이 섞인 기준**을
   만들어야 "컵을 빼면 좋아지나"를 물을 수 있다.

판 — `B(컵 포함)`(= 운영 모양 · 기준) vs `B(리그만)`(= §1 후보).
판정은 **실행 전 커밋된** `judge_models.passes(rule="season")`((a)~(d)).
🔴 **L1** — 폼 목록은 `fotmob.before_as_of` 로 자른다 · 컵 경기도 **그 경기 앞**만.
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

LEAGUES = (("223", "league:J1"), ("9080", "league:KL1"))
OUT = ROOT / "var/judge/cup_trial.json"


async def cup_rows(net, *, teams: list[str], league: str, state
                   ) -> tuple[dict, str]:
    """🔴 팀마다 **리그 밖 경기**(컵·대륙)를 받아 폼 줄 꼴로 만든다."""
    from app.collect import fotmob as fm
    from app.core import competition as cp
    from app.core import discover as _d
    out: dict[str, list[dict]] = {}
    got_n = miss = 0
    for i, team in enumerate(teams, 1):
        if i % 10 == 0:
            print(f"   … 컵 일정 {i}/{len(teams)}", flush=True)
        said = await _d.pick_team(net, team, ref=None, state=state)
        if not said:
            miss += 1
            continue
        tid, slug = said
        page = await net.get(fm.team_fixtures_url(tid, slug))
        for one in _d.team_fixtures(getattr(page, "text", "") or "", tid):
            if not one.get("finished"):
                continue
            comp = str(one.get("league_name") or "")
            key, _w = cp.key_of(competition=comp)
            if key == league:
                continue                  # 🔴 리그 경기는 백필이 이미 든다
            url = str(one.get("page") or "")
            if not url:
                continue
            got_p = await net.get(fm.BASE + url if url.startswith("/") else url)
            j = fm.payload(getattr(got_p, "text", "") or "")
            if not j:
                continue
            from app.core import backfill as bf
            sc = bf.score_of(j)
            if sc is None:
                continue
            ids = fm.side_ids(j)
            mine_home = (str(ids[0]) == str(tid)) if len(ids) == 2 else None
            if mine_home is None:
                continue
            out.setdefault(team, []).append({
                "utc": str(one.get("utc")), "league": league,
                "league_name": comp, "comp": comp,
                "home_name": str(one.get("home")),
                "away_name": str(one.get("away")),
                "mine_home": mine_home,
                "gf": (sc[0] if mine_home else sc[1]),
                "ga": (sc[1] if mine_home else sc[0]),
                "opp": str(one.get("away") if mine_home else one.get("home")),
                "goals": fm.goals_of(j), "stats": fm.stats_of(j),
                "starters": []})
            got_n += 1
    return out, (f"리그 밖 경기 **{got_n}건**(팀 {len(out)}곳 · 못 찾은 팀 "
                 f"{miss}곳)")


async def replay(net) -> list[dict]:
    from app import rules
    from app.collect import fotmob as fm
    from app.core import backfill as bf
    from app.core import matchup as mu
    from app.core import probmodel as pm
    from app.core import season as se
    from app.core import sim as _sim
    from app.core.legacy import form_input as fi
    from app.core.state import RunState
    state = RunState()
    rows2 = json.loads((ROOT / "var/judge/lineup_rows2.json").read_text(
        encoding="utf-8"))
    out: list[dict] = []
    for lid, name in LEAGUES:
        teams = sorted({r["home"] for r in rows2 if r["league"] == name}
                       | {r["away"] for r in rows2 if r["league"] == name})
        cups, why_cup = await cup_rows(net, teams=teams, league=name,
                                       state=state)
        print(f"· {name} — {why_cup}", flush=True)
        rows = await fm.league_matches(net, lid)
        page0 = await net.get(fm.league_matches_url(lid, "x"))
        seasons = fm.league_seasons(
            fm.payload(getattr(page0, "text", "") or "") or {})
        for season in seasons[1:2]:
            more = await net.get(fm.league_matches_url(lid, "x")
                                 + f"?season={season}")
            j = fm.payload(getattr(more, "text", "") or "") or {}
            pp = ((j.get("props") or {}).get("pageProps") or {})
            for m in (((pp.get("fixtures") or {}).get("allMatches")) or []):
                st = m.get("status") or {}
                rows.append({"id": str(m.get("id") or ""),
                             "home": str((m.get("home") or {}).get("name") or ""),
                             "away": str((m.get("away") or {}).get("name") or ""),
                             "utc": str(st.get("utcTime") or ""),
                             "finished": bool(st.get("finished"))})
        done = sorted([r for r in rows if r.get("finished") and r.get("utc")],
                      key=lambda r: str(r["utc"]))[-500:]
        mean = rules.goal_share(name)
        base_box = rules.goal_baseline(name)
        mul_a, _w = pm.away_mul(home_share=base_box.get("home_share"),
                                per_team=mean)
        share = base_box.get("home_share")
        mul_home = (float(share) / float(mean)) if (share and mean) else 1.0
        conf = dict(mu.table().get("weights") or {})
        beta = float(dict(mu.table().get("lambda_model") or {}).get("beta")
                     or 0.25)
        prior: dict[str, list] = {}
        for i, one in enumerate(done, 1):
            if i % 50 == 0:
                print(f"   … {name} {i}/{len(done)}", flush=True)
            page = await net.get(fm.match_url(str(one.get("id") or "")))
            j = fm.payload(getattr(page, "text", "") or "")
            if not j:
                continue
            score = bf.score_of(j)
            if score is None:
                continue
            h, a = score
            home, away = str(one["home"]), str(one["away"])
            at = datetime.fromisoformat(str(one["utc"]).replace("Z", "+00:00"))
            said_season, _w2 = se.id_of(league=name, when=at)
            probs: dict[str, list[float]] = {}
            mix = {"now": 0, "cup": 0}
            for plate, drop in (("B(컵 포함)", False), ("B(리그만)", True)):
                box = {}
                for side, team in (("home", home), ("away", away)):
                    said = list(prior.get(team) or [])
                    said += [x for x in (cups.get(team) or [])
                             if str(x["utc"]) < str(one["utc"])]
                    said.sort(key=lambda r: str(r["utc"]))
                    kept, _why = fi.pick(said, as_of=at, league=name,
                                         k_min=0, drop_cup=drop)
                    box[side] = kept
                    if not drop:
                        mix["now"] += sum(1 for r in kept[-10:]
                                          if not r.get("league_name")
                                          or r.get("comp") is None)
                        mix["cup"] += sum(1 for r in kept[-10:]
                                          if r.get("league_name"))
                gaps, _why3 = bf.features(j, prior=box, league_mean=mean,
                                          home_mul=mul_home)
                if not gaps:
                    probs[plate] = []
                    continue
                tilt = sum(float(conf.get(k) or 0.0) * float(v)
                           for k, v in gaps.items())
                move = max(-0.35, min(0.35, beta * tilt))
                sim = _sim.run(float(mean) * mul_home * math.exp(move),
                               float(mean) * mul_a * math.exp(-move))
                probs[plate] = [sim.home, sim.draw, sim.away]
            out.append({"league": name, "day": str(one["utc"])[:10],
                        "season": said_season, "home": home, "away": away,
                        "hg": h, "ag": a,
                        "hit": (0 if h > a else (1 if h == a else 2)),
                        "probs": probs, "mix": mix})
            for team, is_home in ((home, True), (away, False)):
                prior.setdefault(team, []).append(
                    {"utc": str(one["utc"]), "league": name,
                     "home_name": home, "away_name": away,
                     "mine_home": is_home, "gf": (h if is_home else a),
                     "ga": (a if is_home else h),
                     "opp": (away if is_home else home),
                     "goals": fm.goals_of(j), "stats": fm.stats_of(j),
                     "starters": []})
    return out


def report(rows: list[dict]) -> int:
    import judge_models as jm

    from app.core import metrics as me
    plates = ("B(컵 포함)", "B(리그만)")
    live = [r for r in rows if all(r["probs"].get(k) for k in plates)]
    print()
    print(f"재생 **{len(rows)}경기** · 두 판 모두 확률이 선 경기 **{len(live)}건**")
    cup = sum(r["mix"]["cup"] for r in live)
    tot = sum(r["mix"]["cup"] + r["mix"]["now"] for r in live)
    print(f"🔴 **폼 창의 리그 밖 비율** — 창에 들어간 줄 {tot}개 중 리그 밖 "
          f"**{cup}개({cup / max(1, tot):.1%})**")
    print()

    def score(name: str, box: list[dict]) -> dict:
        p = [r["probs"][name] for r in box]
        h = [r["hit"] for r in box]
        lls = [me.logloss(pi, hi) for pi, hi in zip(p, h, strict=True)]
        dirs = [bool(me.direction_hit(pi, hi))
                for pi, hi in zip(p, h, strict=True)]
        said = me.bands([{"p": pi, "hit": hi}
                         for pi, hi in zip(p, h, strict=True)], keys=("p",))
        return {"ll": sum(lls) / len(lls), "lls": lls,
                "dir": sum(dirs) / len(dirs), "dirs": dirs,
                "bands": {f: said[f]["p"]["rate"] for f in said}}
    base = score(plates[0], live)
    cand = score(plates[1], live)
    diff = me.paired(cand["lls"], base["lls"])
    b = sum(1 for x, y in zip(cand["dirs"], base["dirs"], strict=True)
            if x and not y)
    c = sum(1 for x, y in zip(cand["dirs"], base["dirs"], strict=True)
            if y and not x)
    pv = jm.binom_two_sided(b, c)
    ok, _box, said = jm.passes(
        diff=diff, dir_rate=cand["dir"], base_dir=base["dir"], p_value=pv,
        bands=cand["bands"], base_bands=base["bands"],
        size={"ll": base["ll"] - cand["ll"], "dir": cand["dir"] - base["dir"],
              "top20": cand["bands"][0.20] - base["bands"][0.20]},
        rule="season")
    print("| 판 | 경기 | 로그 손실 | 방향 | 상위 30/20/10% | 짝지은 차이(95%) |"
          " 맥니마 p |")
    print("|---|---|---|---|---|---|---|")
    for name, got in ((plates[0], base), (plates[1], cand)):
        cells = " / ".join(f"{got['bands'][f]:.2%}" for f in (0.30, 0.20, 0.10))
        print(f"| {name} | {len(live)} | **{got['ll']:.4f}** | "
              f"{got['dir']:.2%} | {cells} | "
              + (f"{diff['mean']:+.4f} ({diff['lo']:+.4f}~{diff['hi']:+.4f})"
                 f" | {pv:.4f} |" if name == plates[1] else " — | — |"))
    print()
    print(("✅ **채택 — 컵 제외**" if ok else "🔴 **탈락 — 컵 포함 유지**")
          + " " + said)
    return 0


async def main(argv: list[str]) -> int:
    from app.net import Net
    net = Net(cache=True)
    print("# 🔴🔴 §1 폼 창 컵 제외 — 판정")
    print()
    if "--load" in argv[1:] and OUT.exists():
        rows = json.loads(OUT.read_text(encoding="utf-8"))
        print(f"🔴 적어 둔 재생 {len(rows)}경기를 읽었다")
    else:
        rows = await replay(net)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"🔴 재생 **{len(rows)}경기**를 적었다 — {OUT}")
    return report(rows)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
