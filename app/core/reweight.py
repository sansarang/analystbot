"""🔴🔴 **시나리오 무게를 우리 확률에 묶는다** — 사용자 지시 2026-10-07(재가중).

> 각 시나리오 스코어를 결과(홈승/무/원정승)로 나누고, 같은 결과 안에서는 기존 무게
> 비율로 나누되, **결과별 총량은 OurProb(우리 열)로 맞춘다.** 결과에 갈래가 하나도
> 없으면 그 결과용 보강 갈래를 넣는다. 이 재가중된 무게를 생존율·보드 대입·
> 양상(shape)·총골 분포·예상 스코어 **전부에** 쓴다(한 곳에서 계산).

══════════════════════════════════════════════════════════════════
🔴 왜 — 카드가 **두 말을 했다**(실측 2026-10-07 멕시코–칠레)
══════════════════════════════════════════════════════════════════

```
확률 열   Mexico 73% · 무 19% · Chile 8%
시나리오  C(원정승 2.4) · A(개방 2.1) …  → 양상·논평·예상 스코어가 **칠레 한 골 차 승**
핸디 Mexico -1.5 생존 0.1935   ← 73% 짜리 팀의 수가 아니다
```

⚠️ 두 수는 서로 **다른 출발점**에서 왔다: 우리 열은 ①②에서 출발해 변수로 움직인
   것이고(§6차 ①), 시나리오 무게는 **근거 변수 유형별 최댓값 합**이다. 🔴 그래서
   같은 카드 안에서 어긋났다.
🔴 이제 **우리 열이 총량을 정하고**, 시나리오는 그 안에서 **모양**(어떤 스코어로
   그렇게 되나)을 말한다. ⚠️ 우리 열을 시나리오로 다시 계산하지 않는다 — 한 방향이다.
"""
from __future__ import annotations

import logging

from app.core.schema import HypoSet, MatchRef, ProbTriple, Scenario
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 결과 세 칸 — `rules.direction_of` 가 돌려주는 글자 그대로
SIDES = ("home", "draw", "away")


def _forms() -> dict:
    """🔴 보강 스코어 표 — `config/scenario_required.yaml` 하나가 원본이다."""
    from app import rules
    return dict((rules._load("config/scenario_required.yaml")
                 .get("soccer_forms") or {}))


def cover_scores(side: str) -> list[tuple[int, int]]:
    """🔴 그 결과를 덮는 스코어 — 무승부는 **기존 필수형 표**를 그대로 쓴다(#1)."""
    box = _forms()
    if side == "draw":
        said = (box.get("무승부") or {}).get("scores") or []
    else:
        said = (box.get("결과_덮기") or {}).get(side) or []
    out: list[tuple[int, int]] = []
    for raw in said:
        bits = str(raw).split("-")
        if len(bits) == 2 and bits[0].strip().isdigit() \
                and bits[1].strip().isdigit():
            out.append((int(bits[0]), int(bits[1])))
    return out


def side_of(home: int, away: int) -> str:
    """🔴 스코어 → 결과. ⚠️ 판정은 `rules.direction_of` **하나**다(사본 금지)."""
    from app import rules
    return str(rules.direction_of([f"{home}-{away}"]) or "")


