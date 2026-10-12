"""🔴🔴 **리그용 ② 환산 계수 적합** — `ΔS`(선발 로그 가치 합 차) → **리그 Elo 점수**.

```
PYTHONPATH=. python tools/fit_ds_to_dr_league.py --league league:SA --fotmob 55 \
    --seasons 2 --write
```

🔴 왜 새 도구인가 — `tools/fit_ds_to_dr.py` 는 **대표팀 전용**이다(그 파일이
   *"클럽 경기는 섞지 않는다 — 클럽 Elo 는 `leagueelo` 로 따로 굴린다"* 라고 적었다).
   그래서 리그 대회에는 `ds_to_dr` 이 **없었고**, ② 라인업 보정이 리그에서
   *"🔴 환산 계수가 없다 — 확률을 움직이지 않았다"* 로 끊겼다(실측 2026-10-13:
   토리노·코번트리 카드 두 장).

🔴 재는 식은 **그 파일과 같다**: `dr = a + b·(S_home − S_away)`, `b` 가 `ds_to_dr`.
   · `S` = Σ log(선발 11명 `marketValue`) — ② 와 **같은 식**(사본 금지: 그 식은
     `app/core/playervalue.log_sum` 이 든다).
   · `dr` = **그 경기 전** 리그 자체 Elo 차(`var/league_elo/<날>/<리그>.json` 의
     `fit_rows` 가 경기 전 등급을 들고 있다 — 누설 없음).
🔴 **R² 와 표본을 함께 적는다**. 문턱(`MIN_R2`·`MIN_ROWS`) 미달이면 **적지 않는다** —
   그때 ② 는 전처럼 전력 변화율만 보인다(지어내지 않는다).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 적합을 **쓰기로** 하는 문턱 — 그 아래면 적지 않는다
MIN_R2 = 0.20
MIN_ROWS = 100


async def rows_of(net, lid: str, *, seasons: int) -> list[dict]:
    """🔴 `(ΔS, 경기)` 재료 — 경기 페이지에서 **선발 가치**를 읽는다(캐시 재사용)."""
    from app.collect import fotmob as fm
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
    out: list[dict] = []
    done = [r for r in said if r.get("finished") and r.get("utc")]
    for i, one in enumerate(sorted(done, key=lambda r: str(r["utc"])), 1):
        if i % 50 == 0:
            print(f"   … 가치 {i}/{len(done)}", flush=True)
        page = await net.get(fm.match_url(str(one["id"])))
        j = fm.payload(getattr(page, "text", "") or "")
        if not j:
            continue
        lu = ((j.get("props") or {}).get("pageProps") or {}).get(
            "content", {}).get("lineup") or {}
        vals: dict[str, list[float]] = {}
        for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
            box = dict(lu.get(key) or {})
            got = []
            for p in (box.get("starters") or []):
                said_v = p.get("marketValue")
                if isinstance(said_v, (int, float)) and float(said_v) > 0:
                    got.append(float(said_v))
                elif isinstance(said_v, str):
                    # ⚠️ fotmob 은 `"€12.5M"` 꼴로도 준다 — 그 꼴을 읽는다
                    num = "".join(c for c in said_v if c.isdigit() or c == ".")
                    if num:
                        mul = (1e6 if "M" in said_v.upper()
                               else (1e3 if "K" in said_v.upper() else 1.0))
                        got.append(float(num) * mul)
            vals[side] = got
        if len(vals["home"]) < 8 or len(vals["away"]) < 8:
            continue              # 🔴 선발 가치가 모자란 경기는 **버린다**
        out.append({"utc": str(one["utc"]), "home": one["home"],
                    "away": one["away"],
                    "s_home": sum(math.log(v) for v in vals["home"]),
                    "s_away": sum(math.log(v) for v in vals["away"]),
                    "n_home": len(vals["home"]), "n_away": len(vals["away"])})
    return out


def elo_before(league_file: Path) -> dict:
    """🔴 `(날짜, 홈, 원정) → dr` — **경기 전** 등급 차(그 파일이 든 그 수)."""
    j = json.loads(league_file.read_text(encoding="utf-8"))
    out: dict = {}
    for r in (j.get("fit_rows") or []):
        key = (str(r.get("when"))[:10], str(r.get("home")), str(r.get("away")))
        out[key] = float(r.get("home_elo", 0.0)) - float(r.get("away_elo", 0.0))
    return out


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--fotmob", required=True)
    ap.add_argument("--elo-file", default="")
    ap.add_argument("--seasons", type=int, default=2)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv[1:])
    import numpy as np

    from app.net import Net
    short = str(args.league).split(":")[-1]
    said_file = Path(args.elo_file) if args.elo_file else sorted(
        (ROOT / "var/league_elo").glob(f"*/{short}.json"))[-1]
    print(f"# 🔴🔴 리그 ② 환산 계수 적합 — `{args.league}`")
    print()
    print(f"Elo 파일: `{said_file.relative_to(ROOT)}`")
    net = Net(cache=True)
    rows = await rows_of(net, str(args.fotmob), seasons=int(args.seasons))
    elo = elo_before(said_file)
    pairs: list[tuple[float, float]] = []
    miss = 0
    for r in rows:
        key = (str(r["utc"])[:10], r["home"], r["away"])
        dr = elo.get(key)
        if dr is None:
            miss += 1
            continue
        pairs.append((r["s_home"] - r["s_away"], dr))
    print(f"선발 가치를 읽은 경기 **{len(rows)}건** · Elo 와 이어진 경기 "
          f"**{len(pairs)}건**(못 이은 것 {miss}건)")
    print()
    if len(pairs) < MIN_ROWS:
        print(f"🔴 표본 {len(pairs)}건 < {MIN_ROWS} — **적지 않는다**"
              "(② 는 전력 변화율만 보인다)")
        return 1
    x = np.array([p[0] for p in pairs])
    y = np.array([p[1] for p in pairs])
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - (ss_res / ss_tot if ss_tot else 1.0)
    print("| 수 | 값 |")
    print("|---|---|")
    print(f"| `ds_to_dr`(b) | **{b:+.4f}** Elo 점/ΔS 1단위 |")
    print(f"| 절편(a) | {a:+.2f} |")
    print(f"| R² | **{r2:.4f}** |")
    print(f"| 표본 | {len(pairs)}경기 |")
    print(f"| ΔS 표준편차 | {float(x.std()):.3f} |")
    print(f"| → ΔS 1σ 가 움직이는 Elo | **{b * float(x.std()):+.1f}점** |")
    print()
    if r2 < MIN_R2:
        print(f"🔴 **R² {r2:.4f} < {MIN_R2}** — 쓰지 않는다(적지 않는다). "
              "⚠️ 선발 가치 합이 리그 Elo 차를 그만큼 설명하지 못한다.")
        return 0
    if not args.write:
        print("⚠️ `--write` 가 없다 — 적지 않았다(화면만)")
        return 0
    import yaml
    p = ROOT / "config/base_model.yaml"
    said = p.read_text(encoding="utf-8")
    box = yaml.safe_load(said) or {}
    models = dict(box.get("models") or {})
    m = dict(models.get(str(args.league)) or {})
    if not m:
        print(f"🔴 `{args.league}` 계수 블록이 없다 — 먼저 `fit_base_model --league`")
        return 1
    m["ds_to_dr"] = round(float(b), 4)
    m["ds_fit"] = {"n": len(pairs), "r2": round(float(r2), 4),
                   "intercept": round(float(a), 4),
                   "x_std": round(float(x.std()), 4),
                   "fitted_at": str(said_file.parent.name),
                   "tool": "tools/fit_ds_to_dr_league.py",
                   "note": ("리그 자체 Elo 차 ~ 선발 로그 가치 합 차 · "
                            "경기 전 등급(fit_rows)")}
    models[str(args.league)] = m
    box["models"] = models
    head = "".join(ln for ln in said.splitlines(True) if ln.startswith("#"))
    body = ["models:"]
    for kind, one in models.items():
        body.append(f"  {kind}:")
        for k, v in dict(one).items():
            body.append(f"    {k}: {json.dumps(v, ensure_ascii=False)}")
    p.write_text(head + "\n" + "\n".join(body) + "\n", encoding="utf-8")
    print(f"🔴 적었다 — `config/base_model.yaml` 의 `{args.league}.ds_to_dr`")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
