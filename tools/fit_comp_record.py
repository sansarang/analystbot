"""🔴🔴 **대회 홈/원정 성적**(사용자 지시 2026-10-13 ①) — 직전 2시즌.

```
PYTHONPATH=. python tools/fit_comp_record.py --comp league:ACLE --seasons 2
```

> ① 대륙 대회 카드에 "그 팀의 대회 홈/원정 성적(직전 2시즌)" 칸 추가 —
>   S03 홈 승률 ⬜ 를 **대회 일정 표**로 채운다.

🔴 재료는 **대회 일정 한 장**이다(시즌당 한 번) — fotmob `/leagues/<id>/matches`
   의 `status.scoreStr`. 경기 페이지를 다 받지 않는다(`fit_comp_goals` 와 같은 길).
🔴 두 가지를 적는다 —
   ① **대회 전체** 홈/원정 승률(그 차이가 S03 의 `win_pct_delta` 다)
   ② **팀별** 홈·원정 성적(승/무/패·득·실·경기 수)
🔴 **중립 단계는 뺀다**(CC3 · 홈이 없는 경기는 홈 이점을 말할 수 없다).
⚠️ 판은 `data/comp_record/<대회>/<as-of>.yaml` 이고 **표시 전용**이다 —
   λ 는 `goal_baselines.home_share`(득점 실측)만 쓴다(확률 불변).
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

_SCORE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


async def rows_of(comp: str, *, seasons: int) -> tuple[list[dict], str]:
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
        add = 0
        for m in (((pp.get("fixtures") or {}).get("allMatches")) or []):
            st = dict(m.get("status") or {})
            if not st.get("finished"):
                continue
            got = _SCORE.match(str(st.get("scoreStr") or ""))
            if not got:
                continue
            out.append({"home": str((m.get("home") or {}).get("name") or ""),
                        "away": str((m.get("away") or {}).get("name") or ""),
                        "hg": int(got.group(1)), "ag": int(got.group(2)),
                        "stage": str(m.get("roundName") or m.get("round")
                                     or ""), "season": str(season)})
            add += 1
        box.append(f"{season} {add}경기")
    return out, " · ".join(box)


def build(comp: str, rows: list[dict]) -> dict:
    """🔴 대회 전체 홈 우위 + 팀별 홈/원정 성적."""
    from app.core import competition as _cp
    keep = [r for r in rows
            if not _cp.neutral_of(comp, stage=str(r.get("stage") or ""))[0]]
    hw = sum(1 for r in keep if r["hg"] > r["ag"])
    dr = sum(1 for r in keep if r["hg"] == r["ag"])
    aw = len(keep) - hw - dr
    teams: dict[str, dict] = {}
    for r in keep:
        for side in ("home", "away"):
            name = r[side]
            said = teams.setdefault(name, {
                "home": {"w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "n": 0},
                "away": {"w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "n": 0}})
            mine = said[side]
            gf = r["hg"] if side == "home" else r["ag"]
            ga = r["ag"] if side == "home" else r["hg"]
            mine["n"] += 1
            mine["gf"] += gf
            mine["ga"] += ga
            mine["w" if gf > ga else ("d" if gf == ga else "l")] += 1
    n = len(keep) or 1
    return {
        "대회": comp, "n": len(keep),
        "competition": {
            "home_games": len(keep),
            "home_win_pct": round(100 * hw / n, 1),
            "away_win_pct": round(100 * aw / n, 1),
            "draw_pct": round(100 * dr / n, 1),
            # 🔴 S03 이 읽는 그 수 — **홈 승률 − 원정 승률**(%p)
            "win_pct_delta": round(100 * (hw - aw) / n, 1),
            "goals_delta": round(
                sum(r["hg"] - r["ag"] for r in keep) / n, 2)},
        "teams": teams,
        "왜": ("대회 일정의 스코어로 센다(중립 단계 제외) · **표시 전용** — λ 는 "
               "득점 실측(`goal_baselines.home_share`)만 쓴다")}


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", required=True)
    ap.add_argument("--seasons", type=int, default=2)
    args = ap.parse_args(argv[1:])
    rows, why = await rows_of(args.comp, seasons=args.seasons)
    print(f"# 🔴🔴 {args.comp} 대회 홈/원정 성적(직전 {args.seasons}시즌)")
    print()
    print(f"- 받은 경기 **{len(rows)}건** — {why}")
    if not rows:
        print("🔴 **미산출** — 받은 경기가 없다")
        return 0
    box = build(args.comp, rows)
    one = box["competition"]
    print(f"- 대회 전체 — 홈 승 **{one['home_win_pct']}%** · 무 "
          f"{one['draw_pct']}% · 원정 승 {one['away_win_pct']}% → "
          f"**win_pct_delta {one['win_pct_delta']:+}%p** · 득점차 "
          f"{one['goals_delta']:+}골 · 표본 {one['home_games']}경기")
    import yaml
    at = datetime.now(timezone.utc).date().isoformat()
    path = (ROOT / "data/comp_record" / args.comp.replace(":", "_")
            / f"{at}.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({**box, "as_of": at, "seasons": why},
                                   allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    print(f"🔴 **판을 적었다** — `{path.relative_to(ROOT)}`(표시 전용) · 팀 "
          f"{len(box['teams'])}개")
    print()
    print("| 팀 | 홈 성적 | 홈 득·실 | 원정 성적 | 원정 득·실 |")
    print("|---|---|---|---|---|")
    for name, said in sorted(box["teams"].items())[:40]:
        h, a = said["home"], said["away"]
        print(f"| {name} | {h['w']}승 {h['d']}무 {h['l']}패({h['n']}) | "
              f"{h['gf']}·{h['ga']} | {a['w']}승 {a['d']}무 {a['l']}패"
              f"({a['n']}) | {a['gf']}·{a['ga']} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
