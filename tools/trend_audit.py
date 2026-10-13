"""🔴🔴 **§6 S4 — 폼 추세 그룹 보정표**(통합 지시서 2026-10-13 밤).

```
PYTHONPATH=. python tools/trend_audit.py
```

> `trend` = (이번 시즌 **최근 2경기** 경기당 득실차) − (그 앞 이번 시즌 경기
> 경기당 득실차) · **수축**(경기 수 가중).
> 그룹 보정표: **|trend| 상위 20%** 팀 — B 예측 vs 실제.
> **편향 있을 때만** 경계 모듈 항으로 판정. 없으면 **표시도 하지 않는다**(소음).

🔴 그래서 이 도구는 **먼저 편향을 잰다** — 편향이 구간상 없으면 `app/` 에 코드를
   만들지 않는다(안 이어질 코드를 미리 짓지 않는다 · 규율 2).
🔴 수축은 `n/(n+2)` 다(`n` = 그 앞 경기 수) — 2경기로 센 차이가 **표본 둘**짜리
   라서 그대로 믿을 수 없다. ⚠️ 그 수(2)는 **보고에 적는다**(손값임을 숨기지 않는다).
"""
from __future__ import annotations

import json
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 "최근" 의 뜻 — 지시서의 2경기
RECENT = 2
#: 🔴 수축 상수 — `n/(n+K)`(보고에 적는다)
K = 2.0
#: 🔴 그룹 — |trend| 상위 이 비율
TOP = 0.20


def rows_of() -> tuple[list[dict], str]:
    """🔴 경기 **쪽마다** 한 줄 — `{trend, p_win, won, league, season, games}`."""
    from app.core import probfloor as pf
    from app.core import season as se
    back = json.loads((ROOT / "var/judge/replay_big2.json").read_text(
        encoding="utf-8"))
    out: list[dict] = []
    hist: dict[tuple[str, str], list[float]] = {}
    gone = 0
    for r in sorted(back, key=lambda x: str(x.get("day"))):
        if not r.get("lam"):
            gone += 1
            continue
        league = str(r.get("league") or "")
        at = datetime.fromisoformat(f"{r['day']}T12:00:00+00:00")
        season, _w = se.id_of(league=league, when=at)
        mk = pf.markets_of(pf.score_grid(lam_home=float(r["lam"][0]),
                                         lam_away=float(r["lam"][1]),
                                         rho=0.0))
        p = {"home": mk["home"], "away": mk["away"]}
        for side in ("home", "away"):
            team = str(r[side])
            said = list(hist.get((team, season)) or [])
            if len(said) >= RECENT + 1:
                late = st.fmean(said[-RECENT:])
                early = st.fmean(said[:-RECENT])
                n = len(said) - RECENT
                trend = (late - early) * (n / (n + K))
                out.append({"league": league, "season": season, "team": team,
                            "trend": trend, "p_win": p[side],
                            "won": 1 if ((r["hit"] == 0 and side == "home")
                                         or (r["hit"] == 2
                                             and side == "away")) else 0,
                            "games": len(said), "day": str(r["day"])})
        gd = int(r["hg"]) - int(r["ag"])
        hist.setdefault((str(r["home"]), season), []).append(float(gd))
        hist.setdefault((str(r["away"]), season), []).append(float(-gd))
    return out, (f"쪽 줄 **{len(out)}개**(λ 없는 경기 {gone}건 제외 · "
                 f"이번 시즌 {RECENT + 1}경기 이상인 쪽만)")


def table(rows: list[dict], *, name: str) -> None:
    from app.core import metrics as me
    if not rows:
        print(f"| {name} | 0 | — | — | — |")
        return
    pred = st.fmean([r["p_win"] for r in rows])
    won = sum(r["won"] for r in rows)
    lo, hi = me.wilson(won, len(rows))
    gap = won / len(rows) - pred
    print(f"| {name} | {len(rows)} | {pred:.1%} | **{won / len(rows):.1%}** | "
          f"{lo:.1%}~{hi:.1%} | {gap:+.1%} | "
          + ("🔴 **편향**" if (lo > pred or hi < pred) else "구간이 예측을 품는다")
          + " |")


def main(argv: list[str]) -> int:
    rows, why = rows_of()
    print("# 🔴🔴 §6 S4 — 폼 추세 그룹 보정표")
    print()
    print(why)
    print(f"🔴 `trend` = (최근 {RECENT}경기 평균 득실차) − (그 앞 평균) × "
          f"n/(n+{K:g}) — 수축 상수 **{K:g}** 는 손값이고 그 사실을 적는다.")
    print()
    vals = sorted(abs(r["trend"]) for r in rows)
    cut = vals[int(len(vals) * (1 - TOP))] if vals else 0.0
    print(f"- |trend| 분포 — 평균 {st.fmean([abs(r['trend']) for r in rows]):.3f}"
          f" · 상위 {TOP:.0%} 문턱 **{cut:.3f}**")
    print()
    print("| 그룹 | 쪽 줄 | B 예측 승률 | 실제 승률 | 95% | 차이 | 판정 |")
    print("|---|---|---|---|---|---|---|")
    table(rows, name="전체")
    top = [r for r in rows if abs(r["trend"]) >= cut]
    table(top, name=f"|trend| 상위 {TOP:.0%}")
    table([r for r in top if r["trend"] > 0], name="↳ 상승세(trend>0)")
    table([r for r in top if r["trend"] < 0], name="↳ 하락세(trend<0)")
    print()
    print("🔴 **판정 기준**(지시서 §6) — 구간이 예측을 품으면 **편향 없음**이고,"
          " 그러면 **확률에 넣지 않고 표시도 하지 않는다**(소음).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
