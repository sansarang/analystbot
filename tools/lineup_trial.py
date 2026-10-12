"""🔴🔴 **4번 라인업 재생 — "오늘 정보가 적중률을 올리나"의 첫 시험**.

```
PYTHONPATH=. python tools/lineup_trial.py --collect     # 라인업 재생(덤프)
PYTHONPATH=. python tools/lineup_trial.py               # 비교
```

> 라인업 재생: fotmob 경기 페이지에서 **선발·교체 시각·벤치**를 받아 재생 →
> `pdiff`·`absΔ`·`benchΔ` 를 실제로 계산. 그 위에서
> **M1 vs M1+pdiff vs M1+pdiff+absΔ vs M3(라인업 포함)** 비교.

🔴🔴 **실측 한계(2026-10-12 · 세 번 확인)** — fotmob 경기 페이지에 **교체 시각이
   없다**: 선수 칸의 `timeSubbedOn`·`timeSubbedOff`·`minutesPlayed` 가 전부 `None`,
   타임라인 사건은 `Goal`·`Half`·`Card` 뿐(`Substitution` 없음), `playerStats` 0건,
   `liveticker` 0건.
   🔴 그래서 선수 점수는 **구간 ±가 아니라 경기 단위 ±**(선발 11명이 90분)로
   적합한다. ⚠️ 교체로 들어온 선수는 그 경기에서 **안 센다** — 지어낸 분으로
   메우지 않는다(#4). 그 사실을 보고가 **매번** 적는다.
   ✅ **선발 XI·벤치 id 는 있다** → `pdiff`·`absΔ`·`benchΔ` 는 **실제로** 계산된다.
🔴 누설 금지: 선수 점수·평소 XI 는 그 경기 **앞** 경기로만 적합한다(L1 · `as_of`).
🔴 판정은 `judge_models.passes(rule="v2")` 하나다(사용자 결정: 점추정이 낮고
   구간 하한 < 0).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

GAP = ("🔴 fotmob 에 **교체 시각이 없다**(선수 칸 `timeSubbedOn`·`minutesPlayed` "
       "전부 `None` · `Substitution` 사건 없음 · `playerStats` 0 · `liveticker` 0) "
       "→ 선수 점수는 **경기 단위 ±**(선발 11명 90분)로 적합한다")

#: 🔴 선수 ± 릿지의 벌 — 격자에서 고른다(손값 아니다)
LAMS = (10.0, 50.0, 200.0)


async def collect(leagues: list[tuple[str, str]], *, seasons: int,
                  out: Path) -> int:
    """🔴 라인업 재생 — `{utc, league, home, away, hg, ag, XI, 벤치}` 를 적는다."""
    from app.collect import fotmob as fm
    from app.core import backfill as bf
    from app.net import Net
    net = Net(cache=True)
    rows: list[dict] = []
    for lid, name in leagues:
        said = await fm.league_matches(net, lid)
        page0 = await net.get(fm.league_matches_url(lid, "x"))
        got_seasons = fm.league_seasons(
            fm.payload(getattr(page0, "text", "") or "") or {})
        for season in got_seasons[1:max(1, int(seasons))]:
            more = await net.get(fm.league_matches_url(lid, "x")
                                 + f"?season={season}")
            j = fm.payload(getattr(more, "text", "") or "") or {}
            pp = ((j.get("props") or {}).get("pageProps") or {})
            for m in (((pp.get("fixtures") or {}).get("allMatches")) or []):
                st = m.get("status") or {}
                said.append({"id": str(m.get("id") or ""),
                             "home": str((m.get("home") or {}).get("name") or ""),
                             "away": str((m.get("away") or {}).get("name") or ""),
                             "utc": str(st.get("utcTime") or ""),
                             "finished": bool(st.get("finished"))})
        done = sorted([r for r in said if r.get("finished") and r.get("utc")],
                      key=lambda r: str(r["utc"]))
        print(f"[lineup] {name} — 끝난 경기 {len(done)}건", flush=True)
        for i, one in enumerate(done, 1):
            if i % 50 == 0:
                print(f"   … {i}/{len(done)}", flush=True)
            page = await net.get(fm.match_url(str(one["id"])))
            j = fm.payload(getattr(page, "text", "") or "")
            if not j:
                continue
            score = bf.score_of(j)
            lu = ((j.get("props") or {}).get("pageProps") or {}).get(
                "content", {}).get("lineup") or {}
            home = dict(lu.get("homeTeam") or {})
            away = dict(lu.get("awayTeam") or {})
            h_ids = [str(p.get("id")) for p in (home.get("starters") or [])
                     if p.get("id")]
            a_ids = [str(p.get("id")) for p in (away.get("starters") or [])
                     if p.get("id")]
            if score is None or len(h_ids) != 11 or len(a_ids) != 11:
                continue
            rows.append({
                "utc": str(one["utc"]), "league": name,
                "home": str(one["home"]), "away": str(one["away"]),
                "hg": score[0], "ag": score[1],
                "home_ids": h_ids, "away_ids": a_ids,
                "home_bench": [str(p.get("id"))
                               for p in (home.get("subs") or []) if p.get("id")],
                "away_bench": [str(p.get("id"))
                               for p in (away.get("subs") or []) if p.get("id")],
            })
    out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"🔴 라인업 재생 **{len(rows)}경기**를 적었다 — {out}")
    return 0


def _pm_fit(rows: list[dict], *, as_of, lam: float):
    """🔴 선수 ± — **경기 단위**(선발 11명 90분 · 교체 시각이 없다). L1 을 지난다."""
    from app.core.ratings import player_pm as _pm
    said = [{"utc": r["utc"], "comp": "league",
             "home_ids": r["home_ids"], "away_ids": r["away_ids"],
             "goals": ([{"min": 45, "home": True}] * int(r["hg"])
                       + [{"min": 45, "home": False}] * int(r["ag"])),
             "subs": []}
            for r in rows]
    return _pm.fit(said, as_of=as_of, lam=lam)


def _cov_of(row: dict, table, hist: dict) -> dict:
    """🔴 `pdiff`·`absΔ`·`benchΔ` — **실제로** 센다(선발·벤치 id 가 있다)."""
    from app.core.ratings import lineup_strength as _ls
    from app.core.ratings import player_pm as _pm
    as_of = datetime.fromisoformat(str(row["utc"]).replace("Z", "+00:00"))

    def _mean(ids: list[str]) -> float:
        got = [_pm.value_of(p, table)[0] for p in ids]
        return (sum(got) / len(got)) if got else 0.0

    out = {"pdiff": _mean(row["home_ids"]) - _mean(row["away_ids"])}
    loss = {}
    for side in ("home", "away"):
        past = [{"utc": r["utc"], "comp": "league",
                 "minutes": {p: 90 for p in r[f"{side}_ids"]}}
                for r in hist.get(row[side], [])]
        usual, _w = _ls.usual_xi(past, as_of=as_of)
        loss[side], _w2 = _ls.absence_loss(usual=usual,
                                           today=row[f"{side}_ids"],
                                           value=table.value)
    out["abs_d"] = float(loss["home"]) - float(loss["away"])
    bench = {}
    for side in ("home", "away"):
        got, _w = _ls.bench_mean(row[f"{side}_bench"], value=table.value)
        bench[side] = float(got) if got is not None else 0.0
    out["bench_d"] = bench["home"] - bench["away"]
    return out


def _nll(params, rows, *, terms):
    """🔴 포아송 우도 — λ 는 `exp(b0 ± (b1·diff + 항))`(쪽 대칭)."""
    b0, b1, h = params[0], params[1], params[2]
    extra = dict(zip(terms, params[3:], strict=True))
    out = 0.0
    for r in rows:
        tilt = b1 * float(r["axis_tilt"]) + sum(
            float(w) * float(r["cov"].get(t) or 0.0)
            for t, w in extra.items())
        lh = math.exp(b0 + h + tilt)
        la = math.exp(b0 - tilt)
        hg, ag = int(r["hg"]), int(r["ag"])
        out -= (-lh + hg * math.log(lh) - math.lgamma(hg + 1)
                - la + ag * math.log(la) - math.lgamma(ag + 1))
    return out


def _fit_model(rows, *, terms):
    import numpy as np
    from scipy.optimize import minimize
    start = np.array([0.2, 0.3, 0.1] + [0.0] * len(terms))
    got = minimize(_nll, start, args=(rows,), kwargs={"terms": terms},
                   method="Nelder-Mead",
                   options={"maxiter": 40000, "xatol": 1e-6, "fatol": 1e-7})
    return [float(v) for v in got.x]


def _probs(rows, params, *, terms):
    from app.core import probfloor as _pf
    b0, b1, h = params[0], params[1], params[2]
    extra = dict(zip(terms, params[3:], strict=True))
    out = []
    for r in rows:
        tilt = b1 * float(r["axis_tilt"]) + sum(
            float(w) * float(r["cov"].get(t) or 0.0) for t, w in extra.items())
        lh = math.exp(b0 + h + tilt)
        la = math.exp(b0 - tilt)
        grid = _pf.score_grid(lam_home=lh, lam_away=la, rho=0.0)
        mk = _pf.markets_of(grid)
        out.append([mk["home"], mk["draw"], mk["away"]])
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--rows", default="var/judge/lineup_rows.json")
    ap.add_argument("--backfill", default="var/judge/replay_big2.json")
    ap.add_argument("--seasons", type=int, default=2)
    args = ap.parse_args(argv[1:])
    out = ROOT / args.rows
    if args.collect:
        return asyncio.run(collect([("223", "league:J1"), ("9080", "league:KL1")],
                                   seasons=int(args.seasons), out=out))
    rows = json.loads(out.read_text(encoding="utf-8"))
    back = json.loads((ROOT / args.backfill).read_text(encoding="utf-8"))
    # 🔴 두 재생을 **같은 경기**로 잇는다(날짜+두 팀)
    key = {(str(r.get("day")), str(r.get("home")), str(r.get("away"))): r
           for r in back}
    joined: list[dict] = []
    for r in rows:
        day = str(r["utc"])[:10]
        got = key.get((day, r["home"], r["away"]))
        if not got or got.get("gaps") is None or got.get("dr") is None:
            continue
        conf_tilt = sum(float(v or 0.0) for v in dict(got["gaps"]).values())
        joined.append({**r, "day": day, "gaps": dict(got["gaps"]),
                       "dr": float(got["dr"]), "season": str(got.get("season")
                                                             or ""),
                       "axis_tilt": conf_tilt})
    print("# 🔴🔴 4번 라인업 재생 — 오늘 정보가 적중률을 올리나")
    print()
    print(GAP)
    print()
    print(f"라인업 재생 {len(rows)}경기 · 백필과 **이어진 경기 {len(joined)}건**")
    print()
    if len(joined) < 100:
        print("🔴 표본이 모자라다(100 미만) — 시험하지 않는다")
        return 1
    joined.sort(key=lambda r: r["utc"])
    hist: dict[str, list[dict]] = {}
    for r in joined:
        for side in ("home", "away"):
            hist.setdefault(r[side], []).append(r)
    seasons = sorted({r["season"] for r in joined if r["season"]})
    from app.core import metrics as _me
    import judge_models as _jm
    MODELS = (("M1", ()), ("M1+pdiff", ("pdiff",)),
              ("M1+pdiff+absΔ", ("pdiff", "abs_d")),
              ("M1+pdiff+absΔ+benchΔ", ("pdiff", "abs_d", "bench_d")))
    ll: dict[str, list[float]] = {k: [] for k, _t in MODELS}
    hits: dict[str, int] = {k: 0 for k, _t in MODELS}
    probs: dict[str, list[list[float]]] = {k: [] for k, _t in MODELS}
    keep: list[dict] = []
    for s in seasons:
        ev = [r for r in joined if r["season"] == s]
        fi = [r for r in joined if r["season"] != s]
        if len(ev) < 30 or len(fi) < 100:
            print(f"- ⚠️ 시즌 `{s}` — 바깥 {len(fi)}경기(100 미만) → **뺀다**")
            continue
        _me.check_split(fit={r["season"] for r in fi}, eval={s})
        # 🔴 선수 점수는 **바깥 시즌**으로 적합한다(교차) · 벌은 격자에서 고른다
        as_of = datetime.fromisoformat(
            f"{min(r['day'] for r in ev)}T00:00:00+00:00").replace(
            tzinfo=timezone.utc)
        best = None
        for lam in LAMS:
            table = _pm_fit(fi, as_of=as_of, lam=lam)
            if not table.value:
                continue
            sse = 0.0
            for r in fi[-80:]:
                got = _cov_of(r, table, hist)
                sse += (got["pdiff"] - (int(r["hg"]) - int(r["ag"]))) ** 2
            if best is None or sse < best[0]:
                best = (sse, lam, table)
        if best is None:
            print(f"- 🔴 시즌 `{s}` — 선수 점수를 못 적합했다")
            continue
        _sse, lam, table = best
        print(f"- 시즌 `{s}` — 선수 점수 벌 λ **{lam:g}** · 선수 "
              f"{len(table.value)}명 · 수축 {table.shrunk}명 · {table.why[:60]}")
        for r in ev + fi:
            r["cov"] = _cov_of(r, table, hist)
        for name, terms in MODELS:
            params = _fit_model(fi, terms=terms)
            p = _probs(ev, params, terms=terms)
            probs[name] += p
            for one, pp in zip(ev, p, strict=True):
                hit = 0 if one["hg"] > one["ag"] else (
                    1 if one["hg"] == one["ag"] else 2)
                ll[name].append(_me.logloss(pp, hit))
                hits[name] += 1 if _me.direction_hit(pp, hit) else 0
        keep += ev
    n = len(keep)
    print()
    print(f"🔴 **짝지은 표본 {n}경기**")
    print()
    if n < 50:
        print("🔴 표본이 모자라 판정하지 않는다")
        return 1
    said_rows = [{**{k: probs[k][i] for k, _t in MODELS},
                  "hit": (0 if keep[i]["hg"] > keep[i]["ag"]
                          else (1 if keep[i]["hg"] == keep[i]["ag"] else 2))}
                 for i in range(n)]
    bands = _me.bands(said_rows, keys=tuple(k for k, _t in MODELS))
    print("| 모형 | **로그 손실** | 방향 적중률 | 상위 30% | 상위 20% | 상위 10% |")
    print("|---|---|---|---|---|---|")
    for name, _t in MODELS:
        print(f"| {name} | **{sum(ll[name]) / n:.4f}** | "
              f"**{hits[name] / n:.1%}** | "
              + " | ".join(f"{bands[f][name]['rate']:.1%}"
                           for f in (0.30, 0.20, 0.10)) + " |")
    print()
    print("| 쌍(도전 − 기준 M1) | 평균 차 | 95% 구간 | 판정(v2) |")
    print("|---|---|---|---|")
    base = "M1"
    for name, _t in MODELS[1:]:
        diff = _me.paired(ll[name], ll[base])
        ok, _box, why = _jm.passes(
            diff=diff, dir_rate=hits[name] / n, base_dir=hits[base] / n,
            p_value=_jm.binom_two_sided(
                sum(1 for i in range(n)
                    if _me.direction_hit(probs[name][i], said_rows[i]["hit"])
                    and not _me.direction_hit(probs[base][i],
                                              said_rows[i]["hit"])),
                sum(1 for i in range(n)
                    if not _me.direction_hit(probs[name][i],
                                             said_rows[i]["hit"])
                    and _me.direction_hit(probs[base][i],
                                          said_rows[i]["hit"]))),
            bands={f: bands[f][name]["rate"] for f in (0.30, 0.20, 0.10)},
            base_bands={f: bands[f][base]["rate"] for f in (0.30, 0.20, 0.10)},
            rule="v2")
        print(f"| {name} | {diff['mean']:+.4f} | {diff['lo']:+.4f}~"
              f"{diff['hi']:+.4f} | {'✅ 통과' if ok else '🔴 못 통과'} |")
        print(f"|   ↳ 근거 | | | {why} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
