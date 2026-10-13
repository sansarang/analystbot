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
#: 🔴 `    Jeremy Ebobisse(?) — 부상 · 복귀 Mid November 2026 · www.fotmob.com`
#   ⚠️ 괄호는 **포지션**이다(`render` 의 `m.pos or '?'`) — **의심 표시가 아니다**.
#      🔴 내가 그것을 의심으로 잘못 읽어 286건이 전부 "의심"으로 찍혔다(2026-10-13).
CLAIM = re.compile(r"^ {4}([^—(]{2,40})(?:\(([^)]{0,12})\))? — (.+)$")

#: 🔴 사실 **종류** — 지시 2번의 세 갈래. 가르는 재료는 **꼬리의 글자**다:
#   `복귀 Doubtful` → **의심** · 복귀 날짜가 경기 **뒤** → **확정 결장** ·
#   복귀 날짜가 경기 **앞/당일** → **복귀**(그 경기에는 나올 수 있다)
DOUBT = ("doubtful", "의심", "불확실")
TEAM = re.compile(r"^- \*\*(.+?)\*\*\s*$")
#: 🔴 평소 XI 를 세는 경기 수(운영 `lineup_strength.USUAL_N` 과 같은 수)
BACK = 5


#: 🔴 `복귀 Mid November 2026` · `Early October 2026` 같은 꼴의 달 이름
_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
           "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
           "november": 11, "december": 12}


