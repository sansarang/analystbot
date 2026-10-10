"""🔴🔴 **§4 — 분 단위 경기 시뮬레이션**. 사용자 지시 2026-10-10(셋째).

> 기대 득점을 **시간대**(전반·후반, 가능하면 15분 구간)로 나눈다: 축1 폼·축2
> 상성·축3 시간대 프로필이 구간별 득점률을 정한다.
> **경기 상태 배율**: 앞서는 팀·뒤지는 팀의 득점률 변화(리드 유지력·추격력·동기
> 상태)를 적합해 넣는다.
> **90분을 분 단위로 시뮬레이션(또는 같은 구조의 해석 계산)** 해서 스코어 분포 →
> 승무패, 오버 1.5/2.5/3.5, **"선제골 팀이 이길 확률"** 까지.

🔴 **해석 계산을 쓴다**(무작위 시뮬레이션이 아니다) — 같은 입력이면 **같은 수**가
   나와야 한다(§5 재현 · 온도 0 과 같은 규율). ⚠️ 몬테카를로는 회차마다 수가
   흔들려 사용자가 되돌아볼 수가 없다.
🔴 상태 배율이 들어가므로 **분마다 상태별 확률을 들고 전진**한다(앞섬·동점·뒤짐
   × 점수 차). 그것이 *"선취 후 역전패"* 를 분포에 자연스럽게 넣는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴 §4 — 분 단위. 90분 + 추가시간을 한 칸으로 더 센다
MINUTES = 90
#: 🔴 분포가 다루는 최대 득점(그보다 많으면 한 칸에 모은다)
MAX_GOALS = 8


@dataclass
class Out:
    """🔴 §4 산출 — 스코어 분포에서 나온 수들."""

    #: `{(홈, 원정): 확률}`
    scores: dict = field(default_factory=dict)
    home: float = 0.0
    draw: float = 0.0
    away: float = 0.0
    #: `{"1.5": 확률, …}`
    over: dict = field(default_factory=dict)
    #: 🔴 §4 — **선제골 팀이 이길 확률**(그 경기에 골이 있을 때 기준)
    first_wins: float | None = None
    why: str = ""


def minute_rates(lam_home: float, lam_away: float, *,
                 late_home: float = 0.0, late_away: float = 0.0,
                 ) -> list[tuple[float, float]]:
    """🔴🔴 §4 — **분마다의 득점률**. `[(홈, 원정)] × 90`.

    `lam_*` 는 경기 전체 기대 득점이고 `late_*` 는 **61분 이후 배율**(T10 이 준다).
    🔴 61분 이후에 `late` 를 걸고, **경기 전체 합이 `lam` 을 넘지 않게** 앞 구간을
       줄여 맞춘다 — 그래야 λ 상한(±15%)이 뜻을 갖는다.
    ⚠️ 균일 분포로 시작한다(실제 축구는 후반이 조금 높다) — 🔴 그 분포를 적합하면
       여기 넣는다(`config/tactical_rules.yaml` 의 `buckets`).
    """
    out: list[tuple[float, float]] = []
    base_h, base_a = float(lam_home) / MINUTES, float(lam_away) / MINUTES
    # 🔴 61~90 분에 배율을 걸고 그만큼 전체를 되맞춘다(합 보존)
    def _row(mul: float, base: float, minute: int) -> float:
        return base * (1.0 + mul) if minute > 60 else base
    for m in range(1, MINUTES + 1):
        out.append((_row(late_home, base_h, m), _row(late_away, base_a, m)))
    for i, (mul, idx) in enumerate(((late_home, 0), (late_away, 1))):
        if not mul:
            continue
        tot = sum(r[idx] for r in out)
        want = (float(lam_home) if idx == 0 else float(lam_away))
        if tot > 0:
            scale = want / tot
            out = [(r[0] * (scale if idx == 0 else 1.0),
                    r[1] * (scale if idx == 1 else 1.0)) for r in out]
    return out


def run(lam_home: float, lam_away: float, *, late_home: float = 0.0,
        late_away: float = 0.0, lead_mul: dict | None = None) -> Out:
    """🔴🔴 §4 — **분 단위 전진으로 스코어 분포**를 만든다(해석 계산).

    `lead_mul` 은 **상태 배율**이다:
      `{"leading": 0.9, "trailing": 1.15}` — 앞서는 팀의 득점률 ×0.9,
      뒤지는 팀 ×1.15. ⚠️ 없으면 **1.0**(상태를 안 쓴다).

    🔴 상태를 들고 전진하므로 `first_wins`(선제골 팀이 이길 확률)가 **분포에서
       그냥 나온다** — 따로 세지 않는다.
    """
    mul = dict(lead_mul or {})
    lead = float(mul.get("leading") or 1.0)
    trail = float(mul.get("trailing") or 1.0)
    rates = minute_rates(lam_home, lam_away, late_home=late_home,
                         late_away=late_away)
    # 🔴 상태 = `(홈 득점, 원정 득점, 선제골이 누구였나)`
    #    `first` ∈ `0`(아직 없다) · `1`(홈) · `2`(원정)
    box: dict[tuple[int, int, int], float] = {(0, 0, 0): 1.0}
    for ph, pa in rates:
        nxt: dict[tuple[int, int, int], float] = {}
        for (h, a, first), p in box.items():
            if p <= 0.0:
                continue
            # 🔴 상태 배율 — 앞서는 쪽은 느려지고 뒤지는 쪽은 빨라진다
            mh = ph * (lead if h > a else (trail if h < a else 1.0))
            ma = pa * (lead if a > h else (trail if a < h else 1.0))
            mh, ma = min(mh, 0.5), min(ma, 0.5)   # ⚠️ 분당 확률은 1 을 못 넘는다
            none = (1.0 - mh) * (1.0 - ma)
            _put(nxt, (h, a, first), p * none)
            if h < MAX_GOALS:
                _put(nxt, (min(h + 1, MAX_GOALS), a, first or 1),
                     p * mh * (1.0 - ma))
            if a < MAX_GOALS:
                _put(nxt, (h, min(a + 1, MAX_GOALS), first or 2),
                     p * (1.0 - mh) * ma)
            if h < MAX_GOALS and a < MAX_GOALS:
                # 🔴 같은 분에 둘 다 — 아주 작지만 버리면 합이 1 이 안 된다
                _put(nxt, (min(h + 1, MAX_GOALS), min(a + 1, MAX_GOALS),
                           first or 1), p * mh * ma)
        box = nxt
    return _sum(box)


def _put(box: dict, key: tuple, p: float) -> None:
    if p > 0.0:
        box[key] = box.get(key, 0.0) + p


def _sum(box: dict) -> Out:
    """🔴 상태 표 → 스코어 분포·승무패·오버·선제골 팀 승률."""
    out = Out()
    scores: dict[tuple[int, int], float] = {}
    first_n = first_win = 0.0
    for (h, a, first), p in box.items():
        scores[(h, a)] = scores.get((h, a), 0.0) + p
        if first:
            first_n += p
            if (h > a and first == 1) or (a > h and first == 2):
                first_win += p
    tot = sum(scores.values()) or 1.0
    out.scores = {k: round(v / tot, 6) for k, v in sorted(scores.items())}
    out.home = round(sum(v for (h, a), v in scores.items() if h > a) / tot, 6)
    out.draw = round(sum(v for (h, a), v in scores.items() if h == a) / tot, 6)
    out.away = round(1.0 - out.home - out.draw, 6)
    out.over = {f"{x}": round(sum(v for (h, a), v in scores.items()
                                  if (h + a) > x) / tot, 4)
                for x in (0.5, 1.5, 2.5, 3.5, 4.5)}
    out.first_wins = (round(first_win / first_n, 4) if first_n > 0 else None)
    out.why = (f"분 단위 해석 계산 {MINUTES}분 · 상태 표 {len(box)}칸 · "
               f"합 {tot:.4f}")
    return out
