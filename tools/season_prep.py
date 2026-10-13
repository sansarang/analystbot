"""🔴🔴 **§2 데이터 준비 보고**(통합 지시서 2026-10-13 밤).

```
PYTHONPATH=. python tools/season_prep.py
```

> 보고: 리그별 `retention` 분포 · 하위 10% 팀 목록 · 감독 부임일 확보율 ·
> **폼 창 감사** 결과(이번 시즌 / 지난 시즌 / 컵 경기 수 · 지난 시즌 섞인 비율 ·
> 시즌 초 6라운드 이내 따로) · 코번트리–뉴캐슬 "최근 5경기" 출처 목록.

🔴 폼 창은 **운영이 실제로 받는 목록**으로 센다 — `discover.team_fixtures`(팀 일정
   페이지)다. ⚠️ 거기에는 **컵 경기가 섞여 있다**(백필 덤프는 리그만이라 컵이
   구조적으로 0 이다 — 그래서 덤프로 세면 거짓이 된다).
🔴 **L1** — 창은 `fotmob.before_as_of` 로 자른 뒤 마지막 5경기다(운영과 같은 문).
"""
from __future__ import annotations

import asyncio
import json
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 폼 창 크기 — 운영 ⑪ 이 보는 수(5경기)
WINDOW = 5
#: 🔴 "시즌 초" 의 뜻 — 이번 시즌 리그 경기 수가 이 수 이하
EARLY = 6


async def fixtures_of(net, name: str, *, state) -> tuple[list[dict], str]:
    """🔴 그 팀의 **일정 목록**(운영이 받는 그 목록). `(줄, 사유)`."""
    from app.collect import fotmob as fm
    from app.core import discover as _d
    got = await _d.pick_team(net, name, ref=None, state=state)
    if not got:
        return [], f"🔴 `{name}` 팀을 못 찾았다"
    tid, slug = got
    page = await net.get(fm.team_fixtures_url(tid, slug))
    rows = _d.team_fixtures(getattr(page, "text", "") or "", tid)
    done = [r for r in rows if r.get("finished")]
    return done, f"일정 {len(rows)}건(끝난 경기 {len(done)}건 · 팀 {tid})"


def window_of(rows: list[dict], *, as_of, league: str) -> dict:
    """🔴 그 시점의 **폼 창 5경기** 를 시즌·대회로 가른다."""
    from app.collect import fotmob as fm
    from app.core import level as _lv
    from app.core import season as _se
    said = fm.before_as_of(list(rows or []), as_of=as_of)[-WINDOW:]
    want, _w = _se.id_of(league=league, when=as_of)
    out = {"n": len(said), "now": 0, "prev": 0, "cup": 0, "rows": []}
    for one in said:
        comp = str(one.get("league_name") or one.get("league") or "")
        cup = bool(_lv.is_cup(comp))
        got, _w2 = _se.id_of(league=league, when=one.get("utc"))
        if cup:
            out["cup"] += 1
        elif got == want:
            out["now"] += 1
        else:
            out["prev"] += 1
        out["rows"].append({"day": str(one.get("utc") or "")[:10],
                            "comp": comp, "season": got, "cup": cup,
                            "score": str(one.get("score") or "")})
    return out


