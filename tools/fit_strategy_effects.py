"""🔴🔴 **전략 이동량을 과거 자료로 적합한다** — 사용자 지시 2026-10-10(둘째) §3-2.

> 이동량: **과거 자료로 적합** — *"그 리그에서 평소 대비 ΔA가 −10% 이상인 명단을
> 낸 경기의 득점·결과 변화"*, *"3백 전환 원정 경기의 실점·무승부율"* 등.
> 유형별 **표본·계수·검증 수치**를 `config/strategy_effects.yaml` 에.
> **적합 못 한 유형은 임시값 + 카드 표시.**

```
PYTHONPATH=. python tools/fit_strategy_effects.py --league league:KL1
PYTHONPATH=. python tools/fit_strategy_effects.py --check     # 표본만 센다
```

══════════════════════════════════════════════════════════════════
🔴🔴 **지금 돌리면 "표본이 없다"고 적지 않고 멈춘다**
══════════════════════════════════════════════════════════════════

적합에 필요한 것은 경기마다 **확정 XI + 평소 XI + 결과**다. 실측 2026-10-10 —
우리가 받는 통로:

| 무엇 | 어디까지 |
|---|---|
| 그 경기 확정 XI | 경기 페이지 — **한 경기씩** |
| 과거 경기 XI | `facts.past_xi` — 최대 **5경기**(`s2_facts.FOLLOW_CAP`) |
| 리그 전체의 경기별 XI 이력 | 🔴 **없다** |

🔴 그래서 *"그 리그에서 ΔA −10% 명단을 낸 경기"* 를 셀 표본이 **0건**이다.
⚠️ 그 상태에서 수를 적으면 그것은 **적합이 아니라 지어낸 것**이다(금지 둘째 줄:
   *"적합 없는 계수를 표시 없이 사용"*). 🔴 그래서 **적지 않는다.**

🔴 **무엇이 생기면 적합할 수 있나**(이 도구가 그때 그대로 돈다):
  리그 경기 목록 × 각 경기의 확정 XI — fotmob 경기 페이지를 리그 일정만큼 열면
  된다(robots 허용 경로다). ⚠️ 한 시즌이 300~400경기이므로 그 수집은 **사용자가
  예산을 정한 뒤** 돈다(그래서 이 도구가 스스로 긁지 않는다).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: 🔴 적합에 필요한 최소 표본 — 그보다 적으면 **적지 않는다**
MIN_N = 30


async def sample_of(net, league_id: object) -> tuple[int, str]:
    """🔴 그 리그에서 **적합에 쓸 수 있는 경기 수**를 센다. `(수, 사유)`.

    🔴 조건: 끝난 경기이고 **그 경기의 확정 XI 를 우리가 들고 있어야** 한다.
    ⚠️ 지금은 확정 XI 를 **쌓아 두는 자리가 없다** — 그래서 늘 0 이고, 그 사실을
       사유로 돌려준다(#3 조용한 0 금지).
    """
    from app.collect import fotmob as fm
    rows = await fm.league_season_rows(net, league_id)
    said = (f"끝난 경기 {len(rows)}건 — 🔴 그 경기들의 **확정 XI 를 쌓아 둔 자리가 "
            f"없다**(경기 페이지를 다시 열어야 한다 · 예산은 사용자가 정한다)")
    return 0, said


async def main(argv: list[str]) -> int:
    from app import net as _net_mod
    from app.core import autoleague, competition
    want = ""
    if "--league" in argv:
        want = argv[argv.index("--league") + 1]
    net = _net_mod.Net()
    keys = [want] if want else [*competition.rows(), *autoleague.registered()]
    print(f"볼 리그 {len(keys)}개 · 최소 표본 {MIN_N}경기")
    total = 0
    for key in keys:
        lid = None
        row = competition.row_of(str(key)) or {}
        ids = list((row.get("sources") or {}).get("fotmob_ids") or [])
        if ids:
            lid = ids[0]
        elif str(key).startswith("league:fotmob"):
            lid = str(key).rsplit("fotmob", 1)[-1]
        if lid is None:
            print(f"  {key}: 🔴 fotmob 리그 id 를 모른다 — 건너뛴다")
            continue
        n, why = await sample_of(net, lid)
        total += n
        print(f"  {key}(fotmob {lid}): 표본 **{n}건** — {why}")
    print(f"\n합계 표본 {total}건")
    if total < MIN_N:
        print(f"🔴 **적지 않는다** — 표본이 {MIN_N}건 미만이다.\n"
              f"   `config/strategy_effects.yaml` 의 수는 그대로 **임시값**이고,\n"
              f"   카드가 그 사실을 적는다(§3-2 마지막 줄).")
        return 1
    print("⚠️ 표본이 생겼다 — 적합 식을 여기 넣고 `fit` 칸을 채운다"
          "(실행 중 적합 금지 · 이 도구가 파일을 쓴다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
