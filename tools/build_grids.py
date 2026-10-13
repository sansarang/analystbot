"""🔴🔴 **§8-1 재료 — 경기별 세 격자**(통합 지시서 2026-10-13 밤).

```
PYTHONPATH=. python tools/build_grids.py
```

- `G_M1` : 7절까지 채택된 M1 판 → 격자(무승부 보정 **없음** · 라인업 보정 **없음**)
- `G_M3` : `probfloor`(**평가 시즌 밖** 계수 판)
- `G_Elo`: Elo → 바닥 λ → **독립 포아송**
- 규격 **0~10골** · 꼬리 적고 정규화 · `data/grids/<league>/<season>/<id>.npz`
- 한 격자라도 못 만든 경기 → **제외 목록·사유**(두 개로 몰래 섞지 않는다)

🔴 **채택분 반영** — §3 S1 · §4 S2(M1·Elo) · §5 · §6 **전부 탈락**했다. 그래서
   `G_M1` 은 **B 그대로**이고 `G_M3`·`G_Elo` 도 **현행 이월**이다(§7 전진 선택).
🔴 **EN5** — `as_of` 이후 정보는 없다(계수는 **평가 시즌 밖**에서만 적합한다).
🔴 **EN9** — 경기 목록 해시를 적는다(라인업 시험 표본과 같은 704경기).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

OUT = ROOT / "data/grids"


def rows_of() -> tuple[list[dict], str]:
    """🔴 백필 재생 + 시즌 + 공변량(그 경기 **앞** 경기로만 · L1)."""
    from forward_terms import _ctx_rows
    from app.core import context as _ctx
    from app.core import season as se
    # 🔴🔴 **국내 리그 재생 전부**를 읽는다(2,582경기 · 2026-10-13 밤 넷째 5번).
    #    ⚠️ `replay_big2` 만 보던 자리다 — 표본이 **2,000 문턱**을 넘었으므로
    #    앙상블·판정을 **같은 규칙으로 다시** 돌린다.
    back: list[dict] = []
    for name in ("replay_big2", "replay_mls", "replay_elc", "replay_sa",
                 "replay_pl"):
        path = ROOT / f"var/judge/{name}.json"
        if not path.exists():
            continue
        said = json.loads(path.read_text(encoding="utf-8"))
        back += said
        print(f"   · {name} {len(said)}경기", flush=True)
    ids = {}
    for r in json.loads((ROOT / "var/judge/lineup_rows2.json").read_text(
            encoding="utf-8")):
        ids[(str(r["utc"])[:10], r["home"], r["away"])] = str(r["fm_id"])
    out: list[dict] = []
    hist: dict[str, list[dict]] = {}
    gone = {"λ 없다": 0, "스코어 없다": 0, "시즌 모른다": 0}
    for r in sorted(back, key=lambda x: str(x.get("day"))):
        if r.get("hg") is None or r.get("ag") is None:
            gone["스코어 없다"] += 1
            continue
        if not r.get("lam"):
            gone["λ 없다"] += 1
            continue
        league = str(r.get("league") or "")
        day = str(r.get("day") or "")
        at = datetime.fromisoformat(f"{day}T12:00:00+00:00")
        season, _w = se.id_of(league=league, when=at)
        if not season:
            gone["시즌 모른다"] += 1
            continue
        home, away = str(r["home"]), str(r["away"])
        cov = dict(_ctx.covariates(_ctx_rows(hist.get(home, []), as_of=at),
                                   _ctx_rows(hist.get(away, []), as_of=at)))
        cov["diff"] = float(r["dr"]) / 100.0
        cov["pdiff"] = 0.0
        cov["abs_d"] = 0.0
        out.append({"id": ids.get((day, home, away), f"x{len(out)}"),
                    "league": league, "season": season, "day": day,
                    "home": home, "away": away,
                    "hg": int(r["hg"]), "ag": int(r["ag"]),
                    "hit": int(r["hit"]), "dr": float(r["dr"]),
                    "lam": [float(x) for x in r["lam"]], "cov": cov})
        for team, mine in ((home, True), (away, False)):
            hist.setdefault(team, []).append({
                "utc": f"{day}T00:00:00Z", "comp": "league",
                "gf": (r["hg"] if mine else r["ag"]),
                "ga": (r["ag"] if mine else r["hg"])})
    why = (f"경기 **{len(out)}건** · 버린 것 — "
           + " · ".join(f"{k} {v}건" for k, v in gone.items()))
    return out, why


def main(argv: list[str]) -> int:
    import numpy as np

    from app import rules
    from app.core import base as _base
    from app.core import ensemble as en
    # 🔴 격자 만들기는 `score_grid`·`compute` 만 쓴다 — **`floor_of` 는 안 쓴다**
    #    (그 함수가 운영 판을 읽는 문이다 · EN10).
    from app.core import probfloor as _pf2
    from app.core import probmodel as pm
    from compare_paths import _fit, m0_of
    from forward_terms import probs_of as _unused
    del _unused
    rows, why = rows_of()
    print("# 🔴🔴 §8-1 격자 셋 만들기")
    print()
    print(why)
    said_hash = hashlib.sha256(
        json.dumps([f"{r['day']}|{r['home']}|{r['away']}" for r in rows],
                   ensure_ascii=False).encode()).hexdigest()
    print(f"🔴 **EN9 경기 목록 해시** `{said_hash[:16]}…`(704경기 표본)")
    print()
    seasons = sorted({r["season"] for r in rows})
    kept = 0
    gone: dict[str, int] = {}
    #: 🔴 **E5 의 재료** — 그 리그·시즌에서 **앞서 센 경기 수**(시즌 초 판별)
    seen_before: dict[tuple, int] = {}
    made: list[dict] = []
    for s in seasons:
        train = [r for r in rows if r["season"] != s]
        test = [r for r in rows if r["season"] == s]
        if len(train) < 100 or not test:
            gone["훈련 표본 부족"] = gone.get("훈련 표본 부족", 0) + len(test)
            continue
        coef = _fit(train, adopted=set())          # 🔴 바닥 식만(채택 항 없음)
        # 🔴 Elo 바닥 — **훈련 구간**에서 리그별로 적합한다(EN5)
        by_kind: dict[str, dict] = {}
        from fit_base_model import _fit_rows
        for kind in sorted({r["league"] for r in train}):
            box = [(r["dr"], 2 - r["hit"]) for r in train
                   if r["league"] == kind]
            if len(box) >= 100:
                by_kind[kind] = _fit_rows(box)
        # 🔴 **묶음(pooled) 교차 적합** — 평가 시즌을 뺀 **모든 리그** 줄로.
        #    ⚠️ 리그마다 계수가 조금 다르지만, **운영 판보다 낙관이 덜하다**
        #       (그 판은 평가 시즌을 봤다). 어느 쪽을 썼는지 색인이 적는다.
        pooled = _fit_rows([(r["dr"], 2 - r["hit"]) for r in train])
        for r in test:
            kind = r["league"]
            co = by_kind.get(kind)
            said_fit = "리그 교차"
            if not co:
                # 🔴🔴 **EN10 — 운영 판을 쓰지 않는다**(지시 2026-10-13 밤 다섯째).
                #  ⚠️ 앞 판정에서 **1,380경기**가 `base_model.yaml`(전 표본 적합)
                #     로 만들어졌고, 그 판은 **평가 시즌을 이미 봤다** → 낙관.
                #  🔴 퇴로는 **여러 리그 묶음 적합**이다 — 평가 시즌을 **뺀**
                #     훈련 줄 전부(모든 리그)로 적합한다. 그러면 그 계수는
                #     *"평가 시즌을 한 번도 안 본"* 수다.
                co = pooled
                said_fit = "묶음 교차"
            if not co:
                gone["🔴 바닥 계수를 못 만들었다(훈련 표본 0)"] = gone.get(
                    "🔴 바닥 계수를 못 만들었다(훈련 표본 0)", 0) + 1
                continue
            # 🔴 리그 평균·홈 배율 — 표에서 온다(백필과 **같은 수**)
            mean = float(rules.goal_share(kind) or 1.3)
            box_base = rules.goal_baseline(kind)
            mul_a, _wa = pm.away_mul(home_share=box_base.get("home_share"),
                                     per_team=mean)
            mul_h = (float(box_base.get("home_share")) / mean
                     if box_base.get("home_share") else 1.0)
            floor = _base.triple_from(c1=co["c1"], c2=co["c2"],
                                      b_dr=co["b_dr"], dr=r["dr"])
            gone[f"⚠️ 바닥 {said_fit}"] = gone.get(f"⚠️ 바닥 {said_fit}", 0) + 1
            move = m0_of(floor, mean, mul_h, mul_a)
            if move is None:
                gone["바닥 λ 못 풀었다"] = gone.get("바닥 λ 못 풀었다", 0) + 1
                continue
            import math
            g_elo = _pf2.score_grid(
                lam_home=mean * mul_h * math.exp(move),
                lam_away=mean * mul_a * math.exp(-move), rho=0.0)
            lam3, _w3 = _pf2.compute(r["cov"], coef=coef, adopted=set())
            g_m3 = _pf2.score_grid(lam_home=lam3["home"],
                                   lam_away=lam3["away"], rho=0.0)
            g_m1 = _pf2.score_grid(lam_home=r["lam"][0],
                                   lam_away=r["lam"][1], rho=0.0)
            box: dict[str, dict] = {}
            bad = ""
            for name, grid in (("M1", g_m1), ("M3", g_m3), ("Elo", g_elo)):
                said, w2 = en.normalise(grid)
                if not said:
                    bad = f"{name}: {w2}"
                    break
                box[name] = said
            if bad:
                gone[bad[:30]] = gone.get(bad[:30], 0) + 1
                continue
            path = OUT / kind.replace(":", "_") / s.replace("/", "-")
            path.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                path / f"{r['id']}.npz",
                **{name: np.array([[box[name].get((h, a), 0.0)
                                    for a in range(en.MAXG + 1)]
                                   for h in range(en.MAXG + 1)])
                   for name in ("M1", "M3", "Elo")},
                meta=np.array([r["hg"], r["ag"], r["hit"]]))
            made.append({"id": r["id"], "league": kind, "season": s,
                         "day": r["day"], "hit": r["hit"],
                         "floor_fit": said_fit,
                         "n_before": seen_before.get((kind, s), 0)})
            seen_before[(kind, s)] = seen_before.get((kind, s), 0) + 1
            kept += 1
    (ROOT / "var/judge/grids_index.json").write_text(
        json.dumps({"hash": said_hash, "rows": made}, ensure_ascii=False),
        encoding="utf-8")
    print(f"🔴 격자를 적은 경기 **{kept}건** → `{OUT}` · 색인 "
          f"`var/judge/grids_index.json`")
    print("🔴 **제외 목록** — "
          + (" · ".join(f"{k} {v}건" for k, v in sorted(gone.items()))
             if gone else "없다"))
    print()
    print("⚠️ `G_M1` 에는 **무승부 보정·라인업 보정이 없다**(둘 다 판정에서 "
          "떨어졌다) · `G_M3`·`G_Elo` 의 계수는 **평가 시즌 밖**에서만 적합했다"
          "(EN5).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
