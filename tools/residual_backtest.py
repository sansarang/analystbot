#!/usr/bin/env python
"""[LE-4] 엔진 2 역사 백테스트 — 시장을 이기는가.

사용자 2026-09-22: "시장에 순응하면 안 되고 시장을 이기는 방법을 찾아야 한다."

🔴 목표는 결과가 아니라 `p_close - p_open`(시장의 이동량)이다.
   시장 확률을 그대로 내놓으면 예측 이동량이 0 이라 후보가 하나도 안 나온다 —
   구조상 복사가 불가능하다.

🔴 walk-forward 만. 학습 창 → 검증 창 앞에서 보정 → 뒤에서 측정.
⚠️ 입력은 전부 개장 시점에 알 수 있는 값이다. 마감가·결과는 입력에 없다.

  python -m tools.residual_backtest
  python -m tools.residual_backtest --div E0 --book Avg
"""
from __future__ import annotations

import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("residual_backtest")

DASH = "-"

_SQL = """
    SELECT m.id, m.div, m.season, m.match_date, m.home, m.away, m.ftr,
      max(CASE WHEN p.book=$1 AND p.phase='open'  AND p.side='home' THEN p.odds END) oh,
      max(CASE WHEN p.book=$1 AND p.phase='open'  AND p.side='draw' THEN p.odds END) od,
      max(CASE WHEN p.book=$1 AND p.phase='open'  AND p.side='away' THEN p.odds END) oa,
      max(CASE WHEN p.book=$1 AND p.phase='close' AND p.side='home' THEN p.odds END) ch,
      max(CASE WHEN p.book=$1 AND p.phase='close' AND p.side='draw' THEN p.odds END) cd,
      max(CASE WHEN p.book=$1 AND p.phase='close' AND p.side='away' THEN p.odds END) ca,
      max(CASE WHEN p.book='Max' AND p.phase='open' AND p.side='home' THEN p.odds END) mx
      FROM history_matches m
      JOIN history_prices p ON p.match_id = m.id
     WHERE p.market='h2h' AND m.ftr IN ('H','D','A')
       AND ($2::text IS NULL OR m.div = $2)
     GROUP BY m.id
     ORDER BY m.match_date
"""


def build_rows(recs) -> list[dict]:
    """DB 행 → 학습 행. 🔴 개장·마감이 둘 다 있어야 목표를 만들 수 있다."""
    from datetime import datetime, time, timezone

    from app.learning.prices import devig

    out = []
    for r in recs:
        o = devig({"home": r["oh"], "draw": r["od"], "away": r["oa"]})
        c = devig({"home": r["ch"], "draw": r["cd"], "away": r["ca"]})
        if not o or not c:
            continue
        try:
            over = 1 / float(r["oh"]) + 1 / float(r["od"]) + 1 / float(r["oa"])
        except (TypeError, ValueError, ZeroDivisionError):
            over = None
        # 북들의 불일치 — 최고가가 이 북보다 얼마나 후한가
        try:
            spread = float(r["mx"]) / float(r["oh"]) - 1.0
        except (TypeError, ValueError, ZeroDivisionError):
            spread = None
        out.append({
            "div": r["div"], "season": r["season"], "match_date": r["match_date"],
            "ts": datetime.combine(r["match_date"], time(0, 0), tzinfo=timezone.utc),
            "home": r["home"], "away": r["away"], "ftr": r["ftr"],
            "p_open": o["home"], "p_close": c["home"],
            # 🔴 기준선(i)·후보 판정이 보는 "시장"은 개장가다(결정 시점).
            "p_market": o["home"],
            "p_market_at_decision": o["home"],
            "price_at_decision": float(r["oh"]),
            "overround": round(over, 4) if over else None,
            "book_spread": round(spread, 4) if spread is not None else None,
            "result": ("win" if r["ftr"] == "H"
                       else ("loss" if r["ftr"] == "A" else "push")),
        })
    return out


def _fmt(v, n=4):
    return DASH if v is None else f"{v:.{n}f}"


def _line(tag, s):
    if not s or s.get("insufficient"):
        return f"    {tag:16s} n={(s or {}).get('n', 0):5d}  표본 부족"
    mono = s.get("monotone")
    mono_s = DASH if mono is None else ("단조" if mono else "X")
    return (f"    {tag:16s} n={s['n']:5d}  Brier {_fmt(s['brier'])}  "
            f"로그손실 {_fmt(s['log_loss'])}  적중 {_fmt(s['hit_rate'], 3)}  "
            f"CLV {_fmt(s['clv_mean'])}  보정 {mono_s}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="Avg")
    ap.add_argument("--div")
    ap.add_argument("--train-weeks", type=int, default=52)
    ap.add_argument("--valid-weeks", type=int, default=4)
    a = ap.parse_args()

    from app.db import get_pool
    from app.learning import baselines as B
    from app.learning import engine_residual as E
    from app.learning.features_soccer import running_elo
    from app.learning.split import by_league

    pool = await get_pool()
    recs = await pool.fetch(_SQL, a.book, a.div)
    rows = build_rows(recs)
    print(f"\n{'='*80}\nLE-4 backtest - book {a.book!r} - "
          f"train {a.train_weeks}w -> valid {a.valid_weeks}w"
          f"\n  DB {len(recs)} -> open+close {len(rows)}\n{'='*80}")
    if len(rows) < 200:
        print("  표본이 너무 얇다.")
        return

    overall = {}
    for div, sub in sorted(by_league(rows, league_key="div").items(),
                           key=lambda kv: str(kv[0])):
        sub = running_elo(sub)
        if len(sub) < 300:
            print(f"\n  {div}  n={len(sub)} - 표본 부족, 건너뜀")
            continue
        print(f"\n  ---- {div}  (경기 {len(sub)}) ----")
        base = B.score(sub)
        for n in base["_names"]:
            print(_line(f"기준선:{n}", base[n]))
        for target, tag in ((E.TARGET_RESIDUAL, "엔진2:잔차"),
                            (E.TARGET_RESULT, "비교군:결과")):
            got = E.run(sub, target=target, train_weeks=a.train_weeks,
                        valid_weeks=a.valid_weeks)
            s = got["summary"]
            print(_line(tag, s))
            if target == E.TARGET_RESIDUAL:
                cands = E.candidates(got["rows"])
                win = B.beats_market(s, base)
                mark = "OK" if win else ("NO" if win is False else "판단불가")
                print(f"    {'후보':16s} {len(cands):5d}건  ·  기준선(i) 격파 {mark}")
                overall[div] = (s, base, len(cands), win)

    print(f"\n{'='*80}\n[결론]")
    for div, (s, base, nc, win) in sorted(overall.items(),
                                          key=lambda kv: str(kv[0])):
        mk = base.get("market") or {}
        verdict = "엔진2 활성" if win else "엔진2 비활성 - 기준선(i)을 못 이긴다"
        print(f"  {str(div):5s}  엔진 Brier {_fmt(s.get('brier'))} vs "
              f"시장 {_fmt(mk.get('brier'))}  후보 {nc:4d}  ->  {verdict}")
    print("\n⚠️ 검증 창 밖 성적은 없다. 좋아 보이는 설정을 찾아 헤매면 그건")
    print("   검증 창을 학습에 쓰는 것이다(지시문 §1).")


if __name__ == "__main__":
    asyncio.run(main())