def _kind_by_date(tail: str, *, day: str) -> str:
    """🔴 복귀 날짜가 경기 **뒤**면 확정 결장 · **앞/당일**이면 복귀.

    ⚠️ fotmob 은 `Early/Mid/Late <달> <해>` 로 적는다(날짜가 아니라 **구간**이다)
       → 그 달의 1·15·25일로 본다(그 사실을 사유에 적는다 · 추측 아님: 그 글자가
       Early/Mid/Late 다).
    """
    low = str(tail or "").lower()
    got = re.search(r"(early|mid|late)?\s*([a-z]+)\s+(20\d\d)", low)
    if not got or got.group(2) not in _MONTHS:
        return "⬜ 복귀 시점 모름"
    part = {"early": 1, "mid": 15, "late": 25}.get(got.group(1) or "", 15)
    when = f"{got.group(3)}-{_MONTHS[got.group(2)]:02d}-{part:02d}"
    return "확정 결장" if when > str(day) else "복귀"


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
                    tail = str(one.group(3) or "")
                    low = tail.lower()
                    kind = ("의심" if any(w in low for w in DOUBT)
                            else _kind_by_date(tail, day=f"2026-{head.group(4)}"
                                               f"-{head.group(5)}"))
                    host = ""
                    got_h = re.search(r"([a-z0-9.-]+\.[a-z]{2,})\s*$", tail)
                    if got_h:
                        host = got_h.group(1)
                    box[team].append({"name": one.group(1).strip(),
                                      "pos": str(one.group(2) or ""),
                                      "kind": kind, "why": tail[:40],
                                      "tail": tail[:60], "host": host})
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
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **정답을 둘로 가른다**(지시 2번 · 2026-10-13 밤 넷째)
        # ══════════════════════════════════════════════════════════════
        #
        #  (가) 부상·징계 결장 · (나) 로테이션·벤치(사유 없는 미선발).
        #  🔴🔴 **사유를 주는 허용 경로가 없다**(실측 2026-10-13): 경기 페이지에
        #     결장 목록이 **없고**(`lineup` 에 `unavailable` 칸이 없다), 선수
        #     페이지는 `injuryInformation` 이 **현재 값**이며, J리그 `SFPR02`
        #     (경고·퇴장 누적)는 **검색 양식**이다(인자 미조사).
        #  🔴 그래서 **대리 기준**을 쓴다 — **다음 경기에 선발 복귀하면 (나)**,
        #     그 경기도 못 나오면 **(가)** 로 본다. ⚠️ 추정이고, 보고가 그렇게
        #     적는다(실측: 결장의 44%가 다음 경기에 선발 복귀한다).
        nxt = [r for r in rows if r.get("finished")
               and str(r.get("utc") or "") > str(want[0]["utc"])]
        nxt.sort(key=lambda r: str(r.get("utc")))
        after: list[str] = []
        why_next = "⬜ 다음 경기가 없다 — (가)/(나) 를 못 가린다"
        if nxt:
            u2 = str(nxt[0].get("page") or "")
            if u2:
                p3 = await net.get(fm.BASE + u2 if u2.startswith("/") else u2)
                j3 = fm.payload(getattr(p3, "text", "") or "")
                if j3:
                    lu3 = ((fm._page(j3).get("content") or {})
                           .get("lineup") or {})
                    ids3 = fm.side_ids(j3)
                    w3 = ("homeTeam" if (len(ids3) == 2
                                         and str(ids3[0]) == str(tid))
                          else "awayTeam")
                    after = [r["name"] for r in
                             fm.players_of(dict(lu3.get(w3) or {}))]
                    why_next = (f"다음 경기 {str(nxt[0].get('utc'))[:10]} 선발 "
                                f"{len(after)}명")
        rot = [nm for nm in gone if after and _sy._same_player(nm, set(after))]
        hurt = [nm for nm in gone if nm not in rot]
        out[name] = {"usual": usual, "today": today, "gone": gone,
                     "rot": rot, "hurt": hurt, "next_why": why_next,
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
            names = {str(c["name"]) for c in claims}
            rows.append({
                "league": one["league"], "team": team, "file": one["file"],
                "claims": claims,
                # 🔴 (가)/(나) — 둘 다 **카드 주장과 맞춰** 센다
                "hurt": list(said["hurt"]), "rot": list(said["rot"]),
                "hit_hurt": [nm for nm in said["hurt"]
                             if _sy._same_player(nm, names)],
                "hit_rot": [nm for nm in said["rot"]
                            if _sy._same_player(nm, names)],
                "next_why": said["next_why"]})
    print()
    if not rows:
        print("🔴 **정답을 만든 쪽이 없다** — 아래 실패 사유를 본다")
    else:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **(가) 부상·징계 / (나) 로테이션 따로**(지시 2번)
        # ══════════════════════════════════════════════════════════════
        print("## 🔴 (가) 부상·징계(추정) / (나) 로테이션 — 리그별")
        print()
        print("| 리그 | 쪽 | (가) 결장 | (가) 잡음 | **(가) 재현율** | "
              "(나) 결장 | (나) 잡음 | (나) 재현율 |")
        print("|---|---|---|---|---|---|---|---|")
        for league in sorted({r["league"] for r in rows}):
            mine = [r for r in rows if r["league"] == league]
            h = sum(len(r["hurt"]) for r in mine)
            hh = sum(len(r["hit_hurt"]) for r in mine)
            t = sum(len(r["rot"]) for r in mine)
            th = sum(len(r["hit_rot"]) for r in mine)
            print(f"| {league} | {len(mine)} | {h} | {hh} | "
                  + (f"**{hh / h:.1%}**" if h else "⬜") + f" | {t} | {th} | "
                  + (f"{th / t:.1%}" if t else "⬜") + " |")
        h = sum(len(r["hurt"]) for r in rows)
        hh = sum(len(r["hit_hurt"]) for r in rows)
        t = sum(len(r["rot"]) for r in rows)
        th = sum(len(r["hit_rot"]) for r in rows)
        print()
        print(f"🔴 **전체 — (가) 재현율 {hh / max(1, h):.1%}({hh}/{h}) · "
              f"(나) 재현율 {th / max(1, t):.1%}({th}/{t})**")
        print()
        # ── 🔴 **정밀도** — 종류·등급 칸마다(지시 2번)
        from app.core import competition as _cp
        from app.core.search import sources as _sr
        print("## 🔴 정밀도 — 사실 **종류** × 원천 **등급**")
        print()
        print("| 종류 | 등급 | 주장 | (가)에 맞음 | (나)에 맞음 | 빗나감 | "
              "**정밀도(가)** | 정밀도(가+나) |")
        print("|---|---|---|---|---|---|---|---|")
        cells: dict[tuple, dict] = {}
        for r in rows:
            key_l, _w = _cp.key_of(competition=r["league"])
            for c in r["claims"]:
                grade, _wg = _sr.grade_of(str(c.get("host") or ""),
                                          league=key_l or "")
                key = (str(c.get("kind")), grade)
                box_c = cells.setdefault(key, {"n": 0, "a": 0, "b": 0})
                box_c["n"] += 1
                nm = str(c.get("name"))
                if _sy._same_player(nm, set(r["hurt"])):
                    box_c["a"] += 1
                elif _sy._same_player(nm, set(r["rot"])):
                    box_c["b"] += 1
        for key in sorted(cells, key=lambda k: -cells[k]["n"]):
            one_c = cells[key]
            n, a, b = one_c["n"], one_c["a"], one_c["b"]
            print(f"| {key[0]} | {key[1]} | {n} | {a} | {b} | {n - a - b} | "
                  f"**{a / n:.1%}** | {(a + b) / n:.1%} |")
        print()
        low = [k for k, v in cells.items()
               if v["n"] >= 10 and v["a"] / v["n"] < 0.20]
        print("🔴 **정밀도가 낮은 칸(10건 이상 · (가) 정밀도 20% 미만)** — "
              + (" · ".join(f"{k[0]}/{k[1]}" for k in low) if low else "없다"))
        print("⚠️ 지시의 후보(*\"확정 결장·S/A 만 예상 XI 반영\"*)를 지금 적용하면 "
              + ("**아무 것도 안 남는다**"
                 if not any(k[1] in ("S", "A") for k in cells)
                 else "그 칸만 남는다") + " — 지금 결장 주장의 원천은 "
              + " · ".join(f"{k[1]} {sum(v['n'] for kk, v in cells.items() if kk[1] == k[1])}"
                           for k in sorted({(k[1],) and k for k in cells},
                                           key=lambda x: x[1])[:1]) + " 뿐이다")
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
