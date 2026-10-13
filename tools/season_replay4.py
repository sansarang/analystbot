"""🔴🔴 **§12 재현(참고 · 판정 무관)**(통합 지시서 2026-10-13 밤).

```
PYTHONPATH=. python tools/season_replay4.py
```

> 코번트리–뉴캐슬(10-12) · 광주–울산 · 가와사키–나고야 · 코모–로마: **as-of 킥오프**
> — season 문맥 값(이번 시즌 경기 수 · retention · 감독 경기 수 · trend) · B ·
> 채택 판 · 혼합 확률 · 보호 줄. **결과 줄 맨 끝.**
> 🔴 이 경기들에 맞추려고 계수·문턱을 고치지 않는다.

🔴 **채택 판은 없다** — §3~§6·§8 이 전부 기준 유지였다. 그래서 *"채택 판"* 칸은
   **B 와 같은 수**이고, *"혼합"* 은 **그림자**(E1)다.
⚠️ 백필 표본이 없는 리그(PL·세리에A)는 **계수 판이 없어** B·혼합을 **못 만든다** —
   그 칸은 ⬜ 이고 사유를 적는다(지어내지 않는다).
"""
from __future__ import annotations

import asyncio
import json
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

CASES = (
    {"name": "코번트리 시티 vs 뉴캐슬", "home": "Coventry City",
     "away": "Newcastle United", "league": ""},
    {"name": "광주 vs 울산", "home": "Gwangju FC", "away": "Ulsan HD FC",
     "league": "league:KL1"},
    {"name": "가와사키 vs 나고야", "home": "Kawasaki Frontale",
     "away": "Nagoya Grampus", "league": "league:J1"},
    {"name": "코모 vs AS 로마", "home": "Como", "away": "Roma",
     "league": ""},
)


async def fixtures(net, name: str) -> tuple[list[dict], str, str]:
    """🔴 팀 일정(운영이 받는 그 목록) + 팀 id."""
    from app.collect import fotmob as fm
    from app.core import discover as _d
    from app.core.state import RunState
    got = await _d.pick_team(net, name, ref=None, state=RunState())
    if not got:
        return [], "", f"🔴 `{name}` 팀을 못 찾았다"
    tid, slug = got
    page = await net.get(fm.team_fixtures_url(tid, slug))
    rows = _d.team_fixtures(getattr(page, "text", "") or "", tid)
    return rows, str(tid), f"일정 {len(rows)}건"


def trend_back(back: list[dict], *, team: str, as_of, league: str
               ) -> tuple[float | None, str]:
    """🔴 §6 과 **같은 식** — 최근 2경기 득실차 − 그 앞 · 수축 `n/(n+2)`.

    🔴 스코어는 **백필 목록**에서 온다(팀 일정 줄에는 스코어가 없다 · 실측).
    ⚠️ 백필 표본 밖 리그(PL·세리에A)는 **못 쟨다** — ⬜ 이고 사유를 적는다.
    """
    from app.core import season as _se
    if not league:
        return None, "⬜ 백필 표본 밖 리그다(스코어 목록이 없다)"
    want, _w = _se.id_of(league=league, when=as_of)
    gd: list[float] = []
    for r in sorted(back, key=lambda x: str(x.get("day"))):
        if str(r.get("league")) != league:
            continue
        day = str(r.get("day") or "")
        if not day or day >= as_of.date().isoformat():
            continue
        at0 = datetime.fromisoformat(f"{day}T12:00:00+00:00")
        if _se.id_of(league=league, when=at0)[0] != want:
            continue
        if team == str(r.get("home")):
            gd.append(float(int(r["hg"]) - int(r["ag"])))
        elif team == str(r.get("away")):
            gd.append(float(int(r["ag"]) - int(r["hg"])))
    if len(gd) < 3:
        return None, f"⬜ 이번 시즌 {len(gd)}경기(3건 미만)"
    late = st.fmean(gd[-2:])
    early = st.fmean(gd[:-2])
    n = len(gd) - 2
    return (late - early) * (n / (n + 2.0)), (
        f"최근 2경기 {late:+.2f} − 그 앞 {n}경기 {early:+.2f}")


