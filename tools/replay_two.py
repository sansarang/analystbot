"""🔴🔴 **§17 재현 — 실사고 두 경기**(as-of 킥오프 전) — 지시서 2026-10-12(둘째).

```
PYTHONPATH=. python tools/replay_two.py
```

> 광주–울산(10-11) · 가와사키–나고야(10-11): 단계별 전후표 — 바닥 점수 차 ·
> pdiff · absΔ · restΔ · loadΔ · cupΔ · pb_home · form3Δ · benchΔ · 항별 λ 기여 ·
> λ · 확률 · 역배·보호 줄 · 경고 S·등급 · 판정 행동.
> **결과 줄은 맨 끝.** 두 경기에 맞추려고 고치지 않는다. 🔴 안 바뀌면 안 바뀐
> 그대로, **어느 항이 왜 0이었는지** 적는다.

🔴 모든 수는 **킥오프 이전**만 본다(L1 · 문은 `fotmob.before_as_of` 하나).
🔴 계수 판이 없으면 그 항은 **0 이고 그 사실을 적는다**(손값 금지 · §0).
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 두 경기 — fotmob 경기 id 와 리그 id(실측으로 확인한 것만)
CASES = (
    {"name": "광주 vs 울산", "league": "league:KL1", "lid": "9080",
     "mid": "5140047", "home": "Gwangju FC", "away": "Ulsan HD FC"},
    {"name": "가와사키 vs 나고야", "league": "league:J1", "lid": "223",
     "mid": "", "home": "Kawasaki Frontale", "away": "Nagoya Grampus"},
)


async def _games(net, lid: str, *, seasons: int = 2) -> list[dict]:
    from fit_ratings import games_of
    return await games_of(net, lid, seasons=seasons)


async def one(case: dict, *, net) -> None:
    from app.collect import fotmob as fm
    from app.core import context as _ctx
    from app.core import probfloor as _pf
    from app.core import ratings as _r
    from app.core import underdog as _ud
    from app.core import upset as _up
    from app.core import versions as _v
    print(f"## {case['name']}")
    print()
    rows = await _games(net, case["lid"])
    # 🔴 그 경기를 목록에서 찾는다(이름으로 — 실측으로 확인한 이름만 쓴다)
    said = [r for r in rows
            if r["home"] == case["home"] and r["away"] == case["away"]]
    if not said:
        print(f"🔴 **그 경기를 목록에서 못 찾았다** — `{case['home']}` vs "
              f"`{case['away']}`(받은 경기 {len(rows)}건) · 이 칸은 **비운다**")
        print()
        return
    game = sorted(said, key=lambda r: str(r["utc"]))[-1]
    kick = datetime.fromisoformat(str(game["utc"]).replace("Z", "+00:00"))
    print(f"- 킥오프 **{kick:%Y-%m-%d %H:%M}Z** · as-of = 그 시각")
    before = fm.before_as_of(rows, as_of=kick, key="utc")
    print(f"- 쓸 수 있는 지난 경기 **{len(before)}건**(킥오프 이전만 · L1)")
    print()
    # ── ③ 바닥 점수 — 세 후보를 **판이 있는 것만** 센다
    print("| 바닥 점수 | 홈 | 원정 | 차 | 판 |")
    print("|---|---|---|---|---|")
    diffs: dict[str, float] = {}
    for name in ("elo", "elog", "pi"):
        mod = __import__(f"app.core.ratings.{name}", fromlist=["x"])
        p = _r.load_params(name, league=case["league"], as_of=kick)
        table = mod.rate(before, params=p, as_of=kick)
        h, _w1 = table.of(case["home"])
        a, _w2 = table.of(case["away"])
        d = float(mod.prob_input(case["home"], case["away"], table))
        diffs[name] = d
        print(f"| {name} | {h:+.2f} | {a:+.2f} | **{d:+.3f}** | "
              + ("🔴 **임시 학습률**(판 없음)" if p.provisional
                 else f"{p.ver}") + " |")
    print()
    # ── §7 경기 직전 상태
    ctx_rows = {}
    for side in ("home", "away"):
        mine = [r for r in before
                if r["home"] == case[side] or r["away"] == case[side]]
        said_rows = [{"utc": r["utc"], "comp": "league",
                      "gf": (r["hg"] if r["home"] == case[side] else r["ag"]),
                      "ga": (r["ag"] if r["home"] == case[side] else r["hg"])}
                     for r in mine]
        ctx_rows[side] = _ctx.row_of(case[side], said_rows, as_of=kick)
        print(f"- **{case[side]}** — {ctx_rows[side].why}")
    cov = dict(_ctx.covariates(ctx_rows["home"], ctx_rows["away"]))
    print()
    print("| 공변량 | 값 | 왜 그 값인가 |")
    print("|---|---|---|")
    print(f"| restΔ | {cov['rest_d']:+.1f} | 홈 휴식 "
          f"{ctx_rows['home'].rest_days} − 원정 {ctx_rows['away'].rest_days}"
          f"(0~10 자름) |")
    print(f"| loadΔ | {cov['load_d']:+d} | 14일 내 경기 수 차 |")
    print(f"| cupΔ | {cov['cup_d']:+d} | ⚠️ 이 목록은 **리그만**이라 컵은 "
          f"구조적으로 0 이다 |")
    print(f"| pb_home | {cov['pb_home']} | 휴식기(14일+) 직후 첫 리그 경기인가 |")
    print(f"| form3Δ | {cov['form3_d']:+.3f} | 최근 리그 3경기 승점 차 |")
    print(f"| pdiff | 0.000 | 🔴 **선수 점수 판이 없다**(§5 적합 전) — 0 이다 |")
    print(f"| absΔ | 0.000 | 🔴 **선수 점수가 없어 못 센다**(§8) |")
    print(f"| benchΔ | 0.000 | 🔴 같은 까닭(§8) · λ 식이 아니라 60분 뒤 배율이다 |")
    print()
    # ── ⑯ λ · 확률 — **계수 판**이 있어야 돈다
    got, why = _pf.load_coef(league=case["league"], as_of=kick)
    if not got:
        print(f"🔴 **계수 판이 없다** — λ 를 만들지 않는다({why})")
        print("   ⚠️ `tools/fit_probfloor.py --league … --write` 로 판을 적어야 "
              "이 칸이 찬다(손값으로 돌리지 않는다 · §0).")
        print()
        return
    cov["diff"] = diffs.get("elo", 0.0)
    lam, why_lam, parts = _pf.compute(cov, coef=got, adopted=set(), detail=True)
    print(f"- λ **{lam['home']:.3f} / {lam['away']:.3f}** ← {why_lam}")
    print("- 항별 기여(log λ 홈) — "
          + " · ".join(f"{k} {v:+.4f}" for k, v in parts.items()))
    grid = _pf.score_grid(lam_home=lam["home"], lam_away=lam["away"],
                          rho=float(got.get("rho") or 0.0))
    mk = _pf.markets_of(grid)
    print(f"- 확률 — 홈 **{mk['home']:.1%}** · 무 {mk['draw']:.1%} · 원정 "
          f"**{mk['away']:.1%}**")
    read = _ud.read(grid, home_name=case["home"], away_name=case["away"])
    print(f"- 🔁 {_ud.line(read)}")
    # ── ⑳ 경고
    box = _v.path_of("upset_model", "all")
    try:
        model, why_m = _v.pick(box, as_of=kick)
    except ValueError:
        model, why_m = {}, "판 없음"
    if model and dict(model.get("coef") or {}):
        sig = {"weak_fav": 1.0 if read.fav_win < _up.WEAK_FAV else 0.0,
               "thin_info": 0.0}
        said_up = _up.score_of(sig, model=dict(model), adopted=set())
        print(f"- ⚠️ {said_up.why}")
    else:
        print(f"- ⬜ **이변 경고 판이 없다**({why_m}) — 경고를 켜지 않는다(U5)")
    print()


async def main() -> int:
    from app.net import Net
    net = Net(cache=True)
    print("# 🔴🔴 §17 재현 — 실사고 두 경기(as-of 킥오프 전)")
    print()
    print("🔴 두 경기에 맞추려고 계수·문턱을 고치지 않았다. 안 채워진 칸은 "
          "**왜 0인지** 적었다.")
    print()
    for case in CASES:
        await one(case, net=net)
    print("## 결과(맨 끝 · 판정에 쓰지 않았다)")
    print()
    print("- 광주 **4-3** 울산 — 홈 승")
    print("- 가와사키 **1-2** 나고야 — 원정 승")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
