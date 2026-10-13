"""🔴🔴 **§6 비교 판 — 라인업 보정이 M1 을 이기나**(지시서 2026-10-13).

```
PYTHONPATH=. python tools/lineup_trial2.py
```

판: `B`(M1 단독) · `B+L1` · `B+L1+L2` · `B+L1+L2+L5` · `B+L3` · `B+L4` · `B+L3+L4`
🔴 판정 규칙 **v2**(실행 전 커밋): (a) 로그 손실 점추정 < B **그리고** 구간 하한 < 0
   (b) 방향이 B 보다 낮지 않음(맥니마 B 우세 p<0.05 탈락) (c) 상위 30/20/10% 평균 ≥ B.
🔴 **누설 금지** — 선수 점수 표는 그 경기 **달(月) 이전** 경기로만 적합한다(확장
   창). 직교화 계수 `a·b` 와 `g` 는 **훈련 시즌에서만** 적합한다.
🔴 M1 은 손대지 않는다 — λ 는 백필이 적어 둔 M1 의 λ 다(`replay_big2.json.lam`).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴🔴 비교 판 — **재료 교체판**(사용자 결정 2026-10-13 저녁 3번):
#   `B · B+L6 · B+L7 · B+L8 · B+L6+L8`
#   ⚠️ 옛 판(`B+L1…B+L3+L4`)의 결과는 `docs/fable/stages/2026-10-13_lineup_to_m1.md`
#      에 남아 있다 — 그 재료(구간 ±)는 **반분 상관 0.09/0.06** 으로 탈락했다.
PLATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("B", ()), ("B+L6", ("L6",)), ("B+L7", ("L7",)), ("B+L8", ("L8",)),
    ("B+L6+L8", ("L6", "L8")),
)

#: 🔴 판정 규칙 — (d) 가 더해진 판이다(실행 **전에** 커밋했다)
RULE = "lineup2"

#: 🔴 계수 릿지의 벌 — 격자에서 **시즌 교차**로 고른다(손값 금지)
GS = (0.5, 2.0, 10.0, 50.0)


def month_of(utc: str) -> str:
    return str(utc)[:7]


def load() -> tuple[list[dict], str]:
    """🔴 §1·§2 재료 + 백필(M1 λ)을 **한 꼴**로 잇는다."""
    from fit_pm import key_of, season_blocks
    rows = json.loads((ROOT / "var/judge/lineup_rows2.json").read_text(
        encoding="utf-8"))
    box = json.loads((ROOT / "var/judge/minutes.json").read_text(
        encoding="utf-8"))
    ev = json.loads((ROOT / "var/judge/events.json").read_text(
        encoding="utf-8"))
    back = json.loads((ROOT / "var/judge/replay_big2.json").read_text(
        encoding="utf-8"))
    key = {(str(r.get("day")), str(r.get("home")), str(r.get("away"))): r
           for r in back}
    seasons: dict[str, str] = {}
    for league in {str(r["league"]) for r in rows}:
        seasons.update(season_blocks([r for r in rows
                                      if str(r["league"]) == league]))
    out: list[dict] = []
    gone = {"백필에 없다": 0, "λ 가 없다": 0, "골 분이 없다": 0}
    for r in rows:
        k = key_of(r)
        got = key.get((str(r["utc"])[:10], r["home"], r["away"]))
        if not got:
            gone["백필에 없다"] += 1
            continue
        if not got.get("lam"):
            gone["λ 가 없다"] += 1
            continue
        said = dict(ev.get(k) or {})
        goals = list(said.get("goals") or [])
        if not goals and (int(r["hg"]) + int(r["ag"])) > 0:
            gone["골 분이 없다"] += 1
            continue
        one = dict(box.get(k) or {})
        # 🔴 통로는 §1 백필이 경기마다 적어 둔다(정확한 시각 · 뛴 분 · 거친 판)
        src = str(one.get("src") or "")
        fine = (src == "정확한 시각")
        out.append({
            "utc": r["utc"], "league": str(r["league"]),
            "season": seasons.get(k, ""), "month": month_of(r["utc"]),
            "home": r["home"], "away": r["away"],
            "hg": int(r["hg"]), "ag": int(r["ag"]),
            "hit": int(got["hit"]), "lam": [float(x) for x in got["lam"]],
            "axis0": float(dict(got.get("gaps") or {}).get("axis0") or 0.0),
            "home_ids": [str(x) for x in r["home_ids"]],
            "away_ids": [str(x) for x in r["away_ids"]],
            "home_bench": [str(x) for x in r["home_bench"]],
            "away_bench": [str(x) for x in r["away_bench"]],
            "home_box": dict(one.get("home") or {}),
            "away_box": dict(one.get("away") or {}),
            "goals": goals, "pos": dict(said.get("pos") or {}),
            # 🔴 **선수 가치 v2 의 재료**(분·xG·xA) — 이것이 없으면 표가 빈다
            #    (실사고 2026-10-13: 이 칸을 안 담아 표 0개 · 신호 0건이었다)
            "pstat": dict(said.get("pstat") or {}),
            "fine": bool(fine), "src": src})
    why = (f"이은 경기 **{len(out)}건** · 버린 것 — "
           + " · ".join(f"{k} {v}건" for k, v in gone.items()))
    return out, why


def tables_of(rows: list[dict], *, lam: float = 0.0) -> dict:
    """🔴🔴 **확장 창** — 달마다, 그 달 **이전** 경기로만 **가치 v2** 를 적합한다.

    🔴 재료 교체(2026-10-13 저녁): 구간 ±(`player_pm`) → **박스 기록**
       (`player_box` · 90분당 xG+xA). 반분 상관 0.09/0.06 → **0.54/0.64**.
    """
    from app.core.ratings import player_box as pb
    out: dict[tuple[str, str], object] = {}
    for league in sorted({r["league"] for r in rows}):
        said = sorted([r for r in rows if r["league"] == league],
                      key=lambda r: r["utc"])
        for month in sorted({r["month"] for r in said}):
            at = datetime.fromisoformat(f"{month}-01T00:00:00+00:00")
            prior = [r for r in said if r["month"] < month]
            if len(prior) < 20:
                continue            # 🔴 표본이 모자라면 **표를 만들지 않는다**
            out[(league, month)] = pb.fit(prior, as_of=at)
    return out


def usual_of(rows: list[dict], row: dict, side: str) -> list[str]:
    """🔴 평소 XI — 그 경기 **이전** 그 팀 경기의 출전 분 가중 상위 11명."""
    from app.core.ratings import lineup_strength as ls
    team = row[side]
    past: list[dict] = []
    for r in rows:
        if r["utc"] >= row["utc"]:
            continue
        for s in ("home", "away"):
            if r[s] != team:
                continue
            mins = {p: (float(v[1]) - float(v[0]))
                    for p, v in dict(r[f"{s}_box"] or {}).items()}
            if not mins:
                mins = {p: 90.0 for p in r[f"{s}_ids"]}
            past.append({"utc": r["utc"], "comp": "league", "minutes": mins})
    at = datetime.fromisoformat(str(row["utc"]).replace("Z", "+00:00"))
    got, _why = ls.usual_xi(past, as_of=at)
    return got


def signals_of(rows: list[dict], tables: dict) -> int:
    """🔴 각 경기에 신호 원값을 붙인다. **표가 없는 경기는 건너뛴다**(0 금지)."""
    from app.core import lineupfix as lf
    got = 0
    for r in rows:
        table = tables.get((r["league"], r["month"]))
        if table is None or not getattr(table, "value", None):
            r["raw"] = None
            continue
        side = {}
        for s in ("home", "away"):
            side[s] = {"xi": r[f"{s}_ids"], "bench": r[f"{s}_bench"],
                       "usual": usual_of(rows, r, s)}
        box = {"value": dict(table.value), "kind": dict(table.kind)}
        raw, _why = lf.raw_v2_of(home=side["home"], away=side["away"],
                                 box=box)
        r["raw"] = raw
        r["usual"] = {s: list(side[s]["usual"]) for s in ("home", "away")}
        # 🔴 §7 — **평소 XI 로 뒀을 때**의 신호(확정 XI 와 나란히 볼 짝)
        said_u = {s: {**side[s], "xi": (side[s]["usual"] or side[s]["xi"])}
                  for s in ("home", "away")}
        raw_u, _w2 = lf.raw_v2_of(home=said_u["home"], away=said_u["away"],
                                  box=box)
        r["raw_usual"] = raw_u
        got += 1
    return got


def fit_ortho(rows: list[dict], keys: tuple[str, ...]) -> dict:
    """🔴 직교화 — 각 신호를 **축0 차**로 회귀해 `a·b` 를 낸다(훈련 표본만)."""
    import numpy as np
    out: dict[str, dict] = {}
    for k in keys:
        said = [(float(r["axis0"]), float(r["raw"][k])) for r in rows
                if r.get("raw") and k in r["raw"]]
        if len(said) < 30:
            continue
        x = np.array([a for a, _b in said])
        y = np.array([b for _a, b in said])
        if x.std() == 0:
            out[k] = {"a": float(y.mean()), "b": 0.0}
            continue
        b = float(((x - x.mean()) * (y - y.mean())).sum()
                  / ((x - x.mean()) ** 2).sum())
        out[k] = {"a": float(y.mean() - b * x.mean()), "b": b}
    return out


def _nll(g: dict, rows: list[dict], keys: tuple[str, ...], ridge: float,
         ortho: dict) -> float:
    """🔴 포아송 음의 로그우도 + 릿지(사전 평균 0) — λ 는 **M1 의 λ** 다."""
    from app.core import lineupfix as lf
    out = 0.0
    for r in rows:
        said, _w = lf.ortho({k: r["raw"][k] for k in keys if k in r["raw"]},
                            axis0=r["axis0"], plate={"ortho": ortho})
        move = sum(float(g.get(k) or 0.0) * float(v)
                   for k, v in said.items() if k != "L5")
        lh = float(r["lam"][0]) * math.exp(move)
        la = float(r["lam"][1]) * math.exp(-move)
        hg, ag = int(r["hg"]), int(r["ag"])
        out -= (-lh + hg * math.log(lh) - math.lgamma(hg + 1)
                - la + ag * math.log(la) - math.lgamma(ag + 1))
    return out + ridge * sum(float(v) ** 2 for v in g.values())


def fit_g(rows: list[dict], keys: tuple[str, ...], *, ridge: float,
          ortho: dict) -> dict:
    """🔴 계수 `g` — 릿지(사전 평균 0) 최대우도. 신호가 없으면 빈 표."""
    from scipy.optimize import minimize
    live = [k for k in keys if k != "L5"]
    if not live:
        return {k: 0.0 for k in keys}
    said = minimize(
        lambda v: _nll(dict(zip(live, v, strict=True)), rows, keys, ridge,
                       ortho),
        [0.0] * len(live), method="Nelder-Mead",
        options={"maxiter": 2000, "fatol": 1e-6})
    got = dict(zip(live, [float(x) for x in said.x], strict=True))
    return {**{k: 0.0 for k in keys}, **got}


def probs_of(rows: list[dict], *, g: dict, keys: tuple[str, ...],
             ortho: dict, sd: dict) -> list[list[float]]:
    """🔴 그 판의 확률 — `lineupfix.apply` 를 지난 λ 로 격자를 다시 만든다."""
    from app.core import lineupfix as lf
    from app.core import probfloor as pf
    out: list[list[float]] = []
    plate = {"adopted": list(keys), "g": dict(g), "sd": dict(sd),
             "ortho": dict(ortho)}
    for r in rows:
        lam = {"home": float(r["lam"][0]), "away": float(r["lam"][1])}
        if keys and r.get("raw"):
            lam, _why = lf.apply(lam, raw=r["raw"], plate=plate,
                                 axis0=r["axis0"])
        grid = pf.score_grid(lam_home=lam["home"], lam_away=lam["away"],
                             rho=0.0)
        mk = pf.markets_of(grid)
        out.append([mk["home"], mk["draw"], mk["away"]])
    return out


def main(argv: list[str]) -> int:
    import judge_models as jm

    from app.core import lineupfix as lf
    from app.core import metrics as me
    from app.core.ratings import player_pm as pm
    rows, why = load()
    print("# 🔴🔴 §6 비교 판 — 라인업 보정이 M1(B)을 이기나")
    print()
    print(why)
    if len(rows) < 200:
        print("🔴 표본이 모자라다(200 미만) — 시험하지 않는다")
        return 1
    rows.sort(key=lambda r: r["utc"])
    at = datetime.now(timezone.utc)
    # 🔴 **가치 v2 는 벌이 없다** — 릿지 회귀가 아니라 **집계**(90분당 xG+xA)이고
    #    표본이 적은 선수만 리그·포지션 평균으로 수축한다(450분 문턱).
    print("🔴 선수 가치 **v2**(박스 기록 · 90분당 xG+xA) — 반분 상관 "
          "J1 +0.54 · K1 +0.64(문턱 0.3 통과 · `tools/fit_box.py`)")
    tables = tables_of(rows)
    n_sig = signals_of(rows, tables)
    live = [r for r in rows if r.get("raw")]
    print(f"🔴 신호를 센 경기 **{n_sig}건**(표가 없어 못 센 경기 "
          f"{len(rows) - n_sig}건) · 그 중 분 단위 "
          f"{sum(1 for r in live if r['fine'])}건")
    print()
    seasons = sorted({r["season"] for r in live})
    print(f"시즌 {len(seasons)}개 — {' · '.join(seasons)}")
    print()
    # ── 🔴 시즌 교차 — 한 시즌을 빼고 적합해 **그 시즌**에서 잰다
    out: dict[str, dict] = {}
    for name, keys in PLATES:
        probs: list[list[float]] = []
        hits: list[int] = []
        fine: list[bool] = []
        gs: list[dict] = []
        caps: list[str] = []
        for s in seasons:
            train = [r for r in live if r["season"] != s]
            test = [r for r in live if r["season"] == s]
            if len(train) < 100 or not test:
                continue
            if not keys:
                probs += probs_of(test, g={}, keys=(), ortho={}, sd={})
            else:
                ortho = fit_ortho(train, keys)
                if len(ortho) < len([k for k in keys if k != "L5"]):
                    continue
                best = None
                for ridge in GS:
                    g = fit_g(train, keys, ridge=ridge, ortho=ortho)
                    val = _nll(g, train, keys, 0.0, ortho) / max(1, len(train))
                    if best is None or val < best[0]:
                        best = (val, g, ridge)
                g = best[1]
                import numpy as np
                sd = {k: float(np.std([float(r["raw"][k]) for r in train
                                       if k in r["raw"]]) or 0.0)
                      for k in keys}
                ok, why_cap = lf.check({"g": g, "sd": sd})
                caps.append(f"{s}: {why_cap}")
                gs.append({**g, "_ridge": best[2]})
                probs += probs_of(test, g=g, keys=keys, ortho=ortho, sd=sd)
            hits += [r["hit"] for r in test]
            fine += [r["fine"] for r in test]
        if not probs:
            out[name] = {"why": "🔴 적합·평가를 못 했다(시즌 교차 표본 부족)"}
            continue
        out[name] = {"probs": probs, "hits": hits, "fine": fine, "g": gs,
                     "caps": caps}
    base = out.get("B") or {}
    if "probs" not in base:
        print("🔴 기준(B)을 못 만들었다 — 멈춘다")
        return 1
    # 🔴 운영에 이미 깔린 판이 있나(L3 · 엄격히 이전) — 없으면 **보정 없음**이다
    for league in sorted({r["league"] for r in live}):
        got_plate, why_plate = lf.plate_of(league=league, as_of=at)
        print(f"- **{league}** 운영 판 — "
              + (f"{sorted(got_plate.get('adopted') or [])} · {why_plate}"
                 if got_plate else why_plate))
    print()
    def score(probs: list[list[float]], hits: list[int]) -> dict:
        """🔴 한 판의 지표 — 줄마다 세고 **구간 적중**은 `metrics.bands` 하나다."""
        lls = [me.logloss(pi, hi) for pi, hi in zip(probs, hits, strict=True)]
        dirs = [bool(me.direction_hit(pi, hi))
                for pi, hi in zip(probs, hits, strict=True)]
        said = me.bands([{"p": pi, "hit": hi}
                         for pi, hi in zip(probs, hits, strict=True)],
                        keys=("p",))
        return {"ll": sum(lls) / len(lls), "lls": lls,
                "dir": sum(dirs) / len(dirs), "dirs": dirs,
                "bands": {f: said[f]["p"]["rate"] for f in said}}

    def verdict(cand: dict, base0: dict, move: dict | None = None
                ) -> tuple[str, str, str, bool]:
        """🔴 판정 — 규칙은 **실행 전에 커밋한** `rule="lineup"` 하나다."""
        diff = me.paired(cand["lls"], base0["lls"])
        b = sum(1 for x, y in zip(cand["dirs"], base0["dirs"], strict=True)
                if x and not y)
        c = sum(1 for x, y in zip(cand["dirs"], base0["dirs"], strict=True)
                if y and not x)
        pv = jm.binom_two_sided(b, c)
        ok, _box, why = jm.passes(diff=diff, dir_rate=cand["dir"],
                                  base_dir=base0["dir"], p_value=pv,
                                  bands=cand["bands"],
                                  base_bands=base0["bands"],
                                  move=dict(move or {}), rule=RULE)
        # 🔴 **통과는 불리언이 말한다** — 사유 글자에 ✅ 가 있는지로 세면 조건
        #    하나만 통과한 판도 "채택"으로 둔다(실사고 2026-10-13: 그렇게 세어
        #    탈락한 판 다섯이 통과 목록에 들어갔다).
        return (f"{diff['mean']:+.4f} ({diff['lo']:+.4f}~{diff['hi']:+.4f})",
                f"{pv:.4f}", ("✅ **채택 후보**" if ok else "🔴 탈락") + f" {why}",
                bool(ok))

    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **§7 — 라인업이 실제로 움직이는 폭**(평소 XI → 확정 XI)
    # ══════════════════════════════════════════════════════════════
    print("## 🔴🔴 §7·(d) 평소 XI → 확정 XI 확률 차 분포")
    print()
    print("🔴 *예상 XI* 자리에 **평소 XI**(그 경기 **앞** 경기의 출전 분 가중 상위"
          " 11명)를 둔다 — 과거의 *그때 예상 XI* 는 어디에도 저장돼 있지 않다(#4).")
    print()
    print("| 판 | 쌍 | 평균 |Δ| | σ | 상위 10% | ≥3%p 경기 | 그 경기 방향(B / 판) |")
    print("|---|---|---|---|---|---|---|")
    moves: dict[str, dict] = {}
    import statistics as stt

    from app.core import probfloor as pf0
    for name, keys in PLATES:
        one = out.get(name) or {}
        if "probs" not in one or not keys:
            continue
        deltas: list[float] = []
        wide: list[tuple[list[float], list[float], int]] = []
        for s in seasons:
            train = [r for r in live if r["season"] != s]
            test = [r for r in live if r["season"] == s]
            if len(train) < 100 or not test:
                continue
            ortho = fit_ortho(train, keys)
            if len(ortho) < len([k for k in keys if k != "L5"]):
                continue
            best = None
            for ridge in GS:
                g = fit_g(train, keys, ridge=ridge, ortho=ortho)
                val = _nll(g, train, keys, 0.0, ortho) / max(1, len(train))
                if best is None or val < best[0]:
                    best = (val, g, ridge)
            g = best[1]
            for r in test:
                if not r.get("raw") or not r.get("raw_usual"):
                    continue
                pair = []
                for which in ("raw", "raw_usual"):
                    said, _w = lf.ortho(
                        {k: r[which][k] for k in keys if k in r[which]},
                        axis0=r["axis0"], plate={"ortho": ortho})
                    move = sum(float(g.get(k) or 0.0) * float(v)
                               for k, v in said.items() if k != "L5")
                    lh = float(r["lam"][0]) * math.exp(move)
                    la = float(r["lam"][1]) * math.exp(-move)
                    mk = pf0.markets_of(pf0.score_grid(lam_home=lh,
                                                       lam_away=la, rho=0.0))
                    pair.append([mk["home"], mk["draw"], mk["away"]])
                d = abs(pair[0][0] - pair[1][0])
                deltas.append(d)
                if d >= 0.03:
                    base_p = pf0.markets_of(pf0.score_grid(
                        lam_home=float(r["lam"][0]),
                        lam_away=float(r["lam"][1]), rho=0.0))
                    wide.append(([base_p["home"], base_p["draw"],
                                  base_p["away"]], pair[0], int(r["hit"])))
        if not deltas:
            print(f"| {name} | 0 | — | — | — | — | — |")
            moves[name] = {"mean": 0.0, "wide_n": 0, "wide_hit": 0.0,
                           "base_wide_hit": 0.0}
            continue
        top = sorted(deltas)[int(len(deltas) * 0.9):]
        said_w = "—"
        b_hit = c_hit = 0.0
        if wide:
            b_hit = sum(1 for bp, _cp, h in wide
                        if me.direction_hit(bp, h)) / len(wide)
            c_hit = sum(1 for _bp, cp, h in wide
                        if me.direction_hit(cp, h)) / len(wide)
            said_w = f"{b_hit:.1%} / {c_hit:.1%}"
        moves[name] = {"mean": stt.fmean(deltas), "wide_n": len(wide),
                       "wide_hit": c_hit, "base_wide_hit": b_hit}
        print(f"| {name} | {len(deltas)} | **{stt.fmean(deltas) * 100:.2f}%p** "
              f"| {stt.pstdev(deltas) * 100:.2f}%p | "
              f"{(stt.fmean(top) if top else 0.0) * 100:.2f}%p | "
              f"{len(wide)}건 | {said_w} |")
    print()
    print("⚠️ **전(B)** 은 보정이 0 이므로 이 표에서 Δ 가 **구조적으로 0** 이다 —"
          " 지금 운영에서 평소→확정 XI 가 만드는 폭은 진단에서 잰 **0.2~0.7%p**"
          "(M1 축0 안에서만 움직인 값)이다. 위 표의 Δ 는 **보정이 더하는 폭**이다.")
    print()

    base_s = score(base["probs"], base["hits"])
    print("| 판 | 경기 | 로그 손실 | 방향 적중 | 상위 30% | 20% | 10% | "
          "짝지은 차이(95%) | 맥니마 p | 판정 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    picks: list[dict] = []
    for name, _keys in PLATES:
        one = out.get(name) or {}
        if "probs" not in one:
            print(f"| {name} | — | — | — | — | — | — | — | — | "
                  f"{one.get('why', '🔴')} |")
            continue
        got = score(one["probs"], one["hits"])
        cells = " | ".join(f"{got['bands'][f]:.1%}" for f in (0.30, 0.20, 0.10))
        if name == "B":
            print(f"| {name} | {len(one['hits'])} | {got['ll']:.4f} | "
                  f"{got['dir']:.1%} | {cells} | — | — | **기준** |")
            continue
        d, pv, said, ok = verdict(got, base_s, moves.get(name))
        picks.append({"name": name, "ll": got["ll"], "ok": ok,
                      "keys": _keys})
        print(f"| {name} | {len(one['hits'])} | {got['ll']:.4f} | "
              f"{got['dir']:.1%} | {cells} | {d} | {pv} | {said} |")
    print()
    # 🔴🔴 **교체 시각 확보 경기 / 거친 판을 따로** 본다(§6 요구)
    print("## 🔴 하위 표본 — **교체 시각 확보**(J리그 정확한 시각) vs 그 밖(뛴 분)")
    print()
    print("| 판 | 시각 확보 경기 | 로그 손실 | 방향 | 그 밖 경기 | 로그 손실 | 방향 |")
    print("|---|---|---|---|---|---|---|")
    for name, _keys in PLATES:
        one = out.get(name) or {}
        if "probs" not in one:
            continue
        cells = []
        for want in (True, False):
            pr = [p for p, f in zip(one["probs"], one["fine"], strict=True)
                  if f is want]
            hh = [h for h, f in zip(one["hits"], one["fine"], strict=True)
                  if f is want]
            if not pr:
                cells += ["0", "—", "—"]
                continue
            g2 = score(pr, hh)
            cells += [str(len(hh)), f"{g2['ll']:.4f}", f"{g2['dir']:.1%}"]
        print(f"| {name} | " + " | ".join(cells) + " |")
    print()
    said_ok = [x for x in picks if x["ok"]]
    if said_ok:
        best = min(said_ok, key=lambda x: (x["ll"], len(x["keys"])))
        print(f"🔴🔴 **판정 — 채택: {best['name']}**(통과한 판 "
              f"{[x['name'] for x in said_ok]} 중 로그 손실 최저 · 겹치면 "
              f"단순한 쪽)")
    else:
        print("🔴🔴 **판정 — B 유지**(라인업 보정 판 가운데 **(a)(b)(c)(d) 를 "
              "전부** 통과한 것이 없다 · 규칙 `" + RULE + "`)")
    print()
    for name, _keys in PLATES:
        one = out.get(name) or {}
        for g in (one.get("g") or []):
            print(f"- **{name}** 계수 — "
                  + " · ".join(f"{k} {float(v):+.4f}" for k, v in g.items()))
        for c in (one.get("caps") or []):
            print(f"  · 상한 감시 {c}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
