"""🔴🔴 **§1 백필 — 교체 시각 확보율**(라인업 지시서 2026-10-13 §1).

```
PYTHONPATH=. python tools/minutes_backfill.py            # J1 두 시즌
```

> J1·K1 0-0 포함 전 경기 → **리그·시즌별 교체 시각 확보율 표**.

🔴 J리그는 `data.j-league.or.jp` 가 분을 준다(실측). K리그는 **통로가 없다** —
   그 사실을 표가 적고 그 리그는 **거친 판**으로 간다(지어내지 않는다).
🔴 신원 매칭 실패율을 **경기별로** 센다(§1: *"실패율 경기별 기록"*).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 J리그 대회 틀 id — 1 = J1(실측: `competition_frame_ids=1` 이 J1 을 준다)
FRAMES = {"league:J1": 1}


async def jl_cards(net, *, year: int, frame: int) -> list[dict]:
    """🔴 그 시즌 경기 목록 → `[{card_id, day, home, away, score}]`.

    🔴🔴 **스코어를 함께 읽는다** — 경기 맞춤의 열쇠가 **날짜 + 스코어**이기
       때문이다(이름으로는 1.0% 밖에 못 맞췄다 · 실측 2026-10-13).
    """
    from app.collect import minutes as mn
    got = await net.get(mn.JL_LIST.format(year=year, frame=frame))
    said = getattr(got, "text", "") or ""
    out: list[dict] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", said, re.S):
        card = re.search(r"match_card_id=(\d+)", row)
        if not card:
            continue
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        day = ""
        for c in cells:
            m = re.search(r"(\d\d)/(\d\d)/(\d\d)", c)
            if m:
                day = f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
                break
        score = None
        for c in cells:
            m = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", c)
            if m:
                score = (int(m.group(1)), int(m.group(2)))
                break
        teams = [c for c in cells if c and not re.search(r"\d", c)]
        out.append({"card_id": card.group(1), "day": day, "score": score,
                    "home": (teams[0] if teams else ""),
                    "away": (teams[1] if len(teams) > 1 else "")})
    return out


def jst_day(row: dict) -> str:
    """🔴 UTC 저장 → **일본 현지 날짜**(자료 사이트가 현지 날짜를 쓴다)."""
    at = datetime.fromisoformat(str(row["utc"]).replace("Z", "+00:00"))
    return (at + timedelta(hours=9)).date().isoformat()


def learn(flat: list[dict], rows: list[dict]) -> dict[str, str]:
    """🔴🔴 **1차 통과** — 날짜+스코어가 하나로 떨어진 경기에서 팀명을 배운다."""
    from app.collect import minutes as mn
    pairs: list[tuple[dict, dict]] = []
    for r in rows:
        day = jst_day(r)
        hit = [c for c in flat if str(c.get("day")) == day
               and tuple(c.get("score") or ()) == (int(r["hg"]), int(r["ag"]))]
        if len(hit) == 1:
            pairs.append((hit[0], r))
    got = mn.learn_names(pairs)
    print(f"   · 배운 팀명 **{len(got)}개**(1:1 로 떨어진 {len(pairs)}경기에서)",
          flush=True)
    return got


async def one_match(net, *, flat: list[dict], row: dict,
                    names: dict[str, str] | None = None) -> tuple[dict, str]:
    """🔴 한 경기 → `{side: {fotmob id: (in, out)}}` 과 사유.

    🔴 열쇠 둘 — 경기는 **날짜+스코어**, 선수는 **등번호**(`shirtNumber`).
    """
    from app.collect import minutes as mn
    # 🔴🔴 **JST 로 맞춘다** — J리그 자료 사이트의 날짜는 **현지(일본) 날짜**이고
    #    우리 목록은 UTC 다(절대규칙: 저장은 UTC · 비교는 현지로 옮겨서).
    day = jst_day(row)
    card = mn.pick_card(rows=flat, day=day, home=row["home"], away=row["away"],
                        score=(int(row["hg"]), int(row["ag"])), names=names)
    if not card:
        return {}, "🔴 경기를 못 맞췄다(날짜+스코어가 하나로 안 떨어진다)"
    page = await net.get(mn.JL_MATCH.format(card=card))
    sides, why = mn.sides_of_jleague(getattr(page, "text", "") or "")
    if not sides:
        return {}, why
    out: dict[str, dict] = {}
    notes: list[str] = [why]
    for side in ("home", "away"):
        nums = {int(v): k for k, v in
                dict(row.get(f"{side}_nums") or {}).items()}   # 등번호 → id
        got = dict(sides[side])
        names = {**got["starters"], **got["bench"]}
        box, w2 = mn.intervals_by_number(
            starters={n: (0, mn.FULL) for n in got["starters"].values()},
            subs=got["subs"], names=names)
        kept = {nums[n]: v for n, v in box.items() if n in nums}
        notes.append(f"{side}: {w2} · id 로 이은 선수 {len(kept)}/{len(box)}명")
        out[side] = kept
        out.setdefault("_stat", {"구간": 0, "이음": 0})
        out["_stat"]["구간"] += len(box)
        out["_stat"]["이음"] += len(kept)
    return out, " · ".join(notes)


async def main(argv: list[str]) -> int:
    from app.collect import minutes as mn
    from app.net import Net
    net = Net(cache=True)
    print("# 🔴🔴 §1 출전 시간 — **통로 셋**(정확한 시각 · 뛴 분 · 거친 판)")
    print()
    rows = json.loads((ROOT / "var/judge/lineup_rows2.json").read_text(
        encoding="utf-8"))
    ev_path = ROOT / "var/judge/events.json"
    ev = (json.loads(ev_path.read_text(encoding="utf-8"))
          if ev_path.exists() else {})
    print(f"🔴 fotmob 경기 선수 기록(`playerStats`) — 받아 둔 경기 "
          f"**{len(ev)}건**"
          + ("" if ev else " 🔴 **없다**(`tools/match_events.py` 를 먼저 돌린다)"))
    print()
    # 🔴🔴 **MN1** — `--as-of` 를 주면 그 **이전 경기만** 적는다(§2 전진 판).
    #    문은 `minutes.before` 하나다(= `fotmob.before_as_of`).
    said_as_of = ([a.split("=", 1)[1] for a in argv[1:]
                   if a.startswith("--as-of=")] or [None])[0]
    if said_as_of:
        at = datetime.fromisoformat(said_as_of).replace(tzinfo=timezone.utc)
        was = len(rows)
        rows = mn.before(rows, as_of=at)
        print(f"🔴 **as-of {said_as_of}** — {was} → **{len(rows)}경기**"
              f"(MN1: 그 뒤 경기는 안 쓴다)")
        print()
    by_league: dict[str, list[dict]] = {}
    for r in rows:
        by_league.setdefault(str(r["league"]), []).append(r)
    lines: list[str] = []
    dump: dict[str, dict] = {}       #: 🔴 §2 가 쓸 출전 구간
    for league, said in sorted(by_league.items()):
        flat: list[dict] = []
        names: dict[str, str] = {}
        window = ("", "")
        if league in FRAMES:
            for year in (2026, 2027):
                try:
                    flat += await jl_cards(net, year=year,
                                           frame=FRAMES[league])
                except Exception as exc:                    # noqa: BLE001
                    print(f"🔴 {league} {year} 목록 실패 {exc!r:.60}")
            days = sorted({str(c.get("day") or "") for c in flat
                           if str(c.get("day") or "")})
            window = (days[0], days[-1]) if days else ("", "")
            print(f"   · J리그 경기 목록 **{len(flat)}건** "
                  f"({window[0]}~{window[1]})", flush=True)
            names = learn(flat, said)
        kind = {"정확한 시각": 0, "뛴 분": 0, "거친 판": 0}
        fails: list[float] = []
        for i, r in enumerate(said, 1):
            if i % 50 == 0:
                print(f"   … {league} {i}/{len(said)}", flush=True)
            key = f"{r['utc']}|{r['home']}|{r['away']}"
            box: dict[str, dict] = {}
            # ① J리그 **정확한 시각**
            if flat and window[0] <= jst_day(r) <= window[1]:
                box, why = await one_match(net, flat=flat, row=r, names=names)
                if box:
                    stat = dict(box.get("_stat") or {})
                    span = int(stat.get("구간") or 0)
                    fails.append(max(0.0, 1.0 - int(stat.get("이음") or 0)
                                     / max(1, span)))
                    kind["정확한 시각"] += 1
            # ② fotmob **뛴 분**
            if not box:
                pstat = dict((ev.get(key) or {}).get("pstat") or {})
                if pstat:
                    got: dict[str, dict] = {}
                    ok = True
                    for side in ("home", "away"):
                        one, _w = mn.intervals_from_minutes(
                            starters=[str(x) for x in r[f"{side}_ids"]],
                            bench=[str(x) for x in r[f"{side}_bench"]],
                            played=pstat)
                        ok = ok and bool(one)
                        got[side] = one
                    if ok:
                        box = got
                        kind["뛴 분"] += 1
            # ③ **거친 판**(선발 90분 · 안 뛴 벤치는 칸이 없다 · MN2)
            if not box:
                box = {side: mn.intervals(
                    starters=[str(x) for x in r[f"{side}_ids"]], subs=None,
                    bench=[str(x) for x in r[f"{side}_bench"]])[0]
                    for side in ("home", "away")}
                kind["거친 판"] += 1
            dump[key] = {side: {k: list(v) for k, v in box[side].items()}
                         for side in ("home", "away")}
        n = max(1, len(said))
        fail = (sum(fails) / len(fails)) if fails else None
        lines.append(
            f"| {league} | {len(said)} | **{kind['정확한 시각']}** "
            f"({kind['정확한 시각'] / n:.1%}) | **{kind['뛴 분']}** "
            f"({kind['뛴 분'] / n:.1%}) | {kind['거친 판']} "
            f"({kind['거친 판'] / n:.1%}) | "
            + (f"{fail:.1%}" if fail is not None else "—") + " |")
    out = ROOT / "var/judge/minutes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"🔴 출전 구간 **{len(dump)}경기**를 적었다 — {out}")
    print()
    print("| 리그 | 경기 | ① 정확한 시각(J리그) | ② 뛴 분(fotmob) | "
          "③ 거친 판 | 신원 실패율(①) |")
    print("|---|---|---|---|---|---|")
    for one in lines:
        print(one)
    print()
    print("🔴 ① 은 **교체 시각**이다(J리그 자료 사이트 · 경기는 날짜+스코어, 선수는 "
          "등번호로 이었다). ② 는 **뛴 분**이고 in/out **시각이 아니다** — 선발 "
          "`[0,분]` · 투입 `[90−분,90]` 로 읽는다. ③ 은 선발 90분이다.")
    print("⚠️ **MN2** — 안 뛴 벤치 선수는 **칸이 없다**(0분으로 넣지 않는다).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
