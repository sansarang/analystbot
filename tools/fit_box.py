"""🔴🔴 **선수 가치 v2 적합 + 안정성**(사용자 결정 2026-10-13 저녁 · 1번).

```
PYTHONPATH=. python tools/fit_box.py
```

🔴 **보고 첫 줄 = 반분 상관(J1·K1)** — **0.3 미만이면 거기서 멈춘다**(사용자 지시).
🔴 재료는 §1·§2 가 적어 둔 것이다(다시 받지 않는다): `var/judge/events.json`
   (선수별 분·xG·xA·포지션) + `var/judge/lineup_rows2.json`(경기 열쇠·리그).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def matches_of(league: str) -> list[dict]:
    """🔴 그 리그의 경기 → `{utc, league, pstat, pos, season}`."""
    from fit_pm import key_of, season_blocks
    rows = [r for r in json.loads(
        (ROOT / "var/judge/lineup_rows2.json").read_text(encoding="utf-8"))
        if str(r["league"]) == league]
    ev = json.loads((ROOT / "var/judge/events.json").read_text(
        encoding="utf-8"))
    seasons = season_blocks(rows)
    out: list[dict] = []
    for r in rows:
        said = dict(ev.get(key_of(r)) or {})
        out.append({"utc": r["utc"], "league": league,
                    "season": seasons.get(key_of(r), ""),
                    "pstat": dict(said.get("pstat") or {}),
                    "pos": dict(said.get("pos") or {})})
    return out


def main(argv: list[str]) -> int:
    from app.core.ratings import player_box as pb
    from app.core.ratings import player_pm as pm
    said_as_of = ([a.split("=", 1)[1] for a in argv[1:]
                   if a.startswith("--as-of=")] or ["2026-10-13"])[0]
    as_of = datetime.fromisoformat(said_as_of).replace(tzinfo=timezone.utc)
    print("# 🔴🔴 선수 가치 v2 — 박스 기록(90분당 xG+xA)")
    print()
    first: list[str] = []
    notes: list[str] = []
    print("| 리그 | 경기 | 선수(공격/뒷선) | 450분 미만 수축 | **반분 상관** | 문턱 0.3 |")
    print("|---|---|---|---|---|---|")
    for league in ("league:J1", "league:KL1"):
        rows = matches_of(league)
        table = pb.fit(rows, as_of=as_of)
        if not table.value:
            print(f"| {league} | {len(rows)} | 🔴 {table.why} | — | — | — |")
            continue
        half = len(rows) // 2
        said = sorted(rows, key=lambda r: r["utc"])
        a = pb.fit(said[:half], as_of=as_of)
        b = pb.fit(said[half:], as_of=as_of)
        # 🔴 상관은 **공격 쪽만** 센다 — 뒷선 수는 출전 분 비중이라 단위가 다르다
        ka = {k: v for k, v in a.value.items() if a.kind.get(k) == "공격"}
        kb = {k: v for k, v in b.value.items() if b.kind.get(k) == "공격"}
        r_half, why_half = pm.stability(ka, kb)
        front = sum(1 for k in table.kind.values() if k == "공격")
        print(f"| {league} | {len(rows)} | {front}/"
              f"{len(table.kind) - front} | {table.shrunk}명 | "
              f"**{r_half:+.2f}** | "
              f"{'✅ 넘었다' if r_half >= 0.3 else '🔴 **미달**'} |")
        first.append(f"{league} **{r_half:+.2f}**")
        notes.append(f"- **{league}** — {why_half}")
        notes.append(f"  · {table.why}")
        box = ROOT / "data/player_box" / league.replace(":", "_")
        said_w = pm.save(box / f"{said_as_of}.parquet", value=table.value,
                         minutes=table.minutes, pos=table.pos, raw=table.raw)
        notes.append(f"  · {said_w} → `{box}/{said_as_of}.parquet`")
    print()
    print("🔴 **첫 줄 — 선수 가치 v2 반분 상관:** " + " · ".join(first))
    print()
    for one in notes:
        print(one)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
