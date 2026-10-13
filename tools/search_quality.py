"""🔴🔴 **§6-7 검색 품질 기준선**(지시서 2026-10-13 밤 셋째 · **고치기 전 숫자**).

```
PYTHONPATH=. python tools/search_quality.py            # 저장된 카드 전부
PYTHONPATH=. python tools/search_quality.py --limit 10
```

> 정답: 경기 후 공식 기록으로 **"그 경기에 실제로 빠진 주전"**(usual_xi 중 미출전).
> 측정: 경기 전 카드가 그 결장을 **미리 잡았나**(재현율) · 잡은 결장 중 실제로
> 빠졌나(정밀도) · **몇 시간 전에** 잡았나.
> 계약 **SQ1**: 정답 판정에 **경기 후 정보**를 쓰는 건 **측정용만** — 카드·확률
> 경로에 닿으면 실패.

🔴 카드는 **글자에서** 읽는다(다시 돌리지 않는다 — 카드가 그때의 봇이다).
🔴 이름 비교는 `style._same_player` 하나다(성 기반 · 사본 금지).
🔴 평소 XI 는 그 경기 **앞** 경기의 선발로 센다(L1 · `before_as_of`).
"""
from __future__ import annotations

import asyncio
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

HEAD = re.compile(r"^🏟 \*\*(.+?) vs (.+?)\*\* · (.+?) · (\d\d)-(\d\d) ")
#: 🔴 `    Jeremy Ebobisse(?) — 부상 · …`
CLAIM = re.compile(r"^ {4}([^—(]{2,40})(?:\(\?\))? — ")
TEAM = re.compile(r"^- \*\*(.+?)\*\*\s*$")
#: 🔴 평소 XI 를 세는 경기 수(운영 `lineup_strength.USUAL_N` 과 같은 수)
BACK = 5