async def main(argv: list[str]) -> int:
    from app.collect import coach as co
    from app.collect import fotmob as fm
    from app.core import ensemble as en
    from app.core import season as se
    from app.core.ratings import retention as rt
    from app.net import Net
    net = Net(cache=True)
    print("# 🔴🔴 §12 재현(참고 · 판정 무관)")
    print()
    print("🔴 **채택 판이 없다**(§3~§6·§8 전부 기준 유지) → *채택 판* 칸은 B 와"
          " 같은 수이고 *혼합* 은 **그림자(E1)** 다.")
    print()
    back = json.loads((ROOT / "var/judge/replay_big2.json").read_text(
        encoding="utf-8"))
    rows2 = json.loads((ROOT / "var/judge/lineup_rows2.json").read_text(
        encoding="utf-8"))
    ev = json.loads((ROOT / "var/judge/events.json").read_text(
        encoding="utf-8"))
    mins: list[dict] = []
    for r in rows2:
        one = dict(ev.get(f"{r['utc']}|{r['home']}|{r['away']}") or {})
        pstat = dict(one.get("pstat") or {})
        side = {}
        for key in ("home", "away"):
            ids = set(r[f"{key}_ids"]) | set(r[f"{key}_bench"])
            side[f"{key}_minutes"] = {
                p: float(dict(v).get("minutes_played") or 0.0)
                for p, v in pstat.items() if str(p) in ids}
        mins.append({"utc": r["utc"], "league": r["league"],
                     "home": r["home"], "away": r["away"], **side})
    for case in CASES:
        print(f"## {case['name']}")
        print()
        rows_h, tid_h, why_h = await fixtures(net, case["home"])
        rows_a, tid_a, why_a = await fixtures(net, case["away"])
        # 🔴 그 경기를 **일정에서** 찾는다(킥오프 시각을 거기서 받는다)
        from app.core import discover as _dd
        said = [r for r in rows_h
                if _dd.same_any(str(r.get("away") or ""),
                                _dd.aliases_of(case["away"]), loose=True)
                or _dd.same_any(str(r.get("home") or ""),
                                _dd.aliases_of(case["away"]), loose=True)]
        if not said:
            print(f"🔴 **그 경기를 일정에서 못 찾았다**({why_h} · {why_a}) — "
                  f"이 칸은 비운다")
            print()
            continue
        # 🔴 **끝난 경기**를 고른다(일정에는 다음 시즌 경기도 있다 — 실측:
        #    `said[-1]` 이 2027년 경기를 집었다)
        done = [r for r in said if r.get("finished")]
        one = done[-1] if done else said[-1]
        at = datetime.fromisoformat(str(one.get("utc")).replace("Z", "+00:00"))
        league = case["league"] or ""
        season, why_season = se.id_of(league=league, when=at) if league \
            else ("", "🔴 리그 열쇠가 없다(백필 표본 밖)")
        print(f"- 킥오프 **{at.isoformat()}** · 리그 `{league or '⬜'}` · 시즌 "
              f"`{season or '⬜'}`({why_season})")
        for side, name, rows_t, tid in (("home", case["home"], rows_h, tid_h),
                                        ("away", case["away"], rows_a, tid_a)):
            # 🔴 일정 목록은 **이번 시즌만** 담는다(실측) → 끝난 **리그** 경기를
            #    그대로 센다. ⚠️ 컵은 `level.is_cup` 으로 뺀다.
            from app.collect import fotmob as fm0
            from app.core import level as _lv
            n_fix = sum(1 for x in fm0.before_as_of(
                [y for y in rows_t if y.get("finished")], as_of=at)
                if not _lv.is_cup(str(x.get("league_name") or "")))
            n_season = n_fix
            if league and season:
                got_rows = [r for r in back
                            if str(r.get("league")) == league
                            and str(r.get("day")) < at.date().isoformat()]
                n_season = sum(
                    1 for r in got_rows
                    if se.id_of(league=league,
                                when=datetime.fromisoformat(
                                    f"{r['day']}T12:00:00+00:00"))[0] == season
                    and name in (str(r["home"]), str(r["away"])))
            ret, why_ret = (rt.of(mins, team=name, as_of=at, league=league)
                            if league else (None, "⬜ 리그 열쇠가 없다"))
            page = await net.get(f"{fm.BASE}/teams/{tid}/overview/x")
            row = co.row_of(team_id=tid,
                            payload=fm.payload(getattr(page, "text", "") or "")
                            or {})
            n_coach, why_coach = co.games_of(
                [{"utc": str(x.get("utc")), "home": name, "away": ""}
                 for x in rows_t if x.get("finished")],
                team=name, since=row.since, as_of=at)
            tr, why_tr = trend_back(back, team=name, as_of=at, league=league)
            print(f"- **{name}** — 이번 시즌 리그 **{n_season}경기**"
                  f"(일정에서 {n_fix}) · 잔류율 "
                  + (f"**{ret:.2f}**" if ret is not None else "⬜")
                  + f"({why_ret[:90]}) · 감독 **{row.coach or '⬜'}**"
                    f"(경기 수 {n_coach if n_coach is not None else '⬜'} — "
                    f"{why_coach[:36]}) · trend "
                  + (f"**{tr:+.2f}**({why_tr})" if tr is not None
                     else f"⬜({why_tr})"))
        # 🔴 B·그림자 — 백필에 그 경기가 있으면 그 수를 쓴다(다시 안 센다)
        hit_row = [r for r in back
                   if str(r.get("day")) == at.date().isoformat()
                   and str(r.get("home")) == case["home"]]
        if hit_row and hit_row[0].get("ours"):
            r0 = hit_row[0]
            b = [float(x) for x in r0["ours"]]
            floor = [float(x) for x in (r0.get("floor") or [])] or None
            e1, why_e1 = (en.mix({"M1": b, "M3": floor},
                                 {"M1": 0.5, "M3": 0.5})
                          if floor else ([], "⬜ 바닥이 없다"))
            print(f"- **B(M1)** 홈 {b[0]:.0%} · 무 {b[1]:.0%} · 원정 {b[2]:.0%}"
                  f" · **채택 판 = B**(채택 없음)")
            if e1:
                print(f"- **혼합 그림자 E1**(M1 0.5 + 바닥 0.5) 홈 {e1[0]:.0%} · "
                      f"무 {e1[1]:.0%} · 원정 {e1[2]:.0%} — 🔴 확률은 **B** 다")
            fav_home = b[0] >= b[2]
            no_win = 1.0 - (b[0] if fav_home else b[2])
            print(f"- **보호 줄** — 강팀 미승 확률 {no_win:.0%}"
                  + (" ≥ 50% → 약팀 **+1.5 / 더블찬스**를 본다"
                     if no_win >= 0.50 else " < 50% → 보호 줄 없음"))
        else:
            print("- ⬜ **B·혼합 미산출** — 이 경기는 백필 표본(J1·K1 704경기) "
                  "밖이다(리그 계수 판이 없다 · 지어내지 않는다)")
        # 🔴 **결과는 경기 페이지에서** 받는다(일정 줄에 스코어가 없다)
        said_res = "⬜"
        page_url = str(one.get("page") or "")
        if page_url:
            from app.core import backfill as bf0
            got_p = await net.get(fm.BASE + page_url if page_url.startswith("/")
                                  else page_url)
            j0 = fm.payload(getattr(got_p, "text", "") or "")
            sc = bf0.score_of(j0) if j0 else None
            said_res = f"**{sc[0]}-{sc[1]}**" if sc else "⬜(스코어 못 읽었다)"
        print(f"- **결과** — {said_res}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
