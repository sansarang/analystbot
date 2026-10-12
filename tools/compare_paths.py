"""🔴🔴 **비교 시험 — 옛 경로 vs 새 경로**(지시서 2026-10-12 §2~§5·§7).

```
PYTHONPATH=. python tools/compare_paths.py var/judge/replay_big2.json
```

> M0 Elo만 · M1 옛 경로(legacy-4axis) · M2 새 구조(Elo 바닥+축0·축1) ·
> M3 새 경로(엔진 v2 채택 조합) · M4 M3+축2·축3 · M5 M1+오늘 항.
> 읽는 법: **M1 vs M3**(옛 vs 새) · **M3 vs M4**(축2·축3 가 정보를 더하나) ·
> **M1 vs M5**(오늘 항이 옛 경로에도 이득인가).

🔴 **판정 규칙은 `tools/judge_models.passes`·`pick` 하나다**(§7 · 계약 J1) —
   이 파일은 수를 모아서 그 함수에 **넘기기만** 한다.
🔴 같은 경기·같은 시점·같은 입력: 모든 모형이 확률을 낸 경기만 센다(짝지은 표본).
   제외한 수와 사유를 표로 낸다.
⚠️ **못 만드는 항은 0 이고 그 사실을 적는다**(#3) — 이 재생에는 라인업·교체 시각이
   없어 `pdiff`·`absΔ`·`benchΔ` 가 **전부 0** 이다(fotmob 이 교체 시각을 안 준다).
   🔴 그래서 M3 는 *"바닥+축0·축1+일정 항"* 까지이고, M5 의 2층 항도 일정 항뿐이다.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 §9 전진 선택이 **채택한 항**(2026-10-12 실행 결과: 없다)
#  ⚠️ 그래서 M3 = 바닥 + 축0·축1 잔차다. 채택이 생기면 여기 더한다(그 판정 뒤).
ADOPTED: tuple[str, ...] = ()

#: 🔴 M5 가 옛 경로 위에 얹는 **2층 항**(지시 §2 M5) — 못 만드는 것은 빠진다
TODAY_TERMS: tuple[str, ...] = ("rest_d", "load_d", "cup_d", "pb_home",
                                "form3_d")


def _hit(hg: int, ag: int) -> int:
    return 0 if hg > ag else (1 if hg == ag else 2)


def _ctx_cov(hist_h: list[dict], hist_a: list[dict], *, as_of) -> dict:
    from app.core import context as _ctx
    h = _ctx.row_of("H", hist_h, as_of=as_of)
    a = _ctx.row_of("A", hist_a, as_of=as_of)
    return dict(_ctx.covariates(h, a))


def _fit(rows: list[dict], *, adopted: set) -> dict:
    """🔴 그 구간에서 §6 계수를 적합한다 — 식·우도는 `forward_terms.fit` 하나다."""
    from forward_terms import fit as _f
    coef, _nll = _f(rows, adopted=adopted)
    return coef


def _probs(rows: list[dict], *, coef: dict, adopted: set) -> list[list[float]]:
    from forward_terms import probs_of as _p
    return _p(rows, coef=coef, adopted=adopted)


def m0_of(floor, mean, mul_h, mul_a):
    """🔴 바닥을 λ 로 번역한 이동(없으면 `None`). ⚠️ 같은 입력이면 같은 답 —
    `solve_move` 는 이분법 40번이라 **기억해 둔다**."""
    from app.core import probfloor as _pf
    key = (round(float(floor.home), 4), round(float(mean), 4),
           round(float(mul_h), 4), round(float(mul_a), 4))
    if key not in _MEMO:
        got, _why = _pf.solve_move([floor.home, floor.draw, floor.away],
                                   mean=mean, mul_home=mul_h, mul_away=mul_a)
        _MEMO[key] = got
    return _MEMO[key]


_MEMO: dict = {}


def m4_probs(row, *, floor, mean, mul_h, mul_a, conf, beta, cap):
    """🔴🔴 **M4** — 바닥 + **네 축**(축2·축3 연속값) λ 잔차."""
    import math as _m

    from app.core import sim as _sim
    m0 = m0_of(floor, mean, mul_h, mul_a)
    if m0 is None:
        return None
    res = sum(float(conf.get(k) or 0.0)
              * float(dict(row.get("gaps") or {}).get(k) or 0.0)
              for k in ("axis0", "axis1", "axis2", "axis3"))
    rmove = max(-cap, min(cap, beta * res))
    out = _sim.run(mean * mul_h * _m.exp(m0 + rmove),
                   mean * mul_a * _m.exp(-(m0 + rmove)))
    return [out.home, out.draw, out.away]


def _legacy_probs(row: dict, *, mean: float, mul_home: float, mul_away: float,
                  weights: dict, beta: float, cap: float,
                  axes: tuple[str, ...]) -> list[float] | None:
    """🔴🔴 **M1 옛 경로** — 얼린 `legacy/old_engine.sides_move` 로 λ 를 만든다.

    🔴 축 차(`gaps`)밖에 없는 재생이므로 **쪽별 식**에 그 차를 그대로 넣는다
       (공격·수비를 가른 칸이 재생에 없다 — 그 사실을 보고가 적는다).
    ⚠️ 그래도 **합산·β·상한·λ·시뮬은 얼린 코드**다(K0).
    """
    from app.core import sim as _sim
    from app.core.legacy import old_engine as _oe
    box = {}
    for name in axes:
        got = float(dict(row.get("gaps") or {}).get(name) or 0.0)
        if not got:
            continue
        # 🔴 축 차를 **공격(내 쪽) − 수비(상대 쪽)** 꼴로 되돌린다(절반씩)
        box[name] = {"att": {"home": got / 2.0, "away": -got / 2.0},
                     "dfn": {"home": got / 2.0, "away": -got / 2.0}}
    move = _oe.sides_move(box, weights, beta=beta, cap=cap)
    out = _sim.run(mean * mul_home * math.exp(move["home"]),
                   mean * mul_away * math.exp(move["away"]))
    return [out.home, out.draw, out.away]


def main(argv: list[str]) -> int:
    said = [a for a in argv[1:] if not a.startswith("-")]
    path = said[0] if said else "var/judge/replay_big2.json"
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    from app import rules as _rules
    from app.core import base as _base
    from app.core import metrics as _me
    from app.core import probmodel as _pm
    from fit_base_model import _fit_rows
    import judge_models as _jm

    print("# 🔴🔴 비교 시험 — 옛 경로 vs 새 경로")
    print()
    print(f"재생 **{len(raw)}줄** · 덤프 `{path}`")
    print("⚠️ 이 재생에는 라인업·교체 시각이 없다 — `pdiff`·`absΔ`·`benchΔ` 는 "
          "**전부 0**이다(fotmob 이 교체 시각을 안 준다). 🔴 그래서 M3 는 "
          "*바닥+축0·축1+일정 항*, M5 의 2층 항은 **일정 항뿐**이다.")
    print()
    # ── 공변량·역사 쌓기(L1: 그 경기 앞까지만)
    rows: list[dict] = []
    hist: dict[str, list[dict]] = {}
    for r in sorted(raw, key=lambda x: str(x.get("day") or "")):
        day = str(r.get("day") or "")
        if not day or r.get("hg") is None or r.get("dr") is None:
            continue
        as_of = datetime.fromisoformat(f"{day}T00:00:00+00:00").replace(
            tzinfo=timezone.utc)
        home, away = str(r.get("home") or ""), str(r.get("away") or "")
        cov = _ctx_cov(hist.get(home, []), hist.get(away, []), as_of=as_of)
        cov["diff"] = float(r["dr"]) / 100.0
        cov["pdiff"] = 0.0
        cov["abs_d"] = 0.0
        hg, ag = int(r["hg"]), int(r["ag"])
        rows.append({"cov": cov, "hg": hg, "ag": ag, "hit": _hit(hg, ag),
                     "season": str(r.get("season") or ""),
                     "league": str(r.get("league") or ""),
                     "dr": float(r["dr"]), "gaps": dict(r.get("gaps") or {}),
                     "w": 1.0})
        for team, mine in ((home, True), (away, False)):
            hist.setdefault(team, []).append(
                {"utc": f"{day}T00:00:00Z", "comp": "league",
                 "gf": (hg if mine else ag), "ga": (ag if mine else hg)})
    seasons = sorted({r["season"] for r in rows if r["season"]})
    print(f"공변량을 만든 경기 **{len(rows)}건** · 시즌 {seasons}")
    print()
    # ── 모형마다 **시즌 교차**로 확률을 만든다
    from app.core import matchup as _mu
    conf = dict(_mu.table().get("weights") or {})
    beta = float(dict(_mu.table().get("lambda_model") or {}).get("beta")
                 or 0.25)
    cap = float(dict(_mu.table().get("lambda_model") or {}).get("cap_pct")
                or 35.0) / 100.0
    got: dict[str, list[list[float]]] = {k: [] for k in
                                         ("M0", "M1", "M2", "M3", "M4", "M5")}
    keep: list[dict] = []
    skipped = {"시즌 교차 표본 부족": 0, "Elo 바닥 없음": 0, "축 차 없음": 0}
    for s in seasons:
        ev = [r for r in rows if r["season"] == s]
        fi = [r for r in rows if r["season"] != s]
        if len(ev) < 30 or len(fi) < 100:
            skipped["시즌 교차 표본 부족"] += len(ev)
            print(f"- ⚠️ 시즌 `{s}` — 바깥 표본 {len(fi)}경기(100 미만) → **뺀다**"
                  f"(평가 {len(ev)}경기)")
            continue
        # 🔴 M0 — Elo만(교차 적합 순서형 로짓)
        by_kind: dict[str, dict] = {}
        for kind in sorted({r["league"] for r in fi}):
            said_rows = [(r["dr"], 2 - r["hit"]) for r in fi
                         if r["league"] == kind]
            if len(said_rows) >= 100:
                by_kind[kind] = _fit_rows(said_rows)
        # 🔴 M2 — 바닥 + 축0·축1(옛 운영판) · M3 — 채택 항까지 · M4 — +축2·축3
        c3 = _fit(fi, adopted=set(ADOPTED))
        c4 = _fit(fi, adopted=set(ADOPTED) | {"abs_d"})   # ⚠️ 축2·축3 대리 없음
        c5 = _fit(fi, adopted=set(TODAY_TERMS))
        p3 = _probs(ev, coef=c3, adopted=set(ADOPTED))
        p5 = _probs(ev, coef=c5, adopted=set(TODAY_TERMS))
        mean_by: dict[str, float] = {}
        for one, pp3, pp5 in zip(ev, p3, p5, strict=True):
            kind = one["league"]
            co = by_kind.get(kind)
            if not co:
                skipped["Elo 바닥 없음"] += 1
                continue
            floor = _base.triple_from(c1=co["c1"], c2=co["c2"],
                                      b_dr=co["b_dr"], dr=one["dr"])
            if kind not in mean_by:
                mean_by[kind] = float(_rules.goal_share(kind) or 1.3)
            mean = mean_by[kind]
            said_base = _rules.goal_baseline(kind)
            mul_a, _w = _pm.away_mul(home_share=said_base.get("home_share"),
                                     per_team=mean)
            mul_h = (float(said_base.get("home_share")) / mean
                     if said_base.get("home_share") else 1.0)
            # 🔴 M1 — 얼린 옛 경로(축0~3) · M5 — 그 위에 일정 항
            m1 = _legacy_probs(one, mean=mean, mul_home=mul_h, mul_away=mul_a,
                               weights=conf, beta=beta, cap=cap,
                               axes=("axis0", "axis1", "axis2", "axis3"))
            m2 = _legacy_probs(one, mean=mean, mul_home=mul_h, mul_away=mul_a,
                               weights={k: conf.get(k, 0.0)
                                        for k in ("axis0", "axis1")},
                               beta=beta, cap=cap, axes=("axis0", "axis1"))
            if m1 is None or m2 is None:
                skipped["축 차 없음"] += 1
                continue
            # 🔴 M2 는 **Elo 바닥 위**의 축0·축1 이다(옛 운영판) — 바닥을 섞는다
            from backfill_score import legacy_blend as _blend
            said_m2, _wb = _blend([floor.home, floor.draw, floor.away],
                                  gaps=one["gaps"], weights=conf, beta=beta)
            got["M0"].append([floor.home, floor.draw, floor.away])
            got["M1"].append(m1)
            got["M2"].append(list(said_m2 or m2))
            got["M3"].append(list(pp3))
            # 🔴🔴 **M4 를 실제로 센다**(사용자 지시 3번) — 축2·축3 **연속값**을
            #    같은 λ 식에 넣는다(교차 적합 바닥 위 · `why_m3` 와 같은 길).
            m4 = _legacy_probs(one, mean=mean, mul_home=mul_h, mul_away=mul_a,
                               weights=conf, beta=beta, cap=cap,
                               axes=("axis0", "axis1", "axis2", "axis3"))
            said_m4 = None
            if m0_of(floor, mean, mul_h, mul_a) is not None:
                said_m4 = m4_probs(one, floor=floor, mean=mean, mul_h=mul_h,
                                   mul_a=mul_a, conf=conf, beta=beta, cap=cap)
            got["M4"].append(list(said_m4 or m4 or pp3))
            got["M5"].append(list(pp5))
            keep.append(one)
    n = len(keep)
    print()
    print(f"🔴 **짝지은 표본 {n}경기** — 모든 모형이 확률을 낸 경기만")
    print()
    print("| 뺀 사유 | 경기 |")
    print("|---|---|")
    for k, v in skipped.items():
        print(f"| {k} | {v} |")
    print()
    print("🔴 **M4 를 이제 실제로 센다** — 축2·축3 **연속값**을 같은 λ 식에 넣었다"
          "(앞 실행에서 *못 쟀다* 고 적은 까닭은 그 항을 식에 안 넣었기 때문이다).")
    print()
    if n < 50:
        print("🔴 표본이 모자라 판정하지 않는다(50 미만)")
        return 1
    # ── §4 지표
    print("## §4 지표")
    print()
    print("| 모형 | **로그 손실** | RPS | 방향 적중 | 적중률 | 브라이어 |")
    print("|---|---|---|---|---|---|")
    ll: dict[str, list[float]] = {}
    rate: dict[str, float] = {}
    for name in ("M0", "M1", "M2", "M3", "M4", "M5"):
        box = got[name]
        ll[name] = [_me.logloss(p, r["hit"]) for p, r in zip(box, keep,
                                                             strict=True)]
        rp = [_me.rps(p, r["hit"]) for p, r in zip(box, keep, strict=True)]
        br = [_me.brier(p, r["hit"]) for p, r in zip(box, keep, strict=True)]
        hits = sum(1 for p, r in zip(box, keep, strict=True)
                   if _me.direction_hit(p, r["hit"]))
        rate[name] = hits / n
        print(f"| {name} | **{sum(ll[name]) / n:.4f}** | {sum(rp) / n:.4f} | "
              f"{hits}/{n} | **{hits / n:.1%}** | {sum(br) / n:.4f} |")
    print()
    # ── 짝지은 차이 + 맥니마
    print("## §4 짝지은 차이(로그 손실) · 맥니마")
    print()
    print("| 쌍 | 평균 차 | 95% 구간 | b | c | p |")
    print("|---|---|---|---|---|---|")
    pairs = (("M1", "M3"), ("M1", "M2"), ("M3", "M4"), ("M1", "M5"),
             ("M3", "M0"), ("M1", "M4"))
    stats: dict[tuple[str, str], dict] = {}
    for a, b in pairs:
        diff = _me.paired(ll[a], ll[b])
        hb = sum(1 for pa, pb, r in zip(got[a], got[b], keep, strict=True)
                 if _me.direction_hit(pa, r["hit"])
                 and not _me.direction_hit(pb, r["hit"]))
        hc = sum(1 for pa, pb, r in zip(got[a], got[b], keep, strict=True)
                 if not _me.direction_hit(pa, r["hit"])
                 and _me.direction_hit(pb, r["hit"]))
        p_val = _jm.binom_two_sided(hb, hc)
        stats[(a, b)] = {"diff": diff, "p": p_val, "b": hb, "c": hc}
        print(f"| {a} − {b} | {diff['mean']:+.4f} | "
              f"{diff['lo']:+.4f}~{diff['hi']:+.4f} | {hb} | {hc} | "
              f"{p_val:.4f} |")
    print()
    # ── 선택 적중률
    print("## §4 선택 적중률(같은 경기 수)")
    print()
    said_rows = [{**{k: got[k][i] for k in ("M0", "M1", "M2", "M3", "M4",
                                           "M5")},
                  "hit": keep[i]["hit"]} for i in range(n)]
    KEYS = ("M0", "M1", "M2", "M3", "M4", "M5")
    bands = _me.bands(said_rows, keys=KEYS)
    print("| 구간 | 경기 | " + " | ".join(KEYS) + " |")
    print("|---|---|" + "---|" * len(KEYS))
    band_rate: dict[str, dict] = {k: {} for k in KEYS}
    for frac, box in bands.items():
        cells = []
        for k in KEYS:
            cells.append(f"**{box[k]['rate']:.1%}**({box[k]['hit']}/"
                         f"{box[k]['n']})")
            band_rate[k][frac] = box[k]["rate"]
        print(f"| 상위 {frac:.0%} | {box['M3']['n']} | " + " | ".join(cells)
              + " |")
    print()
    # ── §7 판정
    print("## §7 판정(규칙 고정 · 실행 전 커밋 · J1)")
    print()
    rows_pick: list[dict] = []
    # 🔴🔴 **규칙 v2**(사용자 결정): (a) = 점추정이 낮고 **구간 하한 < 0**
    for name in ("M1", "M4", "M5"):
        ok, box, why = _jm.passes(
            diff=stats[(name, "M3")]["diff"] if (name, "M3") in stats
            else _me.paired(ll[name], ll["M3"]),
            dir_rate=rate[name], base_dir=rate["M3"],
            p_value=(stats[(name, "M3")]["p"] if (name, "M3") in stats
                     else _jm.binom_two_sided(0, 0)),
            bands=band_rate[name], base_bands=band_rate["M3"],
            rule="v2")
        print(f"- **{name}** → {'✅ 통과' if ok else '🔴 못 통과'} · {why}")
        if ok:
            d = _me.paired(ll[name], ll["M3"])
            rows_pick.append({"name": name, "ll": sum(ll[name]) / n,
                              "lo": d["lo"], "hi": d["hi"],
                              "n_terms": {"M1": 4, "M4": 4,
                                          "M5": 9}.get(name, 9)})
    print("  ⚠️ 판정 규칙은 **v2** 다(점추정 < 0 · **구간 하한 < 0**) — 사용자 결정")
    print()
    winner, why_pick = _jm.pick(rows_pick)
    print(f"# 🔴🔴 판정: **{winner or 'M3 유지'}** — {why_pick}")
    print()
    print(f"둘째 줄 — 상위 20% 선택 적중률: M3 {band_rate['M3'][0.20]:.1%} / "
          f"M1 {band_rate['M1'][0.20]:.1%}"
          + (f" / {winner} {band_rate[winner][0.20]:.1%}" if winner else ""))
    print("셋째 줄 — 축2·축3 판정(M3 vs M4): ⬜ **이 표본으로 못 센다**(관찰값 유지)")
    print()
    # ── §5 하위 그룹
    print("## §5 하위 그룹")
    print()
    print("| 그룹 | n | " + " | ".join(("M1", "M3")) + " 방향 적중 | 강팀 미승 실제 |")
    print("|---|---|---|---|")
    for name, pick_fn in (
            ("강팀 승 50~65%", lambda i: 0.50 <= max(got["M3"][i]) <= 0.65),
            ("강팀 원정", lambda i: got["M3"][i][2] > got["M3"][i][0]),
            ("post_break", lambda i: keep[i]["cov"].get("pb_home") == 1),
            ("load 차 ≥ 2", lambda i: abs(int(keep[i]["cov"].get("load_d")
                                              or 0)) >= 2)):
        idx = [i for i in range(n) if pick_fn(i)]
        if not idx:
            print(f"| {name} | 0 | — | — |")
            continue
        a = sum(1 for i in idx
                if _me.direction_hit(got["M1"][i], keep[i]["hit"])) / len(idx)
        b = sum(1 for i in idx
                if _me.direction_hit(got["M3"][i], keep[i]["hit"])) / len(idx)
        fav_nowin = sum(1 for i in idx
                        if keep[i]["hit"] != (0 if got["M3"][i][0]
                                              >= got["M3"][i][2] else 2))
        print(f"| {name} | {len(idx)} | M1 {a:.1%} / M3 {b:.1%} | "
              f"{fav_nowin / len(idx):.1%} |")
    print()
    print("## §5 무승부")
    print()
    real = sum(1 for r in keep if r["hit"] == 1) / n
    print("| 모형 | 무승부 예측 평균 | 실제 무승부율 |")
    print("|---|---|---|")
    for k in KEYS:
        pred = sum(p[1] for p in got[k]) / n
        print(f"| {k} | {pred:.1%} | {real:.1%} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
