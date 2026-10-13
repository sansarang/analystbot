"""🔴🔴 **P1 — 국내 리그 Elo(등록 리그 밖 팀 포함)**(수정 지시 2026-10-13 밤 P1).

```
PYTHONPATH=. python tools/fit_league_elo.py --comp league:ACLE --seasons 2
```

> 등록 리그 밖 팀도 국내 리그 과거 경기를 받는다(fotmob 팀 페이지 · 리그 id
> **자동 등록** · kind=domestic_league). 꽁안(V리그)·부리람(T1)·조호르·상하이·
> 베이징·이스트 벵골·알쇼르타 리그 우선.

🔴 **길** — 대회 일정 → 참가 팀 → **팀 페이지의 순위표 리그 id**(그 팀의 국내
   리그) → 그 리그의 **일정 한 장**(시즌당) → 스코어로 **Elo 를 굴린다**.
   ⚠️ 경기 페이지를 받지 않는다(일정의 `scoreStr` 로 충분하다 · 시즌당 1회 통신).
🔴 판은 `data/league_elo_auto/<리그 열쇠>.yaml` 이고 **팀별 Elo·경기 수·시즌**을
   적는다. 오프셋 적합(`tools/fit_offsets.py`)이 이 판을 읽는다.
🔴 Elo 는 **K=20 · 시작 1500 · 홈 이점 0**(리그 안에서 상대적인 수만 쓴다) —
   리그 **사이** 비교는 오프셋이 한다(P1 둘째 조항).
⚠️ 리그를 못 가린 팀은 **이름으로 남긴다**(지어내지 않는다 · #3).
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

OUT = ROOT / "data/league_elo_auto"
K_ELO = 20.0
_SCORE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


async def comp_teams(net, comp: str) -> tuple[dict, str]:
    """🔴 그 대회 참가 팀 → `{팀 이름: 팀 번호}`(일정 + 경기 페이지 번호)."""
    from app.collect import fotmob as fm
    from app.core import competition as _cp
    ids = [str(x) for x in ((_cp.row_of(comp).get("sources") or {})
                            .get("fotmob_ids") or [])]
    if not ids:
        return {}, f"🔴 `{comp}` fotmob id 가 표에 없다"
    # 🔴 **팀 번호는 일정 줄에 있다**(`home.id`) — 색인을 안 쓴다(색인에 없는
    #    리그가 있다 · 실측: V리그). ⚠️ `league_matches` 는 그 칸을 버리므로
    #    원본(`allMatches`)을 직접 읽는다.
    page = await net.get(fm.league_matches_url(ids[0], "x"))
    j = fm.payload(getattr(page, "text", "") or "") or {}
    said = fm.league_seasons(j)
    out: dict[str, str] = {}
    n = 0
    for i, season in enumerate(said[:2]):
        if i == 0:
            pp = ((j.get("props") or {}).get("pageProps") or {})
        else:
            more = await net.get(fm.league_matches_url(ids[0], "x")
                                 + f"?season={season}")
            pp = (((fm.payload(getattr(more, "text", "") or "") or {})
                   .get("props") or {}).get("pageProps") or {})
        for m in (((pp.get("fixtures") or {}).get("allMatches")) or []):
            n += 1
            for side in ("home", "away"):
                one = dict(m.get(side) or {})
                name = str(one.get("name") or "")
                if name:
                    out.setdefault(name, str(one.get("id") or ""))
    return out, f"대회 일정 {n}경기 · 팀 {len(out)}개(번호 포함)"


async def domestic_of(net, name: str, tid: str) -> tuple[str, str, str]:
    """🔴 그 팀의 **국내 리그**(열쇠, 이름, 사유) — 팀 페이지 순위표에서."""
    from app.collect import fotmob as fm
    from app.core import competition as _cp
    from app.core import discover as _d
    if not tid:
        idx = await fm.team_index(net)
        hits = _d._slug_hit(idx, name)
        if not hits:
            return "", "", f"⬜ `{name}` 색인에 없다(번호를 못 찾았다)"
        tid = hits[0][0]
    got = await net.get(fm.team_fixtures_url(tid, "x"))
    j = fm.payload(getattr(got, "text", "") or "") or {}
    box = (((j.get("props") or {}).get("pageProps") or {})
           .get("fallback") or {}).get(f"team-{tid}") or {}
    # 🔴🔴 **먼저 `details.primaryLeagueId`** — 그 팀의 **주 리그**다(받아서
    #    확인했다 2026-10-13). ⚠️ 순위표(`table`)는 대륙 대회가 섞이고, 시즌 전에는
    #    아예 비어 있다(실측: 사우디·호주 팀이 그래서 ⬜ 였다).
    det = dict(box.get("details") or {})
    said_primary = det.get("primaryLeagueId")
    if said_primary is not None:
        key, _w = _cp.key_of(competition="", league_id=said_primary)
        if not key:
            # 🔴🔴 **자동 등록**(P1) — 손 표에 없는 리그를 여기서 등록한다.
            #    ⚠️ 필수 칸(나라·팀 목록·언어)이 없으면 등록 실패고 그 사유를 적는다.
            key, said_why = await register(net, said_primary,
                                           ccode=str(det.get("country") or ""))
            if not key:
                return "", "", f"⬜ `{name}` 리그 자동 등록 실패 — {said_why}"
        if key and _cp.kind_require(key)[0] in ("domestic_league", ""):
            return (key, f"primaryLeagueId({said_primary})",
                    f"팀 페이지 `details.primaryLeagueId` · 번호 {tid}")
    rows = box.get("table")
    rows = rows if isinstance(rows, list) else [rows]
    for one in rows:
        data = (one or {}).get("data") if isinstance(one, dict) else None
        for r in ([data] if isinstance(data, dict) else []) + \
                 list((data or {}).get("tables") or []
                      if isinstance(data, dict) else []):
            if not isinstance(r, dict):
                continue
            lid, lname = r.get("leagueId"), str(r.get("leagueName") or "")
            if lid is None and not lname:
                continue
            # 🔴 **자동 등록**이 여기서 일어난다(`key_of` 가 표에 없으면 만든다)
            key, _why = _cp.key_of(competition=lname, league_id=lid)
            # 🔴 **대륙 대회는 국내 리그가 아니다** — 순위표 목록에 ACL 이 섞인다
            #    (실측: 그래서 `league:ACLE` 가 "국내 리그"로 잡혔다).
            if key and _cp.kind_require(key)[0] == "club_continental":
                continue
            if key:
                return key, f"{lname}({lid})", f"팀 페이지 순위표 · 번호 {tid}"
    return "", "", f"⬜ `{name}`(번호 {tid}) 팀 페이지에 순위표 리그가 없다"


async def register(net, lid: object, *, ccode: str) -> tuple[str, str]:
    """🔴🔴 **리그 자동 등록**(P1) — `(열쇠, 사유)`. 유형은 `domestic_league` 다.

    🔴 팀 목록은 그 리그 **일정 한 장**에서 온다(순위표가 없는 리그도 있다).
    ⚠️ 나라 코드가 없으면 등록하지 않는다(언어를 못 정한다 · §1 필수 칸).
    """
    from app.collect import fotmob as fm
    from app.core import autoleague as _al
    said_id = str(lid or "")
    if not said_id or not ccode:
        return "", f"리그 번호({said_id or '없음'})·나라({ccode or '없음'})"
    page = await net.get(fm.league_matches_url(said_id, "x"))
    j = fm.payload(getattr(page, "text", "") or "") or {}
    pp = ((j.get("props") or {}).get("pageProps") or {})
    rows = ((pp.get("fixtures") or {}).get("allMatches")) or []
    teams = sorted({str((m.get(s) or {}).get("name") or "")
                    for m in rows for s in ("home", "away")} - {""})
    name = str(((pp.get("details") or {}).get("name"))
               or (pp.get("leagueName") or ""))
    if not teams:
        return "", f"일정에서 팀 목록을 못 만들었다(리그 {said_id})"
    box, why = _al.build(
        competition_key=f"league:fotmob{said_id}",
        meta={"league_id": said_id, "ccode": ccode, "name": name,
              "url": fm.league_matches_url(said_id, "x"),
              # 🔴 **유형을 적는다**(P1) — CP1 이 그것을 본다
              "kind": "domestic_league"},
        teams=teams, baseline={"why": "⬜ 기준 모형 없음(자동 등록)"},
        teams_from=f"fotmob:{said_id} 일정")
    if not box:
        return "", why
    path, why2 = _al.save(box)
    if path is None:
        return "", why2
    return f"league:fotmob{said_id}", f"{why} · {why2}"


async def elo_of(net, key: str, lid: str, *, seasons: int) -> tuple[dict, str]:
    """🔴 그 리그의 팀별 Elo — **일정 한 장**(시즌당)의 스코어로 굴린다."""
    from app.collect import fotmob as fm
    page = await net.get(fm.league_matches_url(lid, "x"))
    j = fm.payload(getattr(page, "text", "") or "") or {}
    said = fm.league_seasons(j)
    rows: list[dict] = []
    box: list[str] = []
    for i, season in enumerate(said[:max(1, int(seasons))]):
        if i == 0:
            pp = ((j.get("props") or {}).get("pageProps") or {})
        else:
            more = await net.get(fm.league_matches_url(lid, "x")
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
            rows.append({"home": str((m.get("home") or {}).get("name") or ""),
                         "away": str((m.get("away") or {}).get("name") or ""),
                         "hg": int(got.group(1)), "ag": int(got.group(2)),
                         "utc": str(st.get("utcTime") or "")})
            add += 1
        box.append(f"{season} {add}경기")
    elo: dict[str, float] = {}
    for r in sorted(rows, key=lambda x: str(x.get("utc"))):
        h, a = r["home"], r["away"]
        dr = elo.get(h, 1500.0) - elo.get(a, 1500.0)
        exp = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        said_got = (1.0 if r["hg"] > r["ag"]
                    else (0.5 if r["hg"] == r["ag"] else 0.0))
        elo[h] = elo.get(h, 1500.0) + K_ELO * (said_got - exp)
        elo[a] = elo.get(a, 1500.0) - K_ELO * (said_got - exp)
    return ({"league": key, "fotmob_id": str(lid), "n": len(rows),
             "seasons": " · ".join(box), "kind": "domestic_league",
             "teams": {k: round(v, 1) for k, v in sorted(elo.items())},
             "왜": ("일정의 스코어로 굴린 Elo(K=20 · 시작 1500 · 홈 이점 0) — "
                    "리그 **안**에서만 비교한다(리그 사이는 오프셋이 한다)")},
            f"{len(rows)}경기 · 팀 {len(elo)}개 · " + " · ".join(box))


async def main(argv: list[str]) -> int:
    import yaml

    from app.net import Net
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", action="append", required=True)
    ap.add_argument("--seasons", type=int, default=2)
    args = ap.parse_args(argv[1:])
    net = Net(cache=True, day_cache=True)
    print("# 🔴🔴 P1 국내 리그 Elo(등록 리그 밖 팀 포함)")
    print()
    teams: dict[str, str] = {}
    for comp in args.comp:
        got, why = await comp_teams(net, comp)
        print(f"- `{comp}` — {why}")
        teams.update(got)
    leagues: dict[str, str] = {}
    gone: list[str] = []
    for name, tid in sorted(teams.items()):
        key, said, why = await domestic_of(net, name, tid)
        if not key:
            gone.append(why)
            continue
        leagues.setdefault(key, said)
    print(f"- 국내 리그 **{len(leagues)}개** — "
          + " · ".join(f"`{k}`({v})" for k, v in sorted(leagues.items())))
    if gone:
        print(f"- ⬜ 리그를 못 가린 팀 **{len(gone)}개** — " + " · ".join(gone[:6]))
    print()
    print("| 리그 | fotmob id | 경기 | 팀 | 시즌 |")
    print("|---|---|---|---|---|")
    OUT.mkdir(parents=True, exist_ok=True)
    for key, said in sorted(leagues.items()):
        lid = said.split("(")[-1].rstrip(")")
        box, why = await elo_of(net, key, lid, seasons=args.seasons)
        if not box["teams"]:
            print(f"| `{key}` | {lid} | 0 | 0 | 🔴 일정에서 스코어를 못 읽었다 |")
            continue
        (OUT / f"{key.replace(':', '_')}.yaml").write_text(
            yaml.safe_dump(box, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        print(f"| `{key}` | {lid} | {box['n']} | {len(box['teams'])} | "
              f"{box['seasons']} |")
    print()
    print(f"🔴 판을 적었다 — `{OUT.relative_to(ROOT)}/*.yaml`(팀별 Elo) · "
          f"오프셋 적합(`tools/fit_offsets.py`)이 이것을 읽는다")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