def cards(limit: int = 0) -> list[dict]:
    """🔴 저장된 카드 → `{file, home, away, league, day, claims}`."""
    out: list[dict] = []
    for path in sorted((ROOT / "var/accept").glob("*card*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        head = HEAD.search(text)
        if not head:
            continue
        box: dict[str, list[str]] = {}
        said = text.split("**2b. 결장**", 1)
        if len(said) == 2:
            team = ""
            for line in said[1].splitlines():
                if line.startswith("**") or line.startswith("🆕"):
                    break
                got = TEAM.match(line)
                if got:
                    team = got.group(1).strip()
                    box.setdefault(team, [])
                    continue
                one = CLAIM.match(line)
                if one and team:
                    box[team].append(one.group(1).strip())
        out.append({"file": path.name, "home": head.group(1).strip(),
                    "away": head.group(2).strip(),
                    "league": head.group(3).strip(),
                    "day": f"2026-{head.group(4)}-{head.group(5)}",
                    "claims": box})
        if limit and len(out) >= limit:
            break
    return out


async def truth(net, one: dict, *, state) -> tuple[dict, str]:
    """🔴🔴 **정답** — 그 경기에 실제로 빠진 주전(`usual_xi` − 오늘 XI).

    ⚠️ **SQ1** — 이 함수는 경기 **뒤** 정보를 본다(측정용). 카드·확률 경로는
       이것을 부르지 않는다(계약이 센다).
    """
    from app.collect import fotmob as fm
    from app.core import discover as _d
    out: dict[str, dict] = {}
    for side in ("home", "away"):
        name = str(one[side])
        got = await _d.pick_team(net, name, ref=None, state=state)
        if not got:
            return {}, f"🔴 `{name}` 팀을 못 찾았다"
        tid, slug = got
        page = await net.get(fm.team_fixtures_url(tid, slug))
        rows = _d.team_fixtures(getattr(page, "text", "") or "", tid)
        want = [r for r in rows
                if str(r.get("utc") or "")[:10] == str(one["day"])]
        if not want:
            return {}, (f"🔴 `{name}` 일정에 {one['day']} 경기가 없다"
                        f"(받은 일정 {len(rows)}건)")
        at = datetime.fromisoformat(str(want[0]["utc"]).replace("Z", "+00:00"))
        # ── 오늘 XI
        url = str(want[0].get("page") or "")
        if not url:
            return {}, f"🔴 `{name}` 경기 주소가 없다"
        got_p = await net.get(fm.BASE + url if url.startswith("/") else url)
        j = fm.payload(getattr(got_p, "text", "") or "")
        if not j:
            return {}, f"🔴 `{name}` 경기 페이지를 못 읽었다"
        lu = ((fm._page(j).get("content") or {}).get("lineup") or {})
        ids = fm.side_ids(j)
        which = "homeTeam" if (len(ids) == 2 and str(ids[0]) == str(tid)) \
            else "awayTeam"
        today = [r["name"] for r in fm.players_of(dict(lu.get(which) or {}))]
        if len(today) < 11:
            return {}, f"🔴 `{name}` 오늘 XI 가 {len(today)}명이다"
        # ── 평소 XI — **그 경기 앞** 경기들의 선발 빈도(L1)
        prior = fm.before_as_of([r for r in rows if r.get("finished")],
                                as_of=at)[-BACK:]
        tally: Counter = Counter()
        for r in prior:
            u = str(r.get("page") or "")
            if not u:
                continue
            p2 = await net.get(fm.BASE + u if u.startswith("/") else u)
            j2 = fm.payload(getattr(p2, "text", "") or "")
            if not j2:
                continue
            lu2 = ((fm._page(j2).get("content") or {}).get("lineup") or {})
            ids2 = fm.side_ids(j2)
            w2 = "homeTeam" if (len(ids2) == 2 and str(ids2[0]) == str(tid)) \
                else "awayTeam"
            for r3 in fm.players_of(dict(lu2.get(w2) or {})):
                tally[r3["name"]] += 1
        usual = [nm for nm, _n in tally.most_common(11)]
        if len(usual) < 11:
            return {}, (f"🔴 `{name}` 평소 XI 를 못 만들었다(앞 경기 "
                        f"{len(prior)}건 · 선수 {len(tally)}명)")
        from app.core import style as _sy
        gone = [nm for nm in usual if not _sy._same_player(nm, set(today))]
        out[name] = {"usual": usual, "today": today, "gone": gone,
                     "prior": len(prior)}
    return out, (f"평소 XI {BACK}경기 · 실제 결장 "
                 + " · ".join(f"{k} {len(v['gone'])}명"
                              for k, v in out.items()))


async def main(argv: list[str]) -> int:
    from app.core import style as _sy
    from app.core.state import RunState
    from app.net import Net
    limit = 0
    for a in argv[1:]:
        if a.startswith("--limit"):
            limit = int(a.split("=", 1)[1] if "=" in a else argv[argv.index(a)
                                                                + 1])
    net = Net(cache=True)
    state = RunState()
    box = cards(limit)
    print("# 🔴🔴 §6-7 검색 품질 **기준선**(고치기 전 숫자)")
    print()
    print(f"저장된 카드 **{len(box)}장**(머리를 읽은 것만) · 결장 주장을 적은 카드 "
          f"{sum(1 for c in box if any(c['claims'].values()))}장")
    print()
    rows: list[dict] = []
    gone_funnel = Counter()
    for i, one in enumerate(box, 1):
        print(f"   … {i}/{len(box)} {one['home']} vs {one['away']}", flush=True)
        got, why = await truth(net, one, state=state)
        if not got:
            gone_funnel[why[:40]] += 1
            continue
        for team, said in got.items():
            claims = []
            for key, names in one["claims"].items():
                if _sy._same_player(key, {team}) or key == team:
                    claims = names
            hit = [nm for nm in said["gone"]
                   if _sy._same_player(nm, set(claims))]
            rows.append({"league": one["league"], "team": team,
                         "file": one["file"], "claims": len(claims),
                         "gone": len(said["gone"]), "hit": len(hit)})
    print()
    if not rows:
        print("🔴 **정답을 만든 쪽이 없다** — 아래 실패 사유를 본다")
    else:
        print("| 리그 | 쪽 | 실제 결장 | 카드 주장 | 맞은 것 | 재현율 | 정밀도 |")
        print("|---|---|---|---|---|---|---|")
        for league in sorted({r["league"] for r in rows}):
            mine = [r for r in rows if r["league"] == league]
            g = sum(r["gone"] for r in mine)
            c = sum(r["claims"] for r in mine)
            h = sum(r["hit"] for r in mine)
            print(f"| {league} | {len(mine)} | {g} | {c} | {h} | "
                  + (f"**{h / g:.1%}**" if g else "⬜")
                  + " | " + (f"{h / c:.1%}" if c else "⬜") + " |")
        gone = sum(r["gone"] for r in rows)
        claims = sum(r["claims"] for r in rows)
        hit = sum(r["hit"] for r in rows)
        print()
        print(f"🔴 **전체 — 재현율 {hit / max(1, gone):.1%}"
              f"({hit}/{gone}) · 정밀도 {hit / max(1, claims):.1%}"
              f"({hit}/{claims})**")
    print()
    print("## 🔴 손실 깔때기 — 정답을 **만들지 못한** 까닭")
    print()
    for why, n in gone_funnel.most_common():
        print(f"- {n}건 — {why}")
    print()
    print("⚠️ **SQ1** — 이 측정은 경기 **뒤** 기록을 본다(측정용). 카드·확률 경로는"
          " 이 도구를 부르지 않는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