def of(hypo: HypoSet | None, ours: ProbTriple | None, *, ref: MatchRef,
       state: RunState) -> HypoSet | None:
    """🔴🔴 재가중한 `HypoSet` — **결과별 합이 우리 열과 같아진다.**

    🔴 돌려주는 것은 **새 `HypoSet`** 이고, 하류(s7 생존·보드·양상·논평)는 그것만
       본다. ⚠️ 우리 열이 없으면(기준도 시나리오도 없으면) **그대로 돌려준다** —
       없는 수로 맞추지 않는다.
    """
    if hypo is None or not (hypo.scenarios or []):
        return hypo
    if ours is None:
        state.note("재가중 건너뜀 — **우리 열이 없다**(맞출 총량이 없다)")
        return hypo
    rows = list(hypo.scenarios)
    before = round(sum(float(s.strength or 0.0) for s in rows), 4)
    # ── ① 스코어 단위로 쪼갠다(섞인 스코어의 무게를 버리지 않는다)
    share: dict[str, float] = {k: 0.0 for k in SIDES}
    for sc in rows:
        w = float(sc.strength or 0.0)
        pairs = list(sc.outcomes or [])
        if w <= 0 or not pairs:
            continue
        for h, a in pairs:
            got = side_of(h, a)
            if got in share:
                share[got] += w / len(pairs)
    # ── ② 빈 결과를 덮는다 — **기존 필수형 스코어 재사용**
    want = {k: float(getattr(ours, k, 0.0) or 0.0) for k in SIDES}
    added: list[str] = []
    for side in SIDES:
        if share[side] > 0 or want[side] <= 0:
            continue
        spots = [p for p in cover_scores(side) if _free(p, rows)]
        if not spots:
            state.note(f"재가중 — `{side}` 갈래가 없는데 **덮을 스코어도 없다**"
                       f"(표에 적힌 스코어가 이미 다른 갈래에 있다)")
            continue
        rows.append(_cover(side, spots, rows, ours))
        share[side] = float(rows[-1].strength or 0.0)
        added.append(f"{side}({'·'.join(f'{h}-{a}' for h, a in spots)})")
    if added:
        state.note(f"재가중 — **빈 결과를 덮었다** {added}(근거 없음 → 바닥값)")
    # ── ③ 결과마다 비례 상수 — 같은 결과 안의 비율은 **그대로**
    live = [k for k in SIDES if share[k] > 0]
    if not live:
        state.note("재가중 건너뜀 — 시나리오 무게가 전부 0 이다")
        return hypo
    tot_want = sum(want[k] for k in live) or 1.0
    factor = {k: (want[k] / tot_want) * before / share[k] for k in live}
    out: list[Scenario] = []
    for sc in rows:
        w = float(sc.strength or 0.0)
        pairs = list(sc.outcomes or [])
        if w <= 0 or not pairs:
            out.append(sc)
            continue
        got = 0.0
        for h, a in pairs:
            side = side_of(h, a)
            got += (w / len(pairs)) * factor.get(side, 0.0)
        out.append(sc.model_copy(update={"strength": round(max(got, 0.0), 4)}))
    said = " · ".join(f"{k} {share[k]:.2f}→{want[k] / tot_want * before:.2f}"
                      f"({want[k] / tot_want:.0%})" for k in SIDES
                      if k in factor)
    state.note(f"재가중 ✅ 결과별 합을 **우리 열에 맞췄다** — {said} "
               f"(총량 {before:.2f} 유지 · 갈래 {len(out)}개)")
    return hypo.model_copy(update={"scenarios": out})


def _free(spot: tuple[int, int], rows: list[Scenario]) -> bool:
    """🔴 그 스코어가 아직 **아무 갈래에도 없나**(같은 스코어를 두 번 넣지 않는다)."""
    have = {(h, a) for sc in rows for h, a in (sc.outcomes or [])}
    return spot not in have


def _cover(side: str, spots: list[tuple[int, int]], rows: list[Scenario],
           ours: ProbTriple) -> Scenario:
    """🔴 그 결과를 덮는 **보강 갈래 하나**. ⚠️ 근거가 없으니 **바닥값**이다(①)."""
    from app.core.stages.s6_hypo import _next_id
    from app.survive import WEIGHT_FLOOR
    kind = {"home": "home_win", "draw": "draw", "away": "away_win"}[side]
    pct = float(getattr(ours, side, 0.0) or 0.0)
    return Scenario(
        id=_next_id(rows), outcomes=spots[:2], driver_vars=[],
        type=kind, added_by="code", strength=float(WEIGHT_FLOOR),
        mechanism=(f"🔴 결과 덮기({side}) — 우리 열이 그 결과에 **{pct:.0%}** 를 "
                   f"주는데 그 결과를 그린 갈래가 **하나도 없었다**. ⚠️ 근거 변수가 "
                   f"없어 **바닥값**이고, 모양은 필수형 표의 스코어다"))
