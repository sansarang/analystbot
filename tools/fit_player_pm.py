"""🔴🔴 **§5 선수 ± 적합 · §8 결장의 무게 측정** — 지시서 2026-10-12(둘째).

```
PYTHONPATH=. python tools/fit_player_pm.py --league league:KL1 --fotmob 9080 \
    --seasons 2 --as-of 2026-10-11T05:00Z
```

🔴🔴 **실측 한계 2026-10-12 — fotmob 이 교체 시각을 주지 않는다.**
   받아서 확인했다(경기 5140047): 선수 칸에 `timeSubbedOn`·`timeSubbedOff`·
   `minutesPlayed` 가 **전부 `None`** 이고, 타임라인 사건은 `Goal`·`Half`·`Card`
   뿐이다(`Substitution` 이 **없다**).
   🔴 그래서 구간을 **교체 시점으로 못 가른다** — 골 시점으로만 가르고 **선발 11명**
      이 경기 전체를 뛴 것으로 센다(교체 선수는 ± 에 **안 들어간다**).
   ⚠️ 이것은 지시 §5 의 *"교체·골 시점"* 중 **골 시점만** 쓰는 것이다. 지어낸
      수로 메우지 않는다(#4 추측 금지) — 이 사실을 보고가 **매번** 적는다.
   🔴 벤치 점수(§8 `bench_mean`)도 그래서 **표에 있는 선수만** 센다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

GAP = ("🔴 fotmob 이 **교체 시각을 주지 않는다** — 구간은 **골 시점만**으로 "
       "가르고 선발 11명이 전 경기를 뛴 것으로 센다(교체 선수는 ± 에 없다)")


def _as_of(said: str) -> datetime:
    from run_stage8 import _as_of as _one
    return _one(said)


async def games_of(net, lid: str, *, seasons: int, limit: int = 500
                   ) -> list[dict]:
    """🔴 그 리그의 끝난 경기 → §5 가 받는 꼴. **id 로만** 선수를 센다(§5 배선)."""
    from app.collect import fotmob as fm
    rows = await fm.league_matches(net, lid)
    page0 = await net.get(fm.league_matches_url(lid, "x"))
    said = fm.league_seasons(fm.payload(getattr(page0, "text", "") or "") or {})
    for season in said[1:max(1, int(seasons))]:
        more = await net.get(fm.league_matches_url(lid, "x")
                             + f"?season={season}")
        j = fm.payload(getattr(more, "text", "") or "") or {}
        pp = ((j.get("props") or {}).get("pageProps") or {})
        for m in (((pp.get("fixtures") or {}).get("allMatches")) or []):
            st = m.get("status") or {}
            rows.append({"id": str(m.get("id") or ""),
                         "utc": str(st.get("utcTime") or ""),
                         "finished": bool(st.get("finished"))})
    done = sorted([r for r in rows if r.get("finished") and r.get("utc")],
                  key=lambda r: str(r["utc"]))[-int(limit):]
    out: list[dict] = []
    for i, one in enumerate(done, 1):
        if i % 50 == 0:
            print(f"   … 라인업 {i}/{len(done)}", flush=True)
        page = await net.get(fm.match_url(str(one["id"])))
        j = fm.payload(getattr(page, "text", "") or "")
        if not j:
            continue
        lu = ((j.get("props") or {}).get("pageProps") or {}).get(
            "content", {}).get("lineup") or {}
        home = dict(lu.get("homeTeam") or {})
        away = dict(lu.get("awayTeam") or {})
        h_ids = [str(p.get("id")) for p in (home.get("starters") or [])
                 if p.get("id")]
        a_ids = [str(p.get("id")) for p in (away.get("starters") or [])
                 if p.get("id")]
        if len(h_ids) != 11 or len(a_ids) != 11:
            continue                      # 🔴 11명이 아니면 쓰지 않는다(§13-c ②)
        goals = [{"min": int(g.get("minute") or 0), "home": bool(g.get("home"))}
                 for g in fm.goals_of(j)]
        out.append({"utc": str(one["utc"]), "comp": "league",
                    "home_ids": h_ids, "away_ids": a_ids,
                    "goals": goals, "subs": [],   # ⚠️ 교체 시각이 없다(GAP)
                    "home_bench": [str(p.get("id"))
                                   for p in (home.get("subs") or [])
                                   if p.get("id")],
                    "away_bench": [str(p.get("id"))
                                   for p in (away.get("subs") or [])
                                   if p.get("id")],
                    "minutes": {**{str(p): 90 for p in h_ids},
                                **{str(p): 90 for p in a_ids}}})
    return out


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--fotmob", required=True)
    ap.add_argument("--seasons", type=int, default=2)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--lams", default="1,10,50,200",
                    help="🔴 벌(λ) 격자 — 적합이 고른다(손값 아니다)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv[1:])
    as_of = _as_of(args.as_of)
    from app.core import metrics as _me
    from app.core.ratings import lineup_strength as _ls
    from app.core.ratings import player_pm as _pm
    from app.net import Net
    net = Net(cache=True)
    print("# 🔴🔴 §5 선수 ± · §8 결장의 무게")
    print()
    print(GAP)
    print()
    games = await games_of(net, str(args.fotmob), seasons=int(args.seasons))
    print(f"선발 11명을 받은 경기 **{len(games)}건** · as-of {as_of:%Y-%m-%d}")
    print()
    # ── 🔴 벌(λ)을 **고른다** — 뒤쪽 20%를 평가로 떼고 골 차 제곱오차로 센다
    rows = sorted(games, key=lambda g: str(g["utc"]))
    cut = int(len(rows) * 0.8)
    fit_rows, ev_rows = rows[:cut], rows[cut:]
    if len(fit_rows) < 30 or not ev_rows:
        print("🔴 표본이 모자라 λ 를 못 고른다(적합하지 않는다)")
        return 1
    split = datetime.fromisoformat(str(ev_rows[0]["utc"]).replace("Z", "+00:00"))
    _me.check_split(fit={f"~{split:%Y-%m-%d}"}, eval={f"{split:%Y-%m-%d}~"})
    print("| 벌 λ | 선수 | 수축 | 평가 골 차 제곱오차 |")
    print("|---|---|---|---|")
    best = None
    for lam in [float(v) for v in str(args.lams).split(",")]:
        got = _pm.fit(fit_rows, as_of=split, lam=lam)
        if not got.value:
            print(f"| {lam:g} | 0 | — | 적합 못 했다 |")
            continue
        sse = 0.0
        n = 0
        for m in ev_rows:
            h = sum(_pm.value_of(p, got)[0] for p in m["home_ids"]) / 11.0
            a = sum(_pm.value_of(p, got)[0] for p in m["away_ids"]) / 11.0
            real = sum(1 for g in m["goals"] if g["home"]) - sum(
                1 for g in m["goals"] if not g["home"])
            sse += ((h - a) - real) ** 2
            n += 1
        sse /= max(1, n)
        print(f"| {lam:g} | {len(got.value)} | {got.shrunk} | {sse:.4f} |")
        if best is None or sse < best[0]:
            best = (sse, lam, got)
    if best is None:
        print("🔴 고를 수 있는 λ 가 없다")
        return 1
    sse, lam, table = best
    print()
    print(f"🔴 **고른 벌 λ {lam:g}** · 평가 제곱오차 {sse:.4f} · {table.why}")
    print()
    # ── 🔴 §8 — 그 점수로 **결장의 무게**를 센다(마지막 경기에서)
    last = rows[-1]
    hist: dict[str, list[dict]] = {}
    for m in rows[:-1]:
        for side, ids in (("home", m["home_ids"]), ("away", m["away_ids"])):
            key = f"{side}:{m['utc'][:10]}"
            hist.setdefault(key, [])
    print("## §8 결장의 무게 — 마지막 경기로 **길이 서는지** 본다")
    print()
    for side in ("home", "away"):
        past = [{"utc": m["utc"], "comp": "league",
                 "minutes": {p: 90 for p in m[f"{side}_ids"]}}
                for m in rows[:-1]]
        usual, why_u = _ls.usual_xi(past, as_of=datetime.fromisoformat(
            str(last["utc"]).replace("Z", "+00:00")))
        loss, why_l = _ls.absence_loss(usual=usual, today=last[f"{side}_ids"],
                                       value=table.value)
        bench, why_b = _ls.bench_mean(last[f"{side}_bench"],
                                      value=table.value)
        print(f"- **{side}** — {why_u}")
        print(f"    결장의 무게 **{loss:+.3f}** — {why_l}")
        print(f"    벤치 — {'**%+.3f**' % bench if bench is not None else '⬜'}"
              f" · {why_b}")
    print()
    if args.write:
        from versions_write import write as _write
        body = {"lam": lam, "sse": round(float(sse), 6),
                "n_matches": table.n_matches, "shrunk": table.shrunk,
                "mean": round(float(table.mean), 6),
                "gap": GAP,
                "value": {k: round(float(v), 6)
                          for k, v in sorted(table.value.items())}}
        out = _write("player_pm", str(args.league).replace(":", "_"),
                     day=as_of.date(), body=body,
                     head="# 🔴 `tools/fit_player_pm.py` 가 적었다(§5)")
        print(f"🔴 판을 적었다 — {out}")
    else:
        print("⚠️ `--write` 가 없다 — 판을 적지 않았다(화면만)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
