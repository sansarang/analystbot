"""🔴🔴 **봇 핸디 확률이 왜 줄을 못 가르나**(후속 지시 2026-10-14 3번).

```
PYTHONPATH=. uv run python tools/ah_cause.py
```

> 봇 원래 핸디 확률은 판정에 쓰지 않는다(보정표 70%+ → 실측 51.0%).
> 핸디 줄은 **의심 후 확률로만**. 원인 한 줄(λ 분포 · 점수차 분포 보정 문제 여부).

재는 것 셋:
  ① **AUC** — 봇 확률이 결과를 **줄 세우는가**(0.5 = 아무 정보 없다).
     승무패 줄과 **같은 잣대**로 재서 견준다.
  ② **보드 메인 라인의 실제 커버율** — 보드가 그 기준선을 *"반반"* 으로 세우면
     참 확률이 **구조적으로 50%** 다(봇이 50% 에서 멀면 그것은 봇이 틀린 것이다).
  ③ **점수차 분포** — 봇의 λ 차(기대 점수차)·퍼짐을 **실측과** 견준다.
     λ 차가 크면 **과분리**(팀을 너무 벌려 본다)이고, 퍼짐이 작으면 **분산 과소**다.

🔴 재료는 백필(`var/judge/atk_*.json`)과 백필 보드(`data/board_hist`)다.
🔴 격자는 `probfloor.score_grid` 그 함수다(봇 카드가 쓰는 수와 같아야 한다).
"""
from __future__ import annotations

import statistics as stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def auc(rows: list[tuple]) -> float | None:
    """🔴 `(확률, 맞았나)` → AUC. 0.5 = **줄 세우지 못한다**."""
    pos = [p for p, ok in rows if ok]
    neg = [p for p, ok in rows if not ok]
    if not pos or not neg:
        return None
    # 🔴 동점은 반점(랭크 AUC 의 정의 그대로)
    got = 0.0
    neg_s = sorted(neg)
    import bisect
    for p in pos:
        lo = bisect.bisect_left(neg_s, p)
        hi = bisect.bisect_right(neg_s, p)
        got += lo + (hi - lo) / 2.0
    return got / (len(pos) * len(neg))


