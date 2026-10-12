"""🔴🔴 **§2 바닥 점수 학습률 격자 적합** — 지시서 2026-10-12(엔진 교체) §2.

```
PYTHONPATH=. python tools/fit_ratings.py --rating pi --league league:KL1 \
    --fotmob 9080 --as-of 2026-01-01T00:00Z --seasons 2
```

> `--rating {elo,elog,pi} --league --as-of` — 시즌 A로 학습률 격자 탐색
> (목적: **다음 경기 골 차 예측 제곱오차**), 판 저장
> `data/ratings_params/<league>/<as_of>.yaml`.

🔴 목적함수는 **골 차 제곱오차**다(승무패가 아니다) — 지시가 그렇게 정했다.
   ⚠️ 그래서 이 적합은 **확률을 못 본다**. 확률 비교는 §3(`fit_probfloor`)과
   §1 판정이 한다 — 두 일을 섞지 않는다.
🔴 **적합 구간과 평가 구간을 가른다**(계약 E1) — `--as-of` **이전** 경기로만
   학습률을 고른다. 그 뒤 경기는 평가용이라 **보지 않는다**.
🔴 판을 적는 것은 **도구**다(`tools/versions_write.py` · 앱은 yaml 을 안 쓴다).
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 격자 — 수를 **코드에 적지만** 이것은 *"어디까지 흔들어 볼까"* 이고,
#  채택되는 값은 **적합이 고른다**(손값 계수가 아니다).
GRID: dict[str, dict[str, list[float]]] = {
    "elo": {"k": [10.0, 15.0, 20.0, 25.0, 30.0, 40.0]},
    "elog": {"k0": [5.0, 8.0, 10.0, 15.0, 20.0],
             "lam": [0.4, 0.6, 0.8, 1.0, 1.2]},
    "pi": {"lam": [0.02, 0.035, 0.05, 0.06, 0.08, 0.1],
           "gamma": [0.3, 0.5, 0.7, 0.9]},
}


def _as_of(said: str) -> datetime:
    from run_stage8 import _as_of as _one
    return _one(said)


async def games_of(net, lid: str, *, seasons: int) -> list[dict]:
    """🔴 그 리그의 **끝난 경기**를 `{utc, home, away, hg, ag}` 로. 사본 금지 —
    목록은 `fotmob.league_matches` 가 만들고 스코어는 경기 페이지에서 읽는다."""
    from app.collect import fotmob as fm
    from app.core import backfill as bf
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
                         "home": str((m.get("home") or {}).get("name") or ""),
                         "away": str((m.get("away") or {}).get("name") or ""),
                         "utc": str(st.get("utcTime") or ""),
                         "finished": bool(st.get("finished"))})
    out = []
    done = [r for r in rows if r.get("finished") and r.get("utc")]
    for i, one in enumerate(sorted(done, key=lambda r: str(r["utc"])), 1):
        if i % 50 == 0:
            print(f"   … 스코어 {i}/{len(done)}", flush=True)
        page = await net.get(fm.match_url(str(one.get("id") or "")))
        j = fm.payload(getattr(page, "text", "") or "")
        if not j:
            continue
        got = bf.score_of(j)
        if got is None:
            continue
        out.append({"utc": str(one["utc"]), "home": str(one["home"]),
                    "away": str(one["away"]), "hg": got[0], "ag": got[1]})
    return out


def sse_of(mod, games: list[dict], *, params, as_of) -> tuple[float, int]:
    """🔴🔴 **다음 경기 골 차 제곱오차** — 지시가 정한 목적함수.

    🔴 경기를 시간 순으로 돌며 **그 경기 앞까지의 표**로 골 차를 예측하고, 실제
       골 차와의 제곱오차를 모은다(누설 없음 — 표는 늘 그 경기 **전**이다).
    ⚠️ Elo·ELOg 는 점수 단위가 골 차가 아니다 — **한 번의 선형 자**(최소제곱)로
       골 차로 바꿔 견준다. 그 자는 **격자마다 다시** 구한다(공평하다).
    """
    rows = sorted(games, key=lambda g: str(g["utc"]))
    xs: list[float] = []
    ys: list[float] = []
    seen: list[dict] = []
    for one in rows:
        when = datetime.fromisoformat(str(one["utc"]).replace("Z", "+00:00"))
        if when >= as_of:
            break
        if len(seen) >= 20:                     # 🔴 표가 설 만큼 쌓인 뒤부터 센다
            table = mod.rate(seen, params=params, as_of=when)
            xs.append(float(mod.prob_input(one["home"], one["away"], table)))
            ys.append(float(int(one["hg"]) - int(one["ag"])))
        seen.append(one)
    if len(xs) < 20:
        return (float("inf"), len(xs))
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = sum((x - mx) ** 2 for x in xs)
    slope = (num / den) if den else 0.0
    inter = my - slope * mx
    sse = sum((y - (inter + slope * x)) ** 2
              for x, y in zip(xs, ys, strict=True)) / len(xs)
    return (sse, len(xs))


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rating", required=True, choices=sorted(GRID))
    ap.add_argument("--league", required=True)
    ap.add_argument("--fotmob", required=True)
    ap.add_argument("--as-of", required=True,
                    help="🔴 이 시각 **이전** 경기로만 적합한다(E1)")
    ap.add_argument("--seasons", type=int, default=2)
    ap.add_argument("--write", action="store_true",
                    help="판 파일로 적는다(없으면 화면만)")
    args = ap.parse_args(argv[1:])
    as_of = _as_of(args.as_of)
    from app.core import ratings as _r
    from app.net import Net
    mod = __import__(f"app.core.ratings.{args.rating}",
                     fromlist=["x"])
    net = Net(cache=True)
    print(f"[fit_ratings] `{args.rating}` · {args.league} · as-of "
          f"{as_of:%Y-%m-%d %H:%M}Z", flush=True)
    games = await games_of(net, str(args.fotmob), seasons=int(args.seasons))
    print(f"[fit_ratings] 끝난 경기 {len(games)}건", flush=True)
    grid = GRID[args.rating]
    names = sorted(grid)
    best = None
    for combo in itertools.product(*[grid[n] for n in names]):
        vals = dict(zip(names, combo, strict=True))
        # 🔴 `start` 는 흔들지 않는다 — 판(있으면)이나 임시값에서 **받아 온다**
        #    (`load_params` 가 그 사실까지 함께 든다 · R2).
        vals.setdefault("start", _r.load_params(
            args.rating, league=args.league, as_of=as_of).get("start"))
        p = _r.Params(name=args.rating, values=vals, ver="격자")
        sse, n = sse_of(mod, games, params=p, as_of=as_of)
        print(f"   {vals} → 제곱오차 {sse:.4f}(n={n})", flush=True)
        if best is None or sse < best[0]:
            best = (sse, vals, n)
    if best is None or best[0] == float("inf"):
        print("🔴 적합 못 했다 — 표본이 모자라다(판을 적지 않는다)")
        return 1
    sse, vals, n = best
    print(f"\n🔴 **고른 학습률** {vals} · 골 차 제곱오차 {sse:.4f} · 경기 {n}건")
    if args.write:
        from versions_write import write as _write
        box = dict(vals)
        box["fit"] = {"sse": round(float(sse), 6), "n": int(n),
                      "as_of": as_of.date().isoformat(),
                      "rating": args.rating, "league": args.league,
                      "objective": "다음 경기 골 차 제곱오차(지시 §2)"}
        said = _write("ratings_params",
                      f"{args.rating}/{args.league.replace(':', '_')}",
                      day=as_of.date(), body=box,
                      head=("# 🔴 `tools/fit_ratings.py` 가 적었다 — 손으로 "
                            "고치지 않는다(지시서 §2 · 계약 R2)"))
        print(f"🔴 판을 적었다 — {said}")
    else:
        print("⚠️ `--write` 가 없다 — 판을 적지 않았다(화면만)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
