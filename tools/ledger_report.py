#!/usr/bin/env python
"""[LE-1a] 결정 원장 지표 표. **읽기 전용 · 표만 낸다.**

🔴 **적중률로 판단하지 않는다.** 표에는 싣지만 결정 기준은 Brier·CLV 다
   (지시문 §1). 실측 2026-09-22: 확신 '하'(57.7%)가 '중'(53.2%)보다 잘 맞아
   적중률·확신 표시가 순서를 못 가린다.

🔴 **30건 미만 셀은 숫자를 내지 않는다** — "표본 부족"만 찍는다. 문턱의 원본은
   `config/learning.yaml` 의 `learning.min_samples` 다.

  python -m tools.ledger_report                 # 전부
  python -m tools.ledger_report --engine bot_v14
  python -m tools.ledger_report --backfill      # pick_ledger 소급 적재 후 표
"""
from __future__ import annotations

import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ledger_report")


def _fmt(v, n=4):
    return "—" if v is None else (f"{v:.{n}f}" if isinstance(v, float) else str(v))


def _row(label: str, s: dict) -> str:
    if s.get("insufficient"):
        return (f"  {label:28s} n={s['n']:4d}  "
                f"**표본 부족** (하한 {s['min_samples']})"
                + (f" · 제외 {s['dropped']}" if s.get("dropped") else ""))
    mono = s.get("monotone")
    mono_s = "—" if mono is None else ("단조" if mono else "🔴 깨짐")
    return (f"  {label:28s} n={s['n']:4d}  Brier {_fmt(s['brier'])}  "
            f"로그손실 {_fmt(s['log_loss'])}  적중 {_fmt(s['hit_rate'],3)}  "
            f"CLV {_fmt(s['clv_mean'])}(n={s['clv_n']})  "
            f"ROI {_fmt(s['roi_mean'])}(n={s['roi_n']})  보정 {mono_s}")


def _curve(s: dict) -> list[str]:
    if s.get("insufficient"):
        return []
    out = ["      보정 곡선 (분위: n · 평균확률 → 실측빈도)"]
    for c in s.get("calibration") or []:
        if not c["n"]:
            continue
        out.append(f"        {c['lo']:.1f}~{c['hi']:.1f}  n={c['n']:4d}  "
                   f"{_fmt(c['mean_p'],3)} → {_fmt(c['freq'],3)}")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine")
    ap.add_argument("--sport")
    ap.add_argument("--backfill", action="store_true",
                    help="pick_ledger 를 decision_ledger 로 소급 적재한 뒤 표를 낸다")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    from app.db import get_pool
    from app.learning import decisions as D
    from app.learning import metrics as M

    pool = await get_pool()
    if a.backfill:
        got = await D.backfill_from_picks(pool, limit=a.limit)
        print(f"소급 적재: {got}")

    rows = await D.load(pool, engine=a.engine, sport=a.sport)
    print(f"\n{'='*78}\n결정 원장 — 행 {len(rows)}개"
          f"{f' · 엔진 {a.engine}' if a.engine else ''}\n{'='*78}")
    if not rows:
        print("  행이 없다. `--backfill` 로 적재하거나 엔진이 후보를 낼 때까지 비어 있다.")
        return

    print("\n[전체]")
    tot = M.summarize(rows)
    print(_row("all", tot))
    for ln in _curve(tot):
        print(ln)

    for keys, title in ((("engine",), "엔진별"), (("sport",), "종목별"),
                        (("engine", "sport"), "엔진×종목"),
                        (("market",), "마켓별")):
        print(f"\n[{title}]")
        for k, s in M.group_by(rows, keys).items():
            print(_row(" / ".join(str(x) for x in k), s))

    print(f"\n⚠️ 적중률은 보고용이다 — 결정 기준은 Brier·CLV 다(지시문 §1).")
    print(f"⚠️ 30건 미만 셀은 숫자를 내지 않는다(하한 {M.min_samples()}).")


if __name__ == "__main__":
    asyncio.run(main())