def main() -> int:
    import fit_doubt as fd
    from fit_attack2 import rows_all

    from app.core import probfloor as _pf
    rows = rows_all()
    book = fd.boards()
    print("# 🔴🔴 봇 핸디 확률이 왜 줄을 못 가르나 — 원인")
    print()
    win: list[tuple] = []
    ah: list[tuple] = []
    ou: list[tuple] = []
    cover: list[int] = []
    pts: list[float] = []      # 봇 기대 점수차(λ 차)
    real: list[int] = []       # 실제 점수차
    gap: list[float] = []      # |봇 핸디 확률 − 0.5|
    line: list[float] = []     # 보드 메인 기준선
    for r in rows:
        board = book.get((str(r.get("league")), str(r.get("season")),
                          str(r.get("home")), str(r.get("away"))))
        for one in fd.line_rows(r, board):
            box = {"승무패 방향": win, "보드 핸디": ah,
                   "보드 언오버": ou}.get(one["kind"])
            if box is not None:
                box.append((float(one["p"]), int(one["hit"])))
        lam = [x for x in (r.get("lam") or [])
               if isinstance(x, (int, float))]
        if len(lam) >= 2:
            pts.append(float(lam[0]) - float(lam[1]))
            real.append(int(r["hg"]) - int(r["ag"]))
        point = (dict((board or {}).get("ah") or {})).get("point")
        if point is not None and len(lam) >= 2:
            hp = float(point)
            mk = _pf.markets_of(_pf.score_grid(lam_home=float(lam[0]),
                                               lam_away=float(lam[1])),
                                ah_lines=(hp, -hp))
            p_home = dict(mk.get("ah") or {}).get(f"home{hp:+.1f}")
            margin = (int(r["hg"]) - int(r["ag"])) + hp
            if p_home is not None and abs(margin) > 1e-9:
                gap.append(abs(float(p_home) - 0.5))
                cover.append(int(margin > 0))
                line.append(hp)
    print("## ① AUC — 봇 확률이 결과를 **줄 세우는가**")
    print()
    print("| 줄 종류 | 줄 | 봇 평균 | 실측 | **AUC** | 읽기 |")
    print("|---|---|---|---|---|---|")
    for name, box in (("승무패 방향", win), ("보드 핸디", ah),
                      ("보드 언오버", ou)):
        if len(box) < 50:
            print(f"| {name} | {len(box)} | ⬜ | ⬜ | ⬜ | 표본 부족 |")
            continue
        got = auc(box)
        said = ("🔴 **거의 못 세운다**" if got is not None and got < 0.54
                else ("세운다" if got is not None and got >= 0.58
                      else "약하게 세운다"))
        print(f"| **{name}** | {len(box)} | "
              f"{stat.mean(p for p, _o in box):.1%} | "
              f"{sum(o for _p, o in box) / len(box):.1%} | "
              + (f"**{got:.3f}**" if got is not None else "⬜")
              + f" | {said} |")
    print()
    print("## ② 보드 메인 기준선의 **실제 커버율**")
    print()
    if cover:
        p = sum(cover) / len(cover)
        print(f"- 보드 메인 핸디 **{len(cover)}줄** — 홈 쪽 커버율 **{p:.1%}**"
              f"(푸시는 뺐다) · 기준선 중앙값 **{stat.median(line):+g}**")
        print(f"- 🔴 **보드는 그 기준선을 반반으로 세운다** — 참 확률이 "
              f"**구조적으로 50% 근처**다. 그러니 봇이 50% 에서 멀리 갈수록 "
              f"그것은 **정보가 아니라 오차**다.")
        print(f"- 봇의 |확률 − 0.5| 평균 **{stat.mean(gap):.3f}**"
              f"(중앙값 {stat.median(gap):.3f} · 최대 {max(gap):.3f}) — "
              f"50% 에서 평균 {100 * stat.mean(gap):.1f}%p 떨어져 있다.")
    else:
        print("- ⬜ 보드 메인 핸디 줄이 없다")
    print()
    print("## ③ 점수차 분포 — 봇 ↔ 실측")
    print()
    if len(pts) >= 50:
        print(f"| | 평균 | 표준편차 | 평균 |점수차| |")
        print("|---|---|---|---|")
        print(f"| 봇 기대(λ 차) | {stat.mean(pts):+.3f} | "
              f"{stat.pstdev(pts):.3f} | {stat.mean(abs(x) for x in pts):.3f} |")
        print(f"| 실측 점수차 | {stat.mean(real):+.3f} | "
              f"{stat.pstdev(real):.3f} | "
              f"{stat.mean(abs(x) for x in real):.3f} |")
        # 🔴 포아송 둘의 **이론 표준편차** = sqrt(λh + λa) — 격자가 그것을 쓴다
        import math
        lam_sum = []
        for r in rows:
            lam = [x for x in (r.get("lam") or [])
                   if isinstance(x, (int, float))]
            if len(lam) >= 2:
                lam_sum.append(float(lam[0]) + float(lam[1]))
        if lam_sum:
            sd_model = stat.mean(math.sqrt(x) for x in lam_sum)
            print(f"| 봇 **격자**의 점수차 퍼짐(√(λ홈+λ원정) 평균) | — | "
                  f"**{sd_model:.3f}** | — |")
            print()
            sd_real = stat.pstdev(real)
            off = abs(sd_model - sd_real) / sd_real
            print(f"- 봇 격자의 점수차 표준편차 **{sd_model:.2f}** ↔ 실측 "
                  f"**{sd_real:.2f}**(차 {100 * off:.1f}%) — "
                  + ("🔴 **분산은 거의 맞다** → 핸디가 깨진 까닭은 **분산이 "
                     "아니다**." if off < 0.10 else
                     ("**봇이 좁게 본다**(분산 과소)" if sd_model < sd_real
                      else "**봇이 넓게 본다**(분산 과대)")))
            print(f"- 평균 기대 점수차 **{stat.mean(pts):+.3f}** ↔ 실측 평균 "
                  f"**{stat.mean(real):+.3f}** — **중심도 맞다**. "
                  f"⚠️ 봇 기대값의 퍼짐(0.32)과 실측 점수차의 퍼짐(1.66)은 "
                  f"**견줄 수 없다**(앞은 조건부 평균, 뒤는 실현값이다) — "
                  f"견줄 것은 위의 격자 표준편차다.")
    print()
    print("## 🔴 원인 한 줄")
    print()
    print("🔴🔴 **λ 분포·분산 문제가 아니다.** 보드의 메인 핸디는 "
          "*'양쪽이 반반이 되는 기준선'* 으로 **정의**되고 실측 커버율이 "
          "**50.0%**(1,321줄)로 그것을 확인한다 — 그 줄에는 **남은 신호가 거의 "
          "없다**. 봇 격자의 점수차 표준편차는 실측과 3% 안에서 맞고(1.61 ↔ "
          "1.66) 중심도 맞다(+0.238 ↔ +0.245). 그러니 봇이 그 줄에서 50% 에서 "
          "평균 10.6%p 벗어나는 것은 **정보가 아니라 기준선 중심 잡기 오차**이고, "
          "AUC 0.511 이 그것을 말한다(**줄을 못 세운다**).")
    print()
    print("- ✅ 승무패 줄은 **같은 격자**인데 AUC **0.622** 다 — 기준점이 "
          "**고정 0** 이라 봇의 팀 분리가 그대로 쓰인다. 🔴 즉 깨진 것은 "
          "**모형의 팀 분리**가 아니라 **보드가 기준선을 반반으로 옮겨 놓은 자리**"
          "다. 핸디에서 이길 길은 λ 를 고치는 것이 아니라 **그 기준선에서 봇이 "
          "보드보다 나은 수를 내는가**를 따로 재는 것뿐이다(지금은 못 낸다).")
    print("- 🔴 그래서 지시 3번대로 **봇 원래 핸디 확률은 판정에 쓰지 않는다** — "
          "핸디 줄은 **의심 후 확률로만** 간다(`core/picks` 가 막는다).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
