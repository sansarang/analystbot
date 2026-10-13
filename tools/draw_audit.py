"""🔴🔴 **무 보정 측정**(수정 지시 2026-10-13 밤 2-①②) — **고치기 전 숫자**.

```
PYTHONPATH=. python tools/draw_audit.py
PYTHONPATH=. python tools/draw_audit.py --plate 2026-10-13   # 판도 적는다(2-④)
```

> ① 구간별(무 예측 0~20 / 20~25 / 25~30 / 30%+) 예측 평균 vs 실측 무승부율 ·
>    경기 수. λ 합 구간별 · 두 팀 λ 차 구간별 · 리그별 같은 표.
> ② 무와 엮인 줄 실측 — 강팀 미승 · ±0.5 핸디 · 오버 1.5/2.5 · 0-0 · 1-1.

🔴 재료는 **격자**다 — `data/grids/**/*.npz` 의 `M1`(운영 판 그 격자)과
   `meta`(실제 스코어·결과). 그래서 *"그때 봇이 말한 수"* 와 실제가 **같은 줄**에
   있다. λ 는 재생 덤프(`replay_*.json` 의 `lam`)에서 `(날짜·홈·원정)` 으로 붙인다.
🔴 **0-0 포함**이다(`backfill.score_of` 수정 뒤 재생 · 2026-10-12).
⚠️ 이 도구는 **확률을 바꾸지 않는다** — 표와 판(`data/draw_bands/<as-of>.yaml`)만
   만든다. 카드 표시는 그 판을 **읽기만** 한다(2-④ · 확률 값 불변).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 무 예측 구간 — 지시의 그 넷(`(이름, 하한, 상한)`)
DRAW_BANDS: tuple[tuple[str, float, float], ...] = (
    ("0~20%", 0.0, 0.20), ("20~25%", 0.20, 0.25),
    ("25~30%", 0.25, 0.30), ("30%+", 0.30, 1.01))

#: 🔴 λ 합 구간 · 두 팀 λ 차 구간
SUM_BANDS = (("< 2.2", 0.0, 2.2), ("2.2~2.8", 2.2, 2.8), ("> 2.8", 2.8, 99.0))
GAP_BANDS = (("< 0.3", 0.0, 0.3), ("0.3~0.7", 0.3, 0.7), ("> 0.7", 0.7, 99.0))


def band_of(x: float, rows) -> str:
    for name, lo, hi in rows:
        if lo <= float(x) < hi:
            return name
    return rows[-1][0]


def load() -> tuple[list[dict], str]:
    """🔴 격자 + 실제 결과 + λ. `(줄, 사유)`."""
    import numpy as np

    from replays import load as _replays
    box = json.loads((ROOT / "var/judge/grids_index.json").read_text(
        encoding="utf-8"))
    lam: dict[tuple, list] = {}
    rows_bf, why_bf = _replays()
    for r in rows_bf:
        if r.get("lam"):
            lam[(str(r.get("day")), str(r.get("home")),
                 str(r.get("away")))] = [float(x) for x in r["lam"]]
    out: list[dict] = []
    gone = {"격자 파일 없다": 0, "λ 없다": 0}
    for one in box["rows"]:
        path = (ROOT / "data/grids" / str(one["league"]).replace(":", "_")
                / str(one["season"]).replace("/", "-") / f"{one['id']}.npz")
        if not path.exists():
            gone["격자 파일 없다"] += 1
            continue
        said = np.load(path)
        arr = said["M1"]
        grid = {(h, a): float(arr[h][a]) for h in range(arr.shape[0])
                for a in range(arr.shape[1]) if arr[h][a] > 0}
        meta = said["meta"]
        key = (str(one["day"]), str(one.get("home")), str(one.get("away")))
        said_lam = lam.get(key)
        if said_lam is None:
            gone["λ 없다"] += 1
        out.append({"grid": grid, "hg": int(meta[0]), "ag": int(meta[1]),
                    "hit": int(meta[2]), "league": str(one["league"]),
                    "season": str(one["season"]), "day": str(one["day"]),
                    "lam": said_lam})
    return out, (f"격자 **{len(out)}경기** · λ 붙은 경기 "
                 f"{sum(1 for r in out if r['lam'])}건 · {why_bf} · 버린 것 — "
                 + " · ".join(f"{k} {v}건" for k, v in gone.items()))


def lines_of(r: dict) -> dict:
    """🔴 그 경기의 **예측**과 **실측**을 같은 열쇠로(②의 재료)."""
    from app.core import probfloor as _pf
    mk = _pf.markets_of(r["grid"])
    hg, ag = int(r["hg"]), int(r["ag"])
    fav_home = float(mk["home"]) >= float(mk["away"])
    # 🔴 강팀 미승 = 무 + 약팀 승
    no_win = 1.0 - (float(mk["home"]) if fav_home else float(mk["away"]))
    real_no_win = (1.0 if (hg <= ag if fav_home else ag <= hg) else 0.0)
    ah = dict(mk.get("ah") or {})
    over = dict(mk.get("over") or {})
    return {
        "무": (float(mk["draw"]), 1.0 if hg == ag else 0.0),
        "강팀 미승": (no_win, real_no_win),
        "홈 -0.5": (float(ah.get("home-0.5", 0.0)), 1.0 if hg > ag else 0.0),
        "홈 +0.5": (float(ah.get("home+0.5", 0.0)), 1.0 if hg >= ag else 0.0),
        "오버 1.5": (float(over.get(1.5, 0.0)), 1.0 if hg + ag > 1.5 else 0.0),
        "오버 2.5": (float(over.get(2.5, 0.0)), 1.0 if hg + ag > 2.5 else 0.0),
        "0-0": (float(r["grid"].get((0, 0), 0.0)),
                1.0 if (hg, ag) == (0, 0) else 0.0),
        "1-1": (float(r["grid"].get((1, 1), 0.0)),
                1.0 if (hg, ag) == (1, 1) else 0.0)}


def table(rows: list[dict], *, key, bands, title: str) -> list[dict]:
    """🔴 구간표 한 장 — 예측 평균 vs 실측 · 경기 수 · 편차."""
    out: list[dict] = []
    print()
    print(f"### {title}")
    print()
    print("| 구간 | 경기 | 예측 평균 | 실측 무승부율 | 편차(예측−실측) |")
    print("|---|---|---|---|---|")
    for name, _lo, _hi in bands:
        box = [r for r in rows if key(r) == name]
        if not box:
            # 🔴 **빈 구간도 판에 적는다** — 카드가 *"그 구간은 표본 0"* 이라고
            #    말할 수 있어야 한다(조용히 빠지면 *"구간에 안 든다"* 가 된다).
            out.append({"band": name, "n": 0, "pred": None, "real": None,
                        "diff": None})
            print(f"| {name} | 0 | — | — | — |")
            continue
        p = sum(float(r["_p"]) for r in box) / len(box)
        y = sum(1 for r in box if r["hg"] == r["ag"]) / len(box)
        out.append({"band": name, "n": len(box), "pred": round(p, 4),
                    "real": round(y, 4), "diff": round(p - y, 4)})
        print(f"| {name} | {len(box)} | {p:.1%} | {y:.1%} | "
              f"**{p - y:+.1%}** |")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plate", default="", help="판을 적을 as-of 날짜")
    args = ap.parse_args(argv[1:])
    from app.core import probfloor as _pf
    rows, why = load()
    print("# 🔴🔴 무 보정 측정 — **고치기 전 숫자**(2-①②)")
    print()
    print(f"- {why}")
    for r in rows:
        mk = _pf.markets_of(r["grid"])
        r["_p"] = float(mk["draw"])
        r["_lines"] = lines_of(r)
    # ── ① 구간표 셋 + 리그별
    said_band = table(rows, key=lambda r: band_of(r["_p"], DRAW_BANDS),
                      bands=DRAW_BANDS, title="① 무 예측 구간별")
    said_lam = [r for r in rows if r["lam"]]
    table(said_lam, key=lambda r: band_of(sum(r["lam"]), SUM_BANDS),
          bands=SUM_BANDS, title=f"① λ 합 구간별(λ 붙은 {len(said_lam)}경기)")
    table(said_lam, key=lambda r: band_of(abs(r["lam"][0] - r["lam"][1]),
                                          GAP_BANDS),
          bands=GAP_BANDS, title="① 두 팀 λ 차 구간별")
    kinds = sorted({r["league"] for r in rows})
    print()
    print("### ① 리그별")
    print()
    print("| 리그 | 경기 | 예측 평균 | 실측 무승부율 | 편차 |")
    print("|---|---|---|---|---|")
    per_league: dict[str, dict] = {}
    for kind in kinds:
        box = [r for r in rows if r["league"] == kind]
        p = sum(r["_p"] for r in box) / len(box)
        y = sum(1 for r in box if r["hg"] == r["ag"]) / len(box)
        per_league[kind] = {"n": len(box), "pred": round(p, 4),
                            "real": round(y, 4), "diff": round(p - y, 4)}
        print(f"| `{kind}` | {len(box)} | {p:.1%} | {y:.1%} | "
              f"**{p - y:+.1%}** |")
    # ── ② 무와 엮인 줄
    print()
    print("### ② 무와 엮인 줄 — 예측 vs 실측(전 표본)")
    print()
    print("| 줄 | 경기 | 예측 평균 | 실측 | 편차 |")
    print("|---|---|---|---|---|")
    names = list(rows[0]["_lines"]) if rows else []
    said_lines: dict[str, dict] = {}
    for nm in names:
        p = sum(r["_lines"][nm][0] for r in rows) / len(rows)
        y = sum(r["_lines"][nm][1] for r in rows) / len(rows)
        said_lines[nm] = {"pred": round(p, 4), "real": round(y, 4),
                          "diff": round(p - y, 4)}
        print(f"| {nm} | {len(rows)} | {p:.1%} | {y:.1%} | **{p - y:+.1%}** |")
    # ── 판(2-④) — 카드가 **읽기만** 한다
    if args.plate:
        import yaml
        box = {"as_of": args.plate, "n": len(rows),
               "bands": said_band, "leagues": per_league,
               "lines": said_lines,
               "왜": ("무 예측 구간별 예측 평균 vs 실측(0-0 포함 백필) — "
                      "카드 표시 전용이고 확률을 바꾸지 않는다(2-④)")}
        path = ROOT / "data/draw_bands" / f"{args.plate}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(box, allow_unicode=True,
                                       sort_keys=False), encoding="utf-8")
        print()
        print(f"🔴 **판을 적었다** — `{path.relative_to(ROOT)}`(카드 표시 전용)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
