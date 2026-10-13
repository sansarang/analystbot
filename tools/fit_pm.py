"""🔴🔴 **§2 선수 점수 적합**(라인업 지시서 2026-10-13 §2).

```
PYTHONPATH=. python tools/fit_pm.py                 # 판 + 안정성 보고
PYTHONPATH=. python tools/fit_pm.py --as-of 2026-10-13
```

받는 재료는 **§1 이 적어 둔 것**이다(다시 받지 않는다):
`var/judge/lineup_rows2.json`(XI·벤치·등번호) · `var/judge/minutes.json`(출전
구간) · `var/judge/events.json`(골 분·포지션).

🔴 **시즌은 일정의 빈 구간으로 가른다**(손으로 적지 않는다) — 30일 넘게 경기가
   없으면 그 자리가 시즌 경계다. 실측: J1 은 `2026 봄`·`2026-27 가을` 둘로,
   K1 은 해마다 하나로 갈린다.
🔴 벌 λ 는 **시즌 교차**로 고른다(`player_pm.pick_lam`) — 손값 금지.
🔴 안정성은 **시즌 반분 두 추정의 상관**이다(0.3 미만 "신뢰 낮음").
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 🔴 이만큼 경기가 없으면 **시즌 경계**다(실측으로 가른다 · 손 표 금지)
GAP_DAYS = 30


def season_blocks(rows: list[dict]) -> dict[str, str]:
    """🔴 `{경기 열쇠: 시즌 이름}` — 일정의 **빈 구간**으로 가른다."""
    said = sorted(rows, key=lambda r: str(r["utc"]))
    out: dict[str, str] = {}
    start = said[0]["utc"][:10] if said else ""
    prev: datetime | None = None
    for r in said:
        at = datetime.fromisoformat(str(r["utc"]).replace("Z", "+00:00"))
        if prev is not None and (at - prev) > timedelta(days=GAP_DAYS):
            start = at.date().isoformat()
        prev = at
        out[key_of(r)] = start
    return out


def key_of(r: dict) -> str:
    return f"{r['utc']}|{r['home']}|{r['away']}"


def matches_of(league: str) -> tuple[list[dict], str]:
    """🔴 §1·§2 재료를 **한 꼴**로 합친다. `(경기 목록, 사유)`."""
    rows = [r for r in json.loads(
        (ROOT / "var/judge/lineup_rows2.json").read_text(encoding="utf-8"))
        if str(r["league"]) == league]
    box = json.loads((ROOT / "var/judge/minutes.json").read_text(
        encoding="utf-8"))
    ev = json.loads((ROOT / "var/judge/events.json").read_text(
        encoding="utf-8")) if (ROOT / "var/judge/events.json").exists() else {}
    seasons = season_blocks(rows)
    out: list[dict] = []
    fine = no_ev = 0
    for r in rows:
        k = key_of(r)
        one = dict(box.get(k) or {})
        said = dict(ev.get(k) or {})
        if not said:
            no_ev += 1
        goals = list(said.get("goals") or [])
        if not goals and (int(r["hg"]) + int(r["ag"])) > 0:
            # 🔴 골 분을 모른다 — **지어내지 않는다**(그 경기는 구간 응답을
            #    만들 수 없으니 센 수를 보고에 남긴다)
            no_ev += 1
            continue
        got = {"utc": r["utc"], "league": league, "season": seasons.get(k, ""),
               "home": r["home"], "away": r["away"],
               "home_ids": [str(x) for x in r["home_ids"]],
               "away_ids": [str(x) for x in r["away_ids"]],
               "goals": goals, "pos": dict(said.get("pos") or {})}
        if one.get("home") and one.get("away"):
            got["home_box"] = one["home"]
            got["away_box"] = one["away"]
            if any(tuple(v) != (0, 90) for v in one["home"].values()):
                fine += 1
        out.append(got)
    why = (f"경기 {len(out)}건(분 단위 **{fine}건** · 나머지 거친 판) · "
           f"⬜ 골 분을 못 받아 버린 경기 **{no_ev}건**")
    return out, why


def main(argv: list[str]) -> int:
    from app.core.ratings import player_pm as pm
    said_as_of = ([a.split("=", 1)[1] for a in argv[1:]
                   if a.startswith("--as-of=")] or ["2026-10-13"])[0]
    as_of = datetime.fromisoformat(said_as_of).replace(tzinfo=timezone.utc)
    print("# 🔴🔴 §2 선수 점수 — 구간 ± · 팀 고정효과")
    print()
    print(f"as-of **{said_as_of}**")
    print()
    print("| 리그 | 재료 | 시즌 | 벌 λ(시즌 교차) | 선수 | 수축 | 반분 상관 |")
    print("|---|---|---|---|---|---|---|")
    notes: list[str] = []
    for league in ("league:J1", "league:KL1"):
        rows, why = matches_of(league)
        if not rows:
            print(f"| {league} | 🔴 재료 없음 | — | — | — | — | — |")
            continue
        seasons = sorted({r["season"] for r in rows})
        lam, lam_why = pm.pick_lam(rows, as_of=as_of,
                                   lams=(1.0, 10.0, 50.0, 200.0))
        table = pm.fit(rows, as_of=as_of, lam=lam)
        # 🔴 안정성 — 각 시즌을 **반으로** 갈라 두 추정의 상관
        half = len(rows) // 2
        a = pm.fit(sorted(rows, key=lambda r: r["utc"])[:half], as_of=as_of,
                   lam=lam)
        b = pm.fit(sorted(rows, key=lambda r: r["utc"])[half:], as_of=as_of,
                   lam=lam)
        r_half, why_half = pm.stability(a.value, b.value)
        box = ROOT / "data/player_pm" / league.replace(":", "_")
        # 🔴 **지난 판과 비교한다**(L3 로 `as_of` 이전 최신 판을 고른다) — 판이
        #    흔들리면 그 수가 라인업 신호를 흔든다(없으면 사유만 적는다).
        prev, why_prev = pm.load(box, as_of=as_of)
        r_prev, why_r = ((None, why_prev) if not prev.value
                         else pm.stability(prev.value, table.value))
        said = pm.save(box / f"{said_as_of}.parquet", value=table.value,
                       minutes=table.minutes, pos=table.pos, raw=table.raw)
        print(f"| {league} | {why} | {len(seasons)}개 "
              f"({' · '.join(seasons)}) | **{lam:g}** | "
              f"{len(table.value)}명 | {table.shrunk}명 | {why_half} |")
        notes.append(f"- **{league}** — {lam_why}")
        notes.append(f"  · {table.why}")
        notes.append(f"  · {said} → `{box}/{said_as_of}.parquet`")
        notes.append(f"  · 지난 판과 — {why_r}"
                     + (f"(상관 {r_prev:+.2f})" if r_prev is not None else ""))
    print()
    for one in notes:
        print(one)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
