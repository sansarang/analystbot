"""🔴🔴 **§8-3·8-4·8-5·8-6 앙상블 적합·판정**(통합 지시서 2026-10-13 밤).

```
PYTHONPATH=. python tools/fit_ensemble.py
```

후보 — `E0` G_M1 단독(기준) · `E1` 0.5·M1+0.5·M3 **고정** · `E2` w 교차 적합 ·
`E3` w·M1+v·M3+(1−w−v)·Elo · `E4` **리그별 w**(그 리그 표본 < 300 → 전체 w).
단순함 순서 **E0 > E1 > E2 > E4 > E3**.

🔴 가중치는 **시즌 교차**로 고른다(격자 0.05) · **부트스트랩 200회** w 구간 ·
   폭 > 0.4 면 **"가중치 불안정"**. 판은 `data/ensemble/<league|all>/<as_of>.yaml`.
🔴 판정은 **실행 전 커밋된** `rule="season"`((a)~(d)) · 기준은 **E0**.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

STEP = 0.05
BOOT = 200
WIDE = 0.4
#: 🔴 리그별 w 를 쓰려면 그 리그 표본이 이만큼 필요하다(§8-3 E4)
MIN_LEAGUE = 300


def load() -> tuple[list[dict], str]:
    """🔴 격자 색인 → `{grids:{M1,M3,Elo}, hit, league, season, games}`."""
    import numpy as np
    box = json.loads((ROOT / "var/judge/grids_index.json").read_text(
        encoding="utf-8"))
    out: list[dict] = []
    seen: dict[tuple[str, str], int] = {}
    for one in sorted(box["rows"], key=lambda r: str(r["day"])):
        path = (ROOT / "data/grids" / str(one["league"]).replace(":", "_")
                / str(one["season"]).replace("/", "-") / f"{one['id']}.npz")
        if not path.exists():
            continue
        said = np.load(path)
        grids = {}
        for name in ("M1", "M3", "Elo"):
            arr = said[name]
            grids[name] = {(h, a): float(arr[h][a])
                           for h in range(arr.shape[0])
                           for a in range(arr.shape[1]) if arr[h][a] > 0}
        key = (str(one["league"]), str(one["season"]))
        meta = said["meta"]
        out.append({"grids": grids, "hit": int(one["hit"]),
                    "hg": int(meta[0]), "ag": int(meta[1]),
                    "league": str(one["league"]),
                    "season": str(one["season"]), "day": str(one["day"]),
                    "n_before": seen.get(key, 0)})
        seen[key] = seen.get(key, 0) + 1
    return out, (f"격자를 읽은 경기 **{len(out)}건** · 목록 해시 "
                 f"`{str(box['hash'])[:16]}…`(EN9)")


def marks(rows: list[dict]) -> None:
    """🔴🔴 경기마다 **구성 모형의 승무패 세 수**를 한 번만 만들어 둔다.

    🔴 혼합은 **선형**이다 — `markets_of(Σ w_k·G_k) = Σ w_k·markets_of(G_k)`
       (계약 `test_markets_come_from_the_blended_grid_only` 가 그것을 센다).
       그래서 **가중치 적합·부트스트랩은 세 수로** 하면 격자 혼합과 **같은 답**이
       나오고, 200만 번 격자를 섞지 않아도 된다(실측: 그 길은 멈췄다).
    ⚠️ 운영 경로는 그대로 **격자를 섞는다**(오버·핸디캡·BTTS 가 한 분포에서 나와야
       한다 · §8-2).
    """
    from app.core import probfloor as pf
    for r in rows:
        if "mk" in r:
            continue
        r["mk"] = {name: [v["home"], v["draw"], v["away"]]
                   for name, v in ((k, pf.markets_of(g))
                                   for k, g in r["grids"].items())}


def probs(rows: list[dict], w: dict) -> list[list[float]]:
    """🔴 그 가중치의 승무패 — **선형 혼합**(위 설명 · 격자 혼합과 같은 답)."""
    marks(rows)
    out = []
    for r in rows:
        got = [0.0, 0.0, 0.0]
        for name, weight in dict(w or {}).items():
            one = r["mk"].get(name)
            if one is None:
                got = None
                break
            for i in range(3):
                got[i] += float(weight) * one[i]
        out.append(got if got else list(r["mk"]["M1"]))
    return out


def ll_of(rows: list[dict], w: dict) -> float:
    """🔴 그 가중치의 평균 로그 손실(적합·부트스트랩이 부른다)."""
    from app.core import metrics as me
    p = probs(rows, w)
    return sum(me.logloss(pi, r["hit"])
               for pi, r in zip(p, rows, strict=True)) / max(1, len(rows))


def pick_w(rows: list[dict], *, keys=("M1", "M3")) -> tuple[dict, float]:
    """🔴 `w` 격자(0.05) — 로그 손실 최소. 두 재료면 한 축, 셋이면 단체 격자."""
    best = None
    steps = [round(i * STEP, 2) for i in range(int(1 / STEP) + 1)]
    if len(keys) == 2:
        for a in steps:
            w = {keys[0]: a, keys[1]: round(1 - a, 2)}
            got = ll_of(rows, w)
            if best is None or got < best[1]:
                best = (w, got)
    else:
        for a in steps:
            for b in steps:
                if a + b > 1.0 + 1e-9:
                    continue
                w = {keys[0]: a, keys[1]: b,
                     keys[2]: round(1 - a - b, 2)}
                if min(w.values()) < 0:
                    continue
                got = ll_of(rows, w)
                if best is None or got < best[1]:
                    best = (w, got)
    return best[0], best[1]


def main(argv: list[str]) -> int:
    import judge_models as jm

    from app.core import metrics as me
    from app.core import probfloor as pf
    rows, why = load()
    print("# 🔴🔴 §8 앙상블 — 적합과 판정")
    print()
    print(why)
    seasons = sorted({r["season"] for r in rows})
    print(f"시즌 {len(seasons)}개 — {' · '.join(seasons)} · 리그 "
          + " · ".join(f"{k} {sum(1 for r in rows if r['league'] == k)}"
                       for k in sorted({r['league'] for r in rows})))
    print()

    def score(p, h) -> dict:
        lls = [me.logloss(pi, hi) for pi, hi in zip(p, h, strict=True)]
        dirs = [bool(me.direction_hit(pi, hi))
                for pi, hi in zip(p, h, strict=True)]
        said = me.bands([{"p": pi, "hit": hi}
                         for pi, hi in zip(p, h, strict=True)], keys=("p",))
        return {"ll": sum(lls) / len(lls), "lls": lls,
                "dir": sum(dirs) / len(dirs), "dirs": dirs,
                "bands": {f: said[f]["p"]["rate"] for f in said}}

    # ── 🔴 시즌 교차로 후보마다 확률을 만든다
    cand: dict[str, list[list[float]]] = {}
    hits: list[int] = []
    order: list[dict] = []
    picks: dict[str, list[str]] = {}
    for s in seasons:
        train = [r for r in rows if r["season"] != s]
        test = [r for r in rows if r["season"] == s]
        if len(train) < 100 or not test:
            continue
        order += test
        hits += [r["hit"] for r in test]
        cand.setdefault("E0", []).extend(probs(test, {"M1": 1.0}))
        cand.setdefault("E1", []).extend(probs(test, {"M1": 0.5, "M3": 0.5}))
        w2, _l2 = pick_w(train)
        picks.setdefault("E2", []).append(f"{s} → M1 {w2['M1']:.2f}")
        cand.setdefault("E2", []).extend(probs(test, w2))
        w3, _l3 = pick_w(train, keys=("M1", "M3", "Elo"))
        picks.setdefault("E3", []).append(
            f"{s} → M1 {w3['M1']:.2f}/M3 {w3['M3']:.2f}/Elo {w3['Elo']:.2f}")
        cand.setdefault("E3", []).extend(probs(test, w3))
        # 🔴 E4 — 리그별 w(표본 < 300 이면 **전체 w**)
        got4: list[list[float]] = []
        said4: list[str] = []
        for r in test:
            box = [x for x in train if x["league"] == r["league"]]
            if len(box) >= MIN_LEAGUE:
                wl, _ll = pick_w(box)
                said4.append(f"{r['league']} 자체 w {wl['M1']:.2f}")
            else:
                wl = w2
                said4.append(f"{r['league']} 전체 w {w2['M1']:.2f}"
                             f"(표본 {len(box)} < {MIN_LEAGUE})")
            got4 += probs([r], wl)
        picks.setdefault("E4", []).append(f"{s} → " + " · ".join(
            sorted(set(said4))))
        cand["E4"] = cand.get("E4", []) + got4
    base = score(cand["E0"], hits)
    print("- 교차로 고른 가중치")
    for name in ("E2", "E3", "E4"):
        print(f"  · **{name}** — " + " / ".join(picks.get(name, [])))
    # 🔴 부트스트랩 w 구간(E2) — 폭 > 0.4 면 "불안정"
    rnd = random.Random(7)
    boot: list[float] = []
    for _ in range(BOOT):
        said = [rows[rnd.randrange(len(rows))] for _ in range(len(rows))]
        w, _l = pick_w(said)
        boot.append(float(w["M1"]))
    boot.sort()
    lo, hi = boot[int(BOOT * 0.025)], boot[int(BOOT * 0.975)]
    print(f"- **부트스트랩 {BOOT}회**(E2 의 `w(M1)`) — 중앙 "
          f"{boot[BOOT // 2]:.2f} · 95% **{lo:.2f}~{hi:.2f}**"
          + (f" · 🔴 폭 {hi - lo:.2f} > {WIDE} → **가중치 불안정**"
             if (hi - lo) > WIDE else f" · 폭 {hi - lo:.2f}"))
    print()
    print("| 후보 | 경기 | 로그 손실 | 방향 | 상위 30/20/10% | 짝지은 차이(95%)"
          " | 맥니마 p | 판정 |")
    print("|---|---|---|---|---|---|---|---|")
    picked: list[dict] = []
    for name in ("E0", "E1", "E2", "E3", "E4"):
        got = score(cand[name], hits)
        cells = " / ".join(f"{got['bands'][f]:.2%}" for f in (0.30, 0.20, 0.10))
        if name == "E0":
            print(f"| **E0**(G_M1 단독) | {len(hits)} | **{got['ll']:.4f}** | "
                  f"{got['dir']:.2%} | {cells} | — | — | **기준** |")
            continue
        diff = me.paired(got["lls"], base["lls"])
        b = sum(1 for x, y in zip(got["dirs"], base["dirs"], strict=True)
                if x and not y)
        c = sum(1 for x, y in zip(got["dirs"], base["dirs"], strict=True)
                if y and not x)
        pv = jm.binom_two_sided(b, c)
        ok, _box, said = jm.passes(
            diff=diff, dir_rate=got["dir"], base_dir=base["dir"], p_value=pv,
            bands=got["bands"], base_bands=base["bands"],
            size={"ll": base["ll"] - got["ll"],
                  "dir": got["dir"] - base["dir"],
                  "top20": got["bands"][0.20] - base["bands"][0.20]},
            rule="season")
        picked.append({"name": name, "ll": got["ll"], "ok": ok})
        print(f"| {name} | {len(hits)} | {got['ll']:.4f} | {got['dir']:.2%} | "
              f"{cells} | {diff['mean']:+.4f} "
              f"({diff['lo']:+.4f}~{diff['hi']:+.4f}) | {pv:.4f} | "
              + ("✅ **채택**" if ok else "🔴 탈락") + f" {said} |")
    print()
    # ── 🔴 8-5 추가 지표 — 방향 뒤집힘 · 하위 그룹 · 보호 줄
    flip = [i for i, (p1, p2) in enumerate(zip(cand["E0"], cand["E2"],
                                               strict=True))
            if max(range(3), key=lambda k: p1[k])
            != max(range(3), key=lambda k: p2[k])]
    print(f"- **방향 뒤집힘**(E0 vs E2) — **{len(flip)}경기**"
          + (f" · 그 경기에서 E0 {sum(1 for i in flip if me.direction_hit(cand['E0'][i], hits[i]))}"
             f" / E2 {sum(1 for i in flip if me.direction_hit(cand['E2'][i], hits[i]))} 적중"
             if flip else ""))
    early = [i for i, r in enumerate(order) if r["n_before"] <= 6 * 9]
    del early
    print()
    print("## 🔴 하위 그룹")
    print()
    print("| 그룹 | 경기 | E0 로그 손실 | E2 로그 손실 | E0 방향 | E2 방향 |")
    print("|---|---|---|---|---|---|")
    groups = {
        "시즌 초 6라운드 이내": [i for i, r in enumerate(order)
                                if r["n_before"] <= 6 * 9],
        "강팀 승 50~65%": [i for i, p in enumerate(cand["E0"])
                           if 0.50 <= max(p[0], p[2]) <= 0.65],
    }
    for name, idx in groups.items():
        if not idx:
            print(f"| {name} | 0 | — | — | — | — |")
            continue
        for key in ("E0", "E2"):
            pass
        e0 = score([cand["E0"][i] for i in idx], [hits[i] for i in idx])
        e2 = score([cand["E2"][i] for i in idx], [hits[i] for i in idx])
        print(f"| {name} | {len(idx)} | {e0['ll']:.4f} | {e2['ll']:.4f} | "
              f"{e0['dir']:.2%} | {e2['dir']:.2%} |")
    print()
    # 🔴 보호 줄 — 강팀 미승 ≥ 50% 경기의 **약팀 +1.5** · 더블찬스
    said_prot = 0
    hit_ah = hit_dc = 0
    from app.core import ensemble as en0
    for r, p, h in zip(order, cand["E2"], hits, strict=True):
        got, _w = en0.of(r["grids"], plate={"w": {"M1": 0.5, "M3": 0.5}})
        del got
        fav_home = p[0] >= p[2]
        no_win = 1.0 - (p[0] if fav_home else p[2])
        if no_win < 0.50:
            continue
        said_prot += 1
        # 🔴 **실제 스코어로** 센다 — 약팀 +1.5 는 *"두 골 차 이상으로 지지
        #    않았다"* 다(1골 차 패배·무승부·승리 모두 통과).
        gap = (int(r["ag"]) - int(r["hg"])) if fav_home \
            else (int(r["hg"]) - int(r["ag"]))
        hit_ah += 1 if gap + 1.5 > 0 else 0
        hit_dc += 1 if h != (0 if fav_home else 2) else 0
    if said_prot:
        print(f"- **보호 줄** — 강팀 미승 확률 ≥ 50% 경기 **{said_prot}건** · "
              f"약팀 **+1.5 적중 {hit_ah / said_prot:.1%}** · "
              f"더블찬스(약팀 승·무) 적중 **{hit_dc / said_prot:.1%}**")
    print()
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **판을 적는다**(§8-4 꼴) — 채택이 아니어도 **그림자용**으로 남긴다(§11)
    # ══════════════════════════════════════════════════════════════
    #
    #  🔴 `app/` 은 yaml 을 쓰지 않는다(계약) — **도구가** 적는다.
    import yaml
    w_all, ll_all = pick_w(rows)
    at = str(argv[1]) if len(argv) > 1 else "2026-10-13"
    said_ok0 = [x for x in picked if x["ok"]]
    best0 = (min(said_ok0, key=lambda x: (x["ll"], x["name"]))["name"]
             if said_ok0 else "")
    box = {"후보": (best0 or "E2"),
           "w": ({"M1": 0.5, "M3": 0.5} if best0 == "E1"
                 else {k: float(v) for k, v in w_all.items()}),
           "v": None, "n": len(rows),
           "기간": f"{min(r['day'] for r in rows)}~"
                   f"{max(r['day'] for r in rows)}",
           "로그 손실": round(float(ll_all), 6),
           "구간": [float(lo), float(hi)],
           "adopted": bool(best0),
           "shadow": not bool(best0),
           # 🔴 **배선은 아직 아니다** — 운영 확률은 ⑯ **안에서 격자로** 섞어야
           #    한다(C2: 모든 시장 줄이 **한 분포**에서 나와야 한다). 승무패만
           #    섞으면 오버·핸디캡이 그 확률과 **어긋난다**.
           "wired": False,
           "왜": (f"🔴 **{best0} 채택**((a)~(d) 통과) — ⚠️ 운영 배선은 ⑯ 안에서"
                  " **격자로** 해야 한다(C2) · 그때까지 운영 확률은 **M1 단독**"
                  " 이고 이 판은 **그림자**로만 쓰인다."
                  if best0 else
                  "🔴 **E0 유지** — (a)~(d) 를 전부 통과한 후보가 없다."),
           "불안정": bool((hi - lo) > WIDE)}
    said_path = ROOT / "data/ensemble/all" / f"{at}.yaml"
    said_path.parent.mkdir(parents=True, exist_ok=True)
    said_path.write_text(yaml.safe_dump(box, allow_unicode=True,
                                        sort_keys=False), encoding="utf-8")
    print()
    # 🔴 **적은 값을 그대로 말한다** — 전에는 `adopted: false` 를 **글자로 박아**
    #    두어 판이 채택이어도 "false" 라고 적혔다(2026-10-13 · 내 결함).
    print(f"🔴 **판을 적었다** — `{said_path.relative_to(ROOT)}` · 후보 "
          f"**{box['후보']}** · w {box['w']} · n {box['n']} · 로그 손실 "
          f"{ll_all:.4f} · `adopted: {str(box['adopted']).lower()}` · "
          f"`wired: false`")
    # 🔴 **EN2** — 운영이 그 판을 어떻게 보는가(엄격히 이전이라 오늘은 **없다**)
    from datetime import datetime, timezone
    from app.core import ensemble as en2
    for league in sorted({r["league"] for r in rows}) + ["all"]:
        got_plate, why_plate = en2.plate_of(
            league=league,
            as_of=datetime.fromisoformat(at).replace(tzinfo=timezone.utc))
        print(f"  · {league} 운영 판 — "
              + (f"w {got_plate.get('w')} · adopted "
                 f"{got_plate.get('adopted')}" if got_plate else why_plate))
    print()
    ok_list = [x for x in picked if x["ok"]]
    if ok_list:
        best = min(ok_list, key=lambda x: x["ll"])
        print(f"🔴🔴 **판정 — 채택: {best['name']}**(통과 "
              f"{[x['name'] for x in ok_list]} 중 로그 손실 최저)")
    else:
        print("🔴🔴 **판정 — E0 유지**((a)~(d) 를 전부 통과한 후보가 없다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
