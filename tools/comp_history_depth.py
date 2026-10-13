"""🔴🔴 **대회 이력의 깊이** — 예측 지시 2026-10-13 23:10 KST.

```
PYTHONPATH=. python tools/comp_history_depth.py --match 6050078 --comp league:ACLE
```

> 대회 이력 칸: 두 팀 직전 2시즌 ACLE 홈/원정 성적 + **"그때 선발 중 오늘 명단
> 남은 수 / 11"** · **감독 같음/다름** · 남은 선발 < 6 또는 감독 바뀜이면
> 🟡 **이력 근거 약함**.

🔴 왜 — *"2시즌 연속 8강"* 같은 이력은 **그 선수들이 남아 있을 때만** 근거다.
🔴 길 — 팀 페이지 일정에서 **그 대회(leagueId)** 경기만 골라 경기 페이지를 읽고
   그때의 **선발 11명·감독**을 받는다. 오늘 명단은 **오늘 경기 페이지**가 준다.
⚠️ 판은 `data/comp_history/<경기 id>.yaml` 이고 **표시 전용**이다(확률 불변).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BACK = 8          # 🔴 팀마다 볼 과거 대회 경기 수(직전 2시즌 안)


async def today_of(net, mid: str) -> tuple[dict, str]:
    """🔴 오늘 경기의 두 팀 — 번호·오늘 명단(선발+벤치+소집)·감독."""
    from app.collect import fotmob as fm
    got = await net.get(fm.match_url(str(mid)))
    j = fm.payload(getattr(got, "text", "") or "")
    if not j:
        return {}, "🔴 오늘 경기 페이지를 못 읽었다"
    ids = fm.side_ids(j)
    out: dict[str, dict] = {}
    for which, tid in zip(("homeTeam", "awayTeam"), ids, strict=False):
        side = fm._side(j, which)
        out[str(side.get("name") or which)] = {
            "id": str(tid or ""),
            "side": "home" if which == "homeTeam" else "away",
            "squad": sorted({*fm._names(side), *fm.squad_names(side),
                             *[str(x) for x in (side.get("subs") or [])
                               if isinstance(x, str)]}),
            "coach": fm._coach(side) or ""}
    return out, (f"오늘 명단 — "
                 + " · ".join(f"{k} {len(v['squad'])}명(감독 {v['coach'] or '⬜'})"
                              for k, v in out.items()))


async def past_of(net, tid: str, *, lid: str, before: str) -> list[dict]:
    """🔴 그 팀의 **그 대회** 과거 경기 — 선발 11명·감독·결과."""
    from app.collect import fotmob as fm
    from app.core import discover as _d
    page = await net.get(fm.team_fixtures_url(tid, "x"))
    j = fm.payload(getattr(page, "text", "") or "") or {}
    box = (((j.get("props") or {}).get("pageProps") or {})
           .get("fallback") or {}).get(f"team-{tid}") or {}
    rows = ((box.get("fixtures") or {}).get("allFixtures") or {}).get(
        "fixtures") or []
    out: list[dict] = []
    for m in reversed(rows):
        if str(((m.get("tournament") or {}).get("leagueId") or "")) != str(lid):
            continue
        said = str((m.get("status") or {}).get("utcTime") or "")
        if not said or said >= str(before) or (
                not (m.get("status") or {}).get("finished")):
            continue
        g = await net.get(fm.match_url(str(m.get("id") or "")))
        j2 = fm.payload(getattr(g, "text", "") or "")
        if not j2:
            continue
        ids2 = fm.side_ids(j2)
        which = ("homeTeam" if str(ids2[0]) == str(tid) else "awayTeam")
        side = fm._side(j2, which)
        names = fm._names(side)
        if not names:
            continue
        out.append({"utc": said, "id": str(m.get("id") or ""),
                    "xi": names, "coach": fm._coach(side) or "",
                    "stage": str((m.get("tournament") or {}).get("stage") or "")})
        if len(out) >= BACK:
            break
    del _d
    return out


async def main(argv: list[str]) -> int:
    import yaml

    from app.core import competition as _cp
    from app.net import Net
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--comp", required=True)
    args = ap.parse_args(argv[1:])
    lid = str(((_cp.row_of(args.comp).get("sources") or {})
               .get("fotmob_ids") or [""])[0])
    net = Net(cache=True, day_cache=True)
    today, why = await today_of(net, args.match)
    print(f"# 🔴🔴 대회 이력의 깊이 — {args.comp}(리그 {lid})")
    print()
    print(f"- {why}")
    if not today:
        return 0
    from app.core import style as _sy
    said_all: dict[str, dict] = {}
    print()
    print("| 팀 | 과거 대회 경기 | 그때 선발 중 **오늘 명단 남은 수/11** | "
          "감독 | 판정 |")
    print("|---|---|---|---|---|")
    for name, one in today.items():
        rows = await past_of(net, one["id"], lid=lid,
                             before="2026-10-13T00:00:00")
        if not rows:
            print(f"| {name} | ⬜ 0경기 | ⬜ | {one['coach'] or '⬜'} | "
                  f"🟡 **이력 없음** |")
            said_all[name] = {"n": 0}
            continue
        said_rows = []
        for r in rows:
            left = sum(1 for p in r["xi"]
                       if _sy._same_player(p, set(one["squad"])))
            same = bool(r["coach"] and one["coach"]
                        and r["coach"] == one["coach"])
            said_rows.append({"utc": r["utc"][:10], "left": left,
                              "coach": r["coach"], "same_coach": same,
                              "stage": r["stage"]})
        avg = sum(x["left"] for x in said_rows) / len(said_rows)
        same_all = all(x["same_coach"] for x in said_rows)
        weak = (avg < 6) or (not same_all)
        said_all[name] = {"n": len(said_rows), "avg_left": round(avg, 1),
                          "same_coach": same_all, "rows": said_rows,
                          "coach_now": one["coach"]}
        print(f"| {name} | {len(said_rows)}경기 | 평균 **{avg:.1f}/11** "
              f"(최근 {said_rows[0]['left']}/11) | "
              + (f"**같다**({one['coach']})" if same_all
                 else f"🔴 **바뀜** — 지금 {one['coach'] or '⬜'} ↔ 그때 "
                      + " · ".join(sorted({x['coach'] or '⬜'
                                           for x in said_rows})))
              + " | " + ("🟡 **이력 근거 약함**" if weak else "✅ 이력 근거 있다")
              + " |")
    path = ROOT / "data/comp_history" / f"{args.match}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"match": args.match, "comp": args.comp,
                                    "teams": said_all,
                                    "왜": ("그때 선발 중 오늘 명단 남은 수 · "
                                           "감독 같음/다름 — **표시 전용**")},
                                   allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    print()
    print(f"🔴 판을 적었다 — `{path.relative_to(ROOT)}`(표시 전용)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
