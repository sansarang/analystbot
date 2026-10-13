"""🔴🔴 **§3·§4 시즌 문맥 후보 시험**(통합 지시서 2026-10-13 밤).

```
PYTHONPATH=. python tools/season_trial.py            # S1 (폼 입력)
PYTHONPATH=. python tools/season_trial.py --stage s2 # S2-M1 (seasonfix)
```

판 — **S1**: `B` · `M1s(k_min=3)` · `M1s(k_min=5)` · `M1s+가중 축소`
판정은 **실행 전 커밋된** `judge_models.passes(rule="season")`((a)~(d)).

🔴 **M1 은 K0 고정**이다 — 바꾸는 것은 `old_engine` 에 넘기는 **폼 목록**뿐이다
   (`legacy.form_input.pick`). 🔴 λ 식·계수·홈 배율은 백필과 **같은 수**를 쓴다.
🔴 시즌 교차는 **규칙 표**(`season.id_of`)로 가른다 — 옛 간격 탐지는 K1 2026 을
   둘로 쪼갰다(실측 2026-10-13).
🔴 **L1** — 특징은 그 경기 **앞** 경기로만 만든다(`prior` 를 경기 뒤에 더한다).
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 리그 — 백필과 같은 둘(목록 해시를 맞춘다)
LEAGUES = (("223", "league:J1"), ("9080", "league:KL1"))

#: 🔴 S1 판 — 지시서 §3 그대로
PLATES: tuple[tuple[str, dict], ...] = (
    ("B", {}),
    ("M1s(k3)", {"k_min": 3}),
    ("M1s(k5)", {"k_min": 5}),
    ("M1s(k5)+가중축소", {"k_min": 5, "weak": True}),
)


async def replay(net, *, limit: int = 500) -> list[dict]:
    """🔴 두 리그를 시간 순으로 재생하며 **판마다** 확률을 만든다."""
    from app import rules
    from app.collect import fotmob as fm
    from app.core import backfill as bf
    from app.core import matchup as mu
    from app.core import probmodel as pm
    from app.core import season as se
    from app.core import sim as _sim
    from app.core.legacy import form_input as fi
    out: list[dict] = []
    for lid, name in LEAGUES:
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
                      key=lambda r: str(r["utc"]))[-int(limit):]
        print(f"· {name} — 끝난 경기 {len(done)}건", flush=True)
        mean = rules.goal_share(name)
        base_box = rules.goal_baseline(name)
        mul_h, _w = pm.away_mul(home_share=base_box.get("home_share"),
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
            at = _at(str(one["utc"]))
            got_season, _w2 = se.id_of(league=name, when=at)
            said: dict[str, list[float]] = {}
            fills: dict[str, int] = {}
            for plate, opt in PLATES:
                box = {}
                for side, team in (("home", home), ("away", away)):
                    mine = list(prior.get(team) or [])
                    if not opt:
                        box[side] = mine
                        continue
                    kept, _why = fi.pick(mine, as_of=at, league=name,
                                         k_min=int(opt["k_min"]),
                                         weak=bool(opt.get("weak")))
                    box[side] = kept
                    fills[plate] = fills.get(plate, 0) + sum(
                        1 for r in kept if r.get("filled"))
                gaps, _why3 = bf.features(j, prior=box, league_mean=mean,
                                          home_mul=mul_home)
                if not gaps:
                    said[plate] = []
                    continue
                tilt = sum(float(conf.get(k) or 0.0) * float(v)
                           for k, v in gaps.items())
                move = max(-0.35, min(0.35, beta * tilt))
                sim = _sim.run(float(mean) * mul_home * math.exp(move),
                               float(mean) * mul_h * math.exp(-move))
                said[plate] = [sim.home, sim.draw, sim.away]
            out.append({"league": name, "day": str(one["utc"])[:10],
                        "utc": str(one["utc"]), "season": got_season,
                        "home": home, "away": away, "hg": h, "ag": a,
                        "hit": (0 if h > a else (1 if h == a else 2)),
                        "probs": said, "fills": fills,
                        "early": _early(prior, home, away)})
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


def _at(said: str):
    from datetime import datetime
    return datetime.fromisoformat(said.replace("Z", "+00:00"))


def _early(prior: dict, home: str, away: str, cut: int = 6) -> bool:
    """🔴 **시즌 초** — 두 팀 중 하나라도 이번 시즌 경기 수가 `cut` 이하인가."""
    return min(len(prior.get(home) or []), len(prior.get(away) or [])) <= cut


def report(rows: list[dict], plates=PLATES) -> int:
    """🔴 판정 — 1절 규칙((a)~(d) · `rule="season"`)."""
    import judge_models as jm

    from app.core import metrics as me
    live = [r for r in rows if all(r["probs"].get(k) for k, _o in plates)]
    print()
    print(f"재생 **{len(rows)}경기** · 네 판 모두 확률이 선 경기 **{len(live)}건**")
    seasons = sorted({r["season"] for r in live})
    print(f"시즌 {len(seasons)}개 — {' · '.join(seasons)} · "
          f"시즌 초(≤6경기) {sum(1 for r in live if r['early'])}건")
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
    base = score("B", live)
    print("| 판 | 경기 | 로그 손실 | 방향 | 상위 30/20/10% 평균 | 짝지은 차이(95%)"
          " | 맥니마 p | 판정 |")
    print("|---|---|---|---|---|---|---|---|")
    picks: list[dict] = []
    for name, _opt in plates:
        got = score(name, live)
        avg = sum(got["bands"].values()) / len(got["bands"])
        cells = " / ".join(f"{got['bands'][f]:.2%}" for f in (0.30, 0.20, 0.10))
        if name == "B":
            print(f"| **B** | {len(live)} | **{got['ll']:.4f}** | "
                  f"{got['dir']:.2%} | {avg:.2%}({cells}) | — | — | **기준** |")
            continue
        diff = me.paired(got["lls"], base["lls"])
        b = sum(1 for x, y in zip(got["dirs"], base["dirs"], strict=True)
                if x and not y)
        c = sum(1 for x, y in zip(got["dirs"], base["dirs"], strict=True)
                if y and not x)
        pv = jm.binom_two_sided(b, c)
        base_avg = sum(base["bands"].values()) / len(base["bands"])
        ok, _box, why = jm.passes(
            diff=diff, dir_rate=got["dir"], base_dir=base["dir"],
            p_value=pv, bands=got["bands"], base_bands=base["bands"],
            size={"ll": base["ll"] - got["ll"],
                  "dir": got["dir"] - base["dir"],
                  "top20": got["bands"][0.20] - base["bands"][0.20]},
            rule="season")
        picks.append({"name": name, "ll": got["ll"], "ok": ok})
        print(f"| {name} | {len(live)} | {got['ll']:.4f} | {got['dir']:.2%} | "
              f"{avg:.2%}({cells}) · 기준 {base_avg:.2%} | "
              f"{diff['mean']:+.4f} ({diff['lo']:+.4f}~{diff['hi']:+.4f}) | "
              f"{pv:.4f} | " + ("✅ **채택**" if ok else "🔴 탈락")
              + f" {why} |")
    print()
    # 🔴 **시즌 초 6라운드 이내만** 따로(이 수정이 노리는 구간)
    early = [r for r in live if r["early"]]
    if early:
        print("## 🔴 시즌 초(≤6경기)만")
        print()
        print("| 판 | 경기 | 로그 손실 | 방향 |")
        print("|---|---|---|---|")
        for name, _opt in plates:
            got = score(name, early)
            print(f"| {name} | {len(early)} | {got['ll']:.4f} | "
                  f"{got['dir']:.1%} |")
        print()
    fills = {}
    for r in live:
        for k, v in dict(r.get("fills") or {}).items():
            fills[k] = fills.get(k, 0) + int(v)
    print("- 지난 시즌에서 **채운 경기 수**(판별 합계) — "
          + " · ".join(f"{k} {v}" for k, v in sorted(fills.items())))
    said_ok = [x for x in picks if x["ok"]]
    print()
    if said_ok:
        best = min(said_ok, key=lambda x: x["ll"])
        print(f"🔴🔴 **판정 — 채택: {best['name']}**(통과 "
              f"{[x['name'] for x in said_ok]} 중 로그 손실 최저)")
    else:
        print("🔴🔴 **판정 — B 유지**((a)~(d) 를 전부 통과한 판이 없다)")
    return 0


async def main(argv: list[str]) -> int:
    from app.net import Net
    net = Net(cache=True)
    out = ROOT / "var/judge/season_trial.json"
    print("# 🔴🔴 §3 S1 — 이번 시즌 우선 폼")
    print()
    if "--load" in argv[1:] and out.exists():
        rows = json.loads(out.read_text(encoding="utf-8"))
        print(f"🔴 적어 둔 재생 {len(rows)}경기를 읽었다 — {out}")
    else:
        rows = await replay(net)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"🔴 재생 **{len(rows)}경기**를 적었다 — {out}")
    return report(rows)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
