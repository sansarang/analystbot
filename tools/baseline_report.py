#!/usr/bin/env python
"""[LE-2] 기준선 3개의 리그별 Brier 표 — **LE-2 완료 조건.**

지시문 LE-2-4:
> "기준선 3개를 항상 같이 잰다: (i) 시장 디빅값 그대로 (ii) 50% 고정
>  (iii) 팀 Elo 만. **엔진이 (i) 을 Brier·CLV 에서 못 이기면 후보를 내지 않는다.**"

🔴 역사 자료(`history_*`, LE-1b)에서 읽는다. 한 경기 = 한 행이고, 확률은
   **개장가**(`phase='open'`)를 디빅한 값이다.
   ⚠️ **마감가를 쓰지 않는다** — 그건 정답지다(누설). CLV 계산에만 쓴다.

  python -m tools.baseline_report                 # 전 리그
  python -m tools.baseline_report --book Avg      # 참 확률로 쓸 북
  python -m tools.baseline_report --div E0
"""
from __future__ import annotations

import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("baseline_report")

#: 🔴 개장가 = **결정 시점**의 가격. 마감가는 종가(CLV 의 상대편)다.
_SQL = """
    SELECT m.div, m.season, m.match_date, m.ftr,
           max(CASE WHEN p.phase='open'  AND p.side='home' THEN p.odds END) oh,
           max(CASE WHEN p.phase='open'  AND p.side='draw' THEN p.odds END) od,
           max(CASE WHEN p.phase='open'  AND p.side='away' THEN p.odds END) oa,
           max(CASE WHEN p.phase='close' AND p.side='home' THEN p.odds END) ch,
           max(CASE WHEN p.phase='close' AND p.side='draw' THEN p.odds END) cd,
           max(CASE WHEN p.phase='close' AND p.side='away' THEN p.odds END) ca
      FROM history_matches m
      JOIN history_prices p ON p.match_id = m.id
     WHERE p.market='h2h' AND p.book = $1
       AND ($2::text IS NULL OR m.div = $2)
       AND m.ftr IN ('H','D','A')
     GROUP BY m.id, m.div, m.season, m.match_date, m.ftr
     ORDER BY m.match_date
"""


def rows_from(recs) -> list[dict]:
    """DB 행 → 기준선 입력. **홈 승 여부**를 맞히는 문제로 둔다.

    🔴 3-way 를 2-way 로 줄이지 않는다 — 무승부는 `push` 로 분모에서 뺀다
       (`pick_ledger` 와 같은 규약).
    ⚠️ 개장가가 셋 다 있어야 디빅이 된다. 하나라도 없으면 그 경기는 뺀다.
    """
    from app.learning.prices import devig

    out = []
    for r in recs:
        o = devig({"home": r["oh"], "draw": r["od"], "away": r["oa"]})
        if not o:
            continue
        c = devig({"home": r["ch"], "draw": r["cd"], "away": r["ca"]})
        ftr = r["ftr"]
        out.append({
            "div": r["div"], "season": r["season"], "ts": r["match_date"],
            "p_market": o["home"],
            "p_market_at_decision": o["home"],
            "p_close": (c or {}).get("home"),
            "price_at_decision": float(r["oh"]) if r["oh"] else None,
            # 🔴 무승부는 분모에서 뺀다 — 손실로 세면 적중률·ROI 가 동시에 거짓
            "result": "win" if ftr == "H" else ("loss" if ftr == "A" else "push"),
        })
    return out


def _fmt(v, n=4):
    return "—" if v is None else f"{v:.{n}f}"


def _line(label, s):
    if s.get("insufficient"):
        return f"    {label:8s} n={s['n']:5d}  **표본 부족**(하한 {s['min_samples']})"
    mono = s.get("monotone")
    return (f"    {label:8s} n={s['n']:5d}  Brier {_fmt(s['brier'])}  "
            f"로그손실 {_fmt(s['log_loss'])}  적중 {_fmt(s['hit_rate'],3)}  "
            f"CLV {_fmt(s['clv_mean'])}(n={s['clv_n']})  "
            f"보정 {'—' if mono is None else ('단조' if mono else '🔴깨짐')}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="Avg",
                    help="참 확률로 쓸 북 (Avg=여러 북 평균 · PS=피나클)")
    ap.add_argument("--div")
    a = ap.parse_args()

    from app.db import get_pool
    from app.learning import baselines as B

    pool = await get_pool()
    recs = await pool.fetch(_SQL, a.book, a.div)
    rows = rows_from(recs)
    print(f"\n{'='*78}\nLE-2 기준선 — 역사 자료 · 북 {a.book!r}"
          f"\n  DB 행 {len(recs)} → 디빅 가능 {len(rows)}\n{'='*78}")
    if not rows:
        print("  자료가 없다. `python -m tools.backfill_history` 로 먼저 적재하라.")
        return

    print("\n[전 리그]")
    s = B.score(rows)
    print(f"  기준선 {s['_names']} · 공통 표본 {s['_sample']} · 제외 {s['_dropped']}")
    for n in s["_names"]:
        print(_line(n, s[n]))

    print("\n[리그별]")
    from app.learning.split import by_league

    for div, sub in sorted(by_league(rows, league_key="div").items(),
                           key=lambda kv: str(kv[0])):
        ss = B.score(sub)
        print(f"  {div}  (공통 표본 {ss['_sample']})")
        for n in ss["_names"]:
            print(_line(n, ss[n]))

    print("\n⚠️ 확률은 **개장가** 디빅값이다 — 마감가는 정답지라 입력에 안 쓴다.")
    print("⚠️ 무승부는 `push` 로 분모에서 뺀다(홈 승 여부를 맞히는 문제다).")
    print("🔴 엔진은 `market` 을 **Brier·CLV 둘 다에서** 이겨야 후보를 낸다.")


if __name__ == "__main__":
    asyncio.run(main())
