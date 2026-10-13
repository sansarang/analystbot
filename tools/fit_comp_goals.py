"""🔴🔴 **§5-3-c 대회 자체 득점·홈 이점 실측** — 국내 리그 값을 **빌리지 않는다**.

```
PYTHONPATH=. python tools/fit_comp_goals.py --comp league:ACLE --seasons 3
```

> (c) 홈 이점: **그 대회 자체 실측**(최근 3시즌 · 대회별 판). … 중립 경기(결승 등)
> → 홈 이점 0. (지시서 2026-10-13 밤 셋째 §5-3-c)

🔴 **재료는 대회 일정 한 장**이다 — fotmob `/leagues/<id>/matches` 의
   `status.scoreStr`(실측 2026-10-13: `"1 - 0"`). 그래서 시즌당 **한 번** 받는다
   (경기 페이지를 다 받지 않는다).
🔴 **중립 단계는 뺀다**(CC3) — 중립 여부는 `competition.neutral_of` 가 표에서 읽는다.
🔴 적는 곳 둘 — `config/goal_baselines.yaml`(운영 ⑯ 이 읽는 그 표) ·
   `data/comp_home/<대회>/<날짜>.yaml`(`offsets.home_of` 가 읽는 판).
⚠️ **표본 20경기 미만이면 적지 않는다**(손값 금지 · 그 칸은 미산출로 남는다).
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

MIN_GAMES = 20
_SCORE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


async def rows_of(comp: str, *, seasons: int) -> tuple[list[dict], str]:
    """🔴 그 대회의 끝난 경기 — `(홈골, 원정골, 단계)`. 일정 한 장에서 온다."""
    from app.collect import fotmob as fm
    from app.core import competition as _cp
    from app.net import Net
    ids = [str(x) for x in ((_cp.row_of(comp).get("sources") or {})
                            .get("fotmob_ids") or [])]
    if not ids:
        return [], f"🔴 `{comp}` 의 fotmob id 가 표에 없다"
    net = Net(cache=True)
    page = await net.get(fm.league_matches_url(ids[0], "x"))
    j = fm.payload(getattr(page, "text", "") or "") or {}
    said = fm.league_seasons(j)
    out: list[dict] = []
    box: list[str] = []
    for i, season in enumerate(said[:max(1, int(seasons))]):
        if i == 0:
            pp = ((j.get("props") or {}).get("pageProps") or {})
        else:
            more = await net.get(fm.league_matches_url(ids[0], "x")
                                 + f"?season={season}")
            pp = (((fm.payload(getattr(more, "text", "") or "") or {})
                   .get("props") or {}).get("pageProps") or {})
        rows = ((pp.get("fixtures") or {}).get("allMatches")) or []
        add = 0
        for m in rows:
            st = dict(m.get("status") or {})
            if not st.get("finished"):
                continue
            got = _SCORE.match(str(st.get("scoreStr") or ""))
            if not got:
                continue
            out.append({"hg": int(got.group(1)), "ag": int(got.group(2)),
                        "stage": str(m.get("roundName") or m.get("round")
                                     or ""), "season": str(season)})
            add += 1
        box.append(f"{season} {add}경기")
    return out, " · ".join(box)


def write_plates(comp: str, rows: list[dict], *, why: str) -> str:
    """🔴 두 판을 적는다(운영 표 + 대회 홈 이점 판). 돌려주는 것은 보고 글."""
    import yaml

    from app.core import competition as _cp
    keep = [r for r in rows
            if not _cp.neutral_of(comp, stage=str(r.get("stage") or ""))[0]]
    n = len(keep)
    if n < MIN_GAMES:
        return (f"🔴 **적지 않았다** — 중립 아닌 경기 {n}건(< {MIN_GAMES}) · "
                f"그 칸은 **미산출**로 남는다(손값 금지)")
    gpm = sum(r["hg"] + r["ag"] for r in keep) / n
    home = sum(r["hg"] for r in keep) / n
    mul = home / (gpm / 2.0) if gpm else 1.0
    at = datetime.now(timezone.utc).date().isoformat()
    # ── 🔴 ① 운영 표(`config/goal_baselines.yaml`) — **그 열쇠 블록만** 더한다
    path = ROOT / "config/goal_baselines.yaml"
    said = path.read_text(encoding="utf-8")
    block = (f"  {comp}:\n"
             f"    goals_per_match: {round(gpm, 4)}\n"
             f"    home_share: {round(home, 4)}\n"
             f"    n: {n}\n"
             f"    n_home: {n}\n"
             f"    source: fotmob {comp} 자체 실측({why}) · 중립 단계 제외(CC3)"
             f" · tools/fit_comp_goals.py {at}\n")
    if f"\n  {comp}:\n" in said:
        said = re.sub(rf"\n  {re.escape(comp)}:\n(?:    .*\n)+",
                      "\n" + block, said, count=1)
    else:
        said = said.replace("kinds:\n", "kinds:\n" + block, 1)
    path.write_text(said, encoding="utf-8")
    # ── 🔴 ② 대회 홈 이점 판(`offsets.home_of` 가 읽는다)
    from app.core import offsets as off
    said_home = off.HOME_BOX / comp.replace(":", "_") / f"{at}.yaml"
    said_home.parent.mkdir(parents=True, exist_ok=True)
    said_home.write_text(yaml.safe_dump(
        {"대회": comp, "home_mul": round(float(mul), 4),
         "goals_per_match": round(float(gpm), 4), "n": n,
         "왜": f"그 대회 자체 실측({why}) · 중립 단계 제외 · 국내 리그 값을 "
               f"빌리지 않는다(CC1)"},
        allow_unicode=True, sort_keys=False), encoding="utf-8")
    return (f"✅ **적었다** — 경기당 **{gpm:.4f}골** · 홈 몫 **{home:.4f}** "
            f"(배율 ×{mul:.3f}) · 표본 **{n}경기**({why}) → "
            f"`config/goal_baselines.yaml` · `{said_home.relative_to(ROOT)}`")


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", required=True)
    ap.add_argument("--seasons", type=int, default=3)
    args = ap.parse_args(argv[1:])
    rows, why = await rows_of(args.comp, seasons=args.seasons)
    print(f"# 🔴🔴 {args.comp} 대회 자체 득점·홈 이점")
    print()
    print(f"- 받은 경기 **{len(rows)}건** — {why}")
    if not rows:
        print("🔴 **미산출** — 받은 경기가 없다")
        return 0
    print("- " + write_plates(args.comp, rows, why=why))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
