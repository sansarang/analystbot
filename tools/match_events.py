"""🔴🔴 **§2 재료 — 골 분·포지션**(라인업 지시서 2026-10-13 §2).

```
PYTHONPATH=. python tools/match_events.py        # var/judge/events.json
```

🔴 왜 따로 받나 — 구간 ± 의 응답은 **구간 안의 골 차**다. 골을 45분에 몰아 넣으면
   (옛 `lineup_trial._pm_fit` 이 그랬다) 구간이 전부 같은 응답을 받아 **구간
   정보가 사라진다**. 그래서 **골의 분**을 받아 둔다.
🔴🔴 **실측 2026-10-13 — `playerStats` 가 선수별 `minutes_played`·xG·xA 를 준다**
   (두 리그 다 · 한 경기 40명). ⚠️ 이것은 2026-10-12 의 *"fotmob 은 교체 시각을
   주지 않는다"* 를 **덮는다** — 분(分)은 **있다**(정확한 in/out 시각이 아니라
   **뛴 분**이다). 🔴 선발은 `[0, 뛴 분]`, 교체 투입은 `[90 − 뛴 분, 90]` 으로
   읽는다(그 둘을 구분해 적는다 · 지어내지 않는다).
🔴 그래서 §3 의 **공격 기여표**도 이 통로로 채운다 — **경기별 xG+xA** 는
   as-of 정합이라 L2 가 막는 "시즌 누계" 대체 경로가 필요 없다.

🔴 포지션은 §2 의 *"리그·포지션 평균 쪽 수축"* 에 쓴다 — 없으면 **빈칸**이고
   수축은 리그 평균으로 간다(그 사실을 판이 적는다 · 지어내지 않는다).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def main(argv: list[str]) -> int:
    from app.collect import fotmob as fm
    from app.net import Net
    net = Net(cache=True)
    rows = json.loads((ROOT / "var/judge/lineup_rows2.json").read_text(
        encoding="utf-8"))
    out = ROOT / "var/judge/events.json"
    got: dict[str, dict] = {}
    if out.exists():                     # 🔴 받은 것에 **더한다**(#3)
        got = json.loads(out.read_text(encoding="utf-8"))
        print(f"이미 받은 {len(got)}경기에 더한다", flush=True)
    miss = {"payload 없음": 0, "골 목록 없음(0-0 이면 정상)": 0, "포지션 0개": 0,
            "playerStats 0명": 0}
    for i, r in enumerate(rows, 1):
        if i % 50 == 0:
            print(f"   … {i}/{len(rows)}", flush=True)
        key = f"{r['utc']}|{r['home']}|{r['away']}"
        if key in got and "pstat" in got[key]:
            continue
        page = await net.get(fm.match_url(str(r["fm_id"])))
        j = fm.payload(getattr(page, "text", "") or "")
        if not j:
            miss["payload 없음"] += 1
            continue
        goals = [{"min": int(g.get("minute") or 0), "home": bool(g.get("home"))}
                 for g in fm.goals_of(j) if g.get("minute") is not None]
        if not goals and (int(r["hg"]) + int(r["ag"])) > 0:
            miss["골 목록 없음(0-0 이면 정상)"] += 1
        lu = (((j.get("props") or {}).get("pageProps") or {})
              .get("content", {}).get("lineup") or {})
        pos: dict[str, str] = {}
        for side in ("homeTeam", "awayTeam"):
            box = dict(lu.get(side) or {})
            for p in ((box.get("starters") or []) + (box.get("subs") or [])):
                if isinstance(p, dict) and p.get("id"):
                    said = str(fm._pos_of(p) or "").strip()
                    if said:
                        pos[str(p["id"])] = said
        if not pos:
            miss["포지션 0개"] += 1
        # 🔴🔴 선수별 **뛴 분 · xG · xA**(`playerStats`) — §2 구간과 §3 기여표
        pstat: dict[str, dict] = {}
        box = (((j.get("props") or {}).get("pageProps") or {})
               .get("content", {}).get("playerStats") or {})
        for pid, one in dict(box).items():
            cell: dict[str, float] = {}
            for grp in (dict(one).get("stats") or []):
                for _title, v in (dict(grp).get("stats") or {}).items():
                    k2 = str(dict(v).get("key") or "")
                    val = dict(dict(v).get("stat") or {}).get("value")
                    if k2 in ("minutes_played", "expected_goals",
                              "expected_assists", "goals", "assists"):
                        try:
                            cell[k2] = float(val)
                        except (TypeError, ValueError):
                            pass
            if cell:
                pstat[str(pid)] = cell
        if not pstat:
            miss["playerStats 0명"] = miss.get("playerStats 0명", 0) + 1
        got[key] = {"goals": goals, "pos": pos, "pstat": pstat,
                    "hg": int(r["hg"]), "ag": int(r["ag"])}
    out.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
    # 🔴 골 분의 합이 스코어와 **맞는지** 센다(조용한 0 금지)
    bad = [k for k, v in got.items()
           if (sum(1 for g in v["goals"] if g["home"]) != v["hg"]
               or sum(1 for g in v["goals"] if not g["home"]) != v["ag"])]
    print(f"🔴 **{len(got)}경기**를 적었다 — {out}")
    print("🔴 빠진 이유 — " + " · ".join(f"{k} {v}건" for k, v in miss.items()))
    mins = sum(1 for v in got.values()
               if any("minutes_played" in c for c in
                      (v.get("pstat") or {}).values()))
    print(f"🔴 선수별 **뛴 분**이 있는 경기 **{mins}/{len(got)}** "
          f"({mins / max(1, len(got)):.1%})")
    print(f"🔴 골 분 합 ≠ 스코어 인 경기 **{len(bad)}건**"
          f"{' ' + str(bad[:3]) if bad else ''} — 그 경기의 구간 응답은 "
          f"**스코어가 아니라 골 분**을 따른다(둘이 다르면 §2 가 적는다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