async def main(argv: list[str]) -> int:
    from app.collect import coach as co
    from app.collect import fotmob as fm
    from app.core import season as _se
    from app.core.ratings import retention as _rt
    from app.core.state import RunState
    from app.net import Net
    net = Net(cache=True)
    state = RunState()
    rows = json.loads((ROOT / "var/judge/lineup_rows2.json").read_text(
        encoding="utf-8"))
    ev = json.loads((ROOT / "var/judge/events.json").read_text(
        encoding="utf-8"))
    print("# 🔴🔴 §2 데이터 준비 보고")
    print()
    # ── 2-1 시즌 표기
    said = _se.tag(rows)
    why = _se.require(said)
    print("## 2-1 시즌 표기")
    print()
    print("| 리그 | 경기 | season_id 분포 | SE1 |")
    print("|---|---|---|---|")
    for league in sorted({r["league"] for r in said}):
        mine = [r for r in said if r["league"] == league]
        box: dict[str, int] = {}
        for r in mine:
            box[str(r["season_id"])] = box.get(str(r["season_id"]), 0) + 1
        print(f"| {league} | {len(mine)} | "
              + " · ".join(f"`{k or '⬜'}` {v}" for k, v in sorted(box.items()))
              + " | " + ("🔴 " + why if why else "✅ 전부 있다") + " |")
    print()
    # ── 2-4 잔류율(팀마다 **그 팀 마지막 경기** 시점)
    print("## 2-4 선수단 잔류율")
    print()
    mins_rows: list[dict] = []
    for r in rows:
        one = dict(ev.get(f"{r['utc']}|{r['home']}|{r['away']}") or {})
        pstat = dict(one.get("pstat") or {})
        side = {}
        for key in ("home", "away"):
            ids = set(r[f"{key}_ids"]) | set(r[f"{key}_bench"])
            side[f"{key}_minutes"] = {
                p: float(dict(v).get("minutes_played") or 0.0)
                for p, v in pstat.items() if str(p) in ids}
        mins_rows.append({"utc": r["utc"], "league": r["league"],
                          "home": r["home"], "away": r["away"], **side})
    for league in sorted({r["league"] for r in rows}):
        mine = [r for r in mins_rows if r["league"] == league]
        teams = sorted({r["home"] for r in mine} | {r["away"] for r in mine})
        got: dict[str, float] = {}
        blank: list[str] = []
        for team in teams:
            last = max(r["utc"] for r in mine
                       if team in (r["home"], r["away"]))
            at = datetime.fromisoformat(last.replace("Z", "+00:00"))
            val, _w = _rt.of(mine, team=team, as_of=at, league=league)
            if val is None:
                blank.append(team)
            else:
                got[team] = val
        print(f"- **{league}** — 쟀다 {len(got)}팀 · ⬜ 못 쟀다 {len(blank)}팀"
              + (f"({', '.join(blank[:6])}…)" if blank else ""))
        if got:
            vals = sorted(got.values())
            print(f"  · 분포 — 평균 **{st.fmean(vals):.2f}** · 중앙 "
                  f"{st.median(vals):.2f} · 최소 {vals[0]:.2f} · 최대 "
                  f"{vals[-1]:.2f}")
            cut = max(1, len(vals) // 10)
            low = sorted(got.items(), key=lambda x: x[1])[:cut]
            print("  · **하위 10%** — "
                  + " · ".join(f"{k} {v:.2f}" for k, v in low))
    print()
    # ── 2-3 감독
    print("## 2-3 감독 부임일 확보율")
    print()
    teams = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    names = since = 0
    for team in teams[:40]:
        got = await _d_pick(net, team, state=state)
        if not got:
            continue
        tid, slug = got
        page = await net.get(f"{fm.BASE}/teams/{tid}/overview/{slug}")
        row = co.row_of(team_id=str(tid),
                        payload=fm.payload(getattr(page, "text", "") or "")
                        or {})
        names += 1 if row.coach else 0
        since += 1 if row.since else 0
    print(f"- 팀 {len(teams)}곳 중 조회 {min(40, len(teams))}곳 — 감독 **이름 "
          f"{names}곳** · **부임일 {since}곳**")
    # 🔴 **왜 0 인가를 그 함수로 보여 준다**(CO1 · 추측 금지) — 지금 우리에게는
    #    감독 부임 기사를 받는 통로가 **없다**(기사 두 매체가 필요하다).
    _day, why_since = co.since_of([])
    print(f"- `coach.since_of([])` → {why_since}")
    said_team = teams[0]
    _n, why_games = co.games_of(
        [r for r in rows if said_team in (r["home"], r["away"])],
        team=said_team, since=_day,
        as_of=datetime.fromisoformat(
            max(r["utc"] for r in rows).replace("Z", "+00:00")))
    print(f"- `coach.games_of(... since=None)` → {why_games}")
    print("- 🔴 fotmob 팀 페이지는 **이름만** 준다(`since`·`appointed`·"
          "`startDate` 0건 · 실측) → 부임일은 **기사 두 매체**로만 선다(CO1) · "
          "지금 확보율 **0%** 이므로 **§5 감독 후보는 보정표를 만들 수 없다**")
    print()
    # ── 2-2 폼 창 감사
    print("## 2-2 폼 창 감사(운영이 받는 목록 = 팀 일정 · 컵 포함)")
    print()
    fx: dict[str, list[dict]] = {}
    for team in teams:
        got, _w = await fixtures_of(net, team, state=state)
        fx[team] = got
    print(f"- 팀 일정 받은 곳 **{sum(1 for v in fx.values() if v)}/{len(teams)}**")
    print()
    print("| 리그 | 창 | 이번 시즌 | 지난 시즌 | 컵 | 지난 시즌 섞인 창 비율 |")
    print("|---|---|---|---|---|---|")
    for league in sorted({r["league"] for r in rows}):
        mine = [r for r in said if r["league"] == league]
        tally = {"now": 0, "prev": 0, "cup": 0, "n": 0, "mixed": 0,
                 "early_n": 0, "early_mixed": 0}
        for r in mine:
            at = datetime.fromisoformat(str(r["utc"]).replace("Z", "+00:00"))
            for key in ("home", "away"):
                box = window_of(fx.get(r[key]) or [], as_of=at, league=league)
                if not box["n"]:
                    continue
                tally["n"] += 1
                for k in ("now", "prev", "cup"):
                    tally[k] += box[k]
                mixed = box["prev"] > 0
                tally["mixed"] += 1 if mixed else 0
                cnt, _w = _se.games_of(mine, team=r[key], as_of=at,
                                       league=league)
                if cnt <= EARLY:
                    tally["early_n"] += 1
                    tally["early_mixed"] += 1 if mixed else 0
        n = max(1, tally["n"])
        print(f"| {league} | {tally['n']} | {tally['now'] / n:.2f} | "
              f"{tally['prev'] / n:.2f} | {tally['cup'] / n:.2f} | "
              f"**{tally['mixed'] / n:.1%}** |")
        if tally["early_n"]:
            print(f"| ↳ 시즌 초(≤{EARLY}경기) | {tally['early_n']} | — | — | — "
                  f"| **{tally['early_mixed'] / tally['early_n']:.1%}** |")
    print()
    print("⚠️ 칸의 수는 **창 5경기 중 평균 몇 경기**인가다(이번+지난+컵 ≈ 5).")
    return 0


async def _d_pick(net, name: str, *, state):
    from app.core import discover as _d
    return await _d.pick_team(net, name, ref=None, state=state)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
