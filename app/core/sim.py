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
import math
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
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **가설 검증이 읽는 칸들** — 순서 재편 지시서(2026-10-10 다섯째) §3
    # ══════════════════════════════════════════════════════════════
    #
    #  > 분 단위 … 스코어 분포 → 승무패, 오버, **시간대 득점**, **선제골 후 결과**,
    #  > **무득점 확률**, **기대득점**.
    #
    #  🔴 전부 **같은 분포**에서 나온다(새 모델이 아니다 · 계수를 더하지 않는다).
    #: 🔴 팀별 **기대 득점**(분포의 평균) — `{"home": x, "away": y}`
    xg: dict = field(default_factory=dict)
    #: 🔴 팀별 **무득점 확률**
    no_goal: dict = field(default_factory=dict)
    #: 🔴 팀별 **구간 기대 득점** — `{"home": {"0-30": x, …}, …}`
    by_bucket: dict = field(default_factory=dict)
    #: 🔴 팀별 **선제골을 넣었을 때 그 팀이 이길 확률**(조건부)
    first_then_win: dict = field(default_factory=dict)
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


def bench_shift(rates: list[tuple[float, float]], mul: float
                ) -> list[tuple[float, float]]:
    """🔴🔴 §8(c) — **60분 이후** 득점률을 팀 사이로 옮긴다. 경기 전체 λ 보존.

    🔴 `mul = exp(d1·benchΔ)` — 홈 쪽에 곱하고 원정 쪽에 나눈다(`BENCH_FROM` 뒤).
    🔴 그 뒤 **두 팀 합**을 원래 합으로 되맞춘다(지시의 ±2% 안에 들어온다 —
       정확히 보존하므로 0% 다). ⚠️ 팀별 λ 는 **일부러** 바뀐다(그래야 효과가 있다).
    """
    want = sum(h + a for h, a in rates)
    out = [(h * mul, a / mul) if i + 1 > BENCH_FROM else (h, a)
           for i, (h, a) in enumerate(rates)]
    tot = sum(h + a for h, a in out)
    if tot <= 0:
        return rates
    scale = want / tot
    return [(h * scale, a * scale) for h, a in out]


#: 🔴 상태 이름 — **표의 열쇠**다(`staterates` 가 같은 글자를 쓴다)
STATES: tuple[str, ...] = ("lead", "level", "trail")

#: 🔴🔴 **주변분포 보정 상한**(지시서 2026-10-12 [2c]) — 팀 기대 득점이 λ 에서
#   이 비율 안에 들어야 한다. ⚠️ 못 맞추면 **그 사실을 사유로** 남긴다(#3).
NORM_TOL = 0.02
#: 🔴 되맞추는 횟수 상한 — 몇 번 돌려도 못 맞추면 멈추고 적는다
NORM_TRY = 6


def _state_of(mine: int, theirs: int) -> str:
    """🔴 그 분의 **상태** — 앞섬·동점·뒤짐."""
    return "lead" if mine > theirs else ("trail" if mine < theirs else "level")


def _mul_of(table: dict, side: str, mine: int, theirs: int) -> float:
    """🔴🔴 [2c] — 그 팀의 **그 상태 득점률 배율**. 표가 없으면 1.0.

    ⚠️ **`against`(실점률)는 여기서 곱하지 않는다** — 득점 하나에 공격 쪽 `for`
       와 상대 수비 쪽 `against` 를 함께 곱하면 **같은 효과가 두 번** 들어간다.
       🔴 지시서 [2c] 는 *"λ분당 × 그 상태 배율"* 하나다. `against` 는 카드·축3
       근거(관찰)로만 쓴다(그 자리는 `strategy.TeamRead.state_mult` 다).
    """
    box = dict(dict(table or {}).get(side) or {})
    one = dict(box.get(_state_of(mine, theirs)) or {})
    got = one.get("for")
    return float(got) if isinstance(got, (int, float)) and got > 0 else 1.0


def _advance(rates: list, table: dict, *, scale_h: float = 1.0,
             scale_a: float = 1.0):
    """🔴 분 단위 전진 — **팀별 상태 배율**을 걸고 분포와 구간 기대 득점을 만든다.

    `scale_*` 는 **주변분포 보정**(S2)이 쓰는 되맞춤 계수다(기본 1.0).
    """
    box: dict[tuple[int, int, int], float] = {(0, 0, 0): 1.0}
    want = _buckets()
    acc = {"home": {k: 0.0 for k, _lo, _hi in want},
           "away": {k: 0.0 for k, _lo, _hi in want}}
    minute = 0
    for ph, pa in rates:
        minute += 1
        key = _bucket_key(want, minute)
        nxt: dict[tuple[int, int, int], float] = {}
        for (h, a, first), p in box.items():
            if p <= 0.0:
                continue
            mh = min(ph * scale_h * _mul_of(table, "home", h, a), 0.5)
            ma = min(pa * scale_a * _mul_of(table, "away", a, h), 0.5)
            acc["home"][key] += p * mh
            acc["away"][key] += p * ma
            none = (1.0 - mh) * (1.0 - ma)
            _put(nxt, (h, a, first), p * none)
            if h < MAX_GOALS:
                _put(nxt, (min(h + 1, MAX_GOALS), a, first or 1),
                     p * mh * (1.0 - ma))
            if a < MAX_GOALS:
                _put(nxt, (h, min(a + 1, MAX_GOALS), first or 2),
                     p * (1.0 - mh) * ma)
            if h < MAX_GOALS and a < MAX_GOALS:
                _put(nxt, (min(h + 1, MAX_GOALS), min(a + 1, MAX_GOALS),
                           first or 1), p * mh * ma)
        box = nxt
    return box, acc


def _run_with_table(rates: list, table: dict, lam_home: float,
                    lam_away: float) -> Out:
    """🔴🔴 [2c] 상태 배율 판 — **주변분포를 λ 로 되맞춘다**(S2 · ±2%).

    🔴 왜 되맞추나: 뒤진 팀 배율이 1 보다 크므로 그냥 걸면 **총 기대 득점이
       올라간다**. 그러면 λ(축이 만든 수)가 조용히 바뀐다 — 그것은 상태 배율이
       아니라 **다른 λ** 다.
    ⚠️ `NORM_TRY` 번 안에 못 맞추면 **멈추고 그 사실을 남긴다**(지어내지 않는다).
    """
    scale_h = scale_a = 1.0
    box, acc = _advance(rates, table)
    for _ in range(NORM_TRY):
        got_h = sum(acc["home"].values())
        got_a = sum(acc["away"].values())
        off_h = abs(got_h - lam_home) / lam_home if lam_home else 0.0
        off_a = abs(got_a - lam_away) / lam_away if lam_away else 0.0
        if off_h <= NORM_TOL and off_a <= NORM_TOL:
            break
        if got_h > 0:
            scale_h *= float(lam_home) / got_h
        if got_a > 0:
            scale_a *= float(lam_away) / got_a
        box, acc = _advance(rates, table, scale_h=scale_h, scale_a=scale_a)
    return _sum(box, buckets=acc)


#: 🔴🔴 **벤치 배율이 걸리는 분**(지시서 2026-10-12(둘째) §8 · 계약 C8-2) —
#  교체는 그 뒤에 들어온다. ⚠️ 이 수를 두 곳에 적지 않는다.
BENCH_FROM = 60


def run(lam_home: float, lam_away: float, *, late_home: float = 0.0,
        late_away: float = 0.0, lead_mul: dict | None = None,
        state_mult: dict | None = None, bench_d: float = 0.0,
        bench_coef: float = 0.0) -> Out:
    """🔴🔴 §4 — **분 단위 전진으로 스코어 분포**를 만든다(해석 계산).

    `lead_mul` 은 **상태 배율**이다:
      `{"leading": 0.9, "trailing": 1.15}` — 앞서는 팀의 득점률 ×0.9,
      뒤지는 팀 ×1.15. ⚠️ 없으면 **1.0**(상태를 안 쓴다).

    🔴 상태를 들고 전진하므로 `first_wins`(선제골 팀이 이길 확률)가 **분포에서
       그냥 나온다** — 따로 세지 않는다.
    """
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **상태 배율은 한 표다 — 두 번 곱하지 않는다**(지시서 [2c] · S1)
    # ══════════════════════════════════════════════════════════════
    #
    #  🔴 실측 표(`state_mult`)가 오면 **그것만** 쓴다 — T11 임시 배율
    #     (`lead_mul` 의 `leading`·`trailing`)은 같은 효과이므로 **끈다**.
    #  ⚠️ 표가 없으면 T11 이 그대로 돈다(퇴로를 끊지 않는다).
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **§8(c) 벤치 강도 — 60분 이후에만**(계약 C8-2)
    # ══════════════════════════════════════════════════════════════
    #
    #  > `λ_60+ ×= exp(±d1·benchΔ)` · 정규화로 경기 전체 λ **±2%**.
    #
    #  🔴 길은 **`late_*` 와 같은 길**이다(사본 금지) — 그 함수가 이미 *"61분
    #     이후에 걸고 전체 합을 되맞춘다"* 를 한다. 그래서 전체 λ 가 보존된다.
    #  ⚠️ `bench_coef`(d1)는 **백필이 적합한 수**다 — 없으면 0 이고 아무 일도
    #     일어나지 않는다(손값 금지).
    #  🔴🔴 **실측으로 배운 것 2026-10-12**: 벤치 배율을 `late_*` 처럼 걸고 **팀별
    #     λ 를 되맞추면 효과가 정확히 0 이 된다** — 포아송 합의 분포는 **적분에만**
    #     달려 있어서 분포 모양을 바꿔도 승무패가 한 치도 안 움직인다(계약이 그것을
    #     잡았다: 0.41563 != 0.41563).
    #  🔴 그래서 **경기 전체 λ**(두 팀 합)를 지키고 **팀 사이로 옮긴다** — 지시의
    #     *"정규화로 경기 전체 λ ±2% 유지"* 가 그 뜻이다.
    bench_mul = (math.exp(float(bench_coef) * float(bench_d))
                 if (bench_coef and bench_d) else 1.0)
    said_tab = dict(state_mult or {})
    mul = {} if said_tab else dict(lead_mul or {})
    lead = float(mul.get("leading") or 1.0)
    trail = float(mul.get("trailing") or 1.0)
    rates = minute_rates(lam_home, lam_away, late_home=late_home,
                         late_away=late_away)
    if bench_mul != 1.0:
        rates = bench_shift(rates, bench_mul)
    if said_tab:
        return _run_with_table(rates, said_tab, lam_home, lam_away)
    # 🔴 상태 = `(홈 득점, 원정 득점, 선제골이 누구였나)`
    #    `first` ∈ `0`(아직 없다) · `1`(홈) · `2`(원정)
    box: dict[tuple[int, int, int], float] = {(0, 0, 0): 1.0}
    # 🔴🔴 **구간 기대 득점**(§3) — 분마다 `상태 확률 × 그 분의 득점률` 을 더한다.
    #    ⚠️ 상태 배율이 분마다 다르므로 **전진하면서** 재야 맞는다(나중에 λ 를
    #       구간으로 쪼개면 배율을 못 반영한다).
    want = _buckets()
    acc = {"home": {k: 0.0 for k, _lo, _hi in want},
           "away": {k: 0.0 for k, _lo, _hi in want}}
    minute = 0
    for ph, pa in rates:
        minute += 1
        key = _bucket_key(want, minute)
        for (h, a, _first), p in box.items():
            if p <= 0.0:
                continue
            mh = ph * (lead if h > a else (trail if h < a else 1.0))
            ma = pa * (lead if a > h else (trail if a < h else 1.0))
            acc["home"][key] += p * min(mh, 0.5)
            acc["away"][key] += p * min(ma, 0.5)
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
    return _sum(box, buckets=acc)


def _put(box: dict, key: tuple, p: float) -> None:
    if p > 0.0:
        box[key] = box.get(key, 0.0) + p


def _buckets() -> list[tuple[str, int, int]]:
    """🔴 구간 표 — `config/tactical_rules.yaml` 의 `buckets` **하나**가 든다.

    🔴 사본 금지: 골 프로필(`goals.bucket_of`)과 **같은 구간**이어야 가설이
       *"후반 득점 비중"* 을 같은 뜻으로 읽는다.
    """
    from app.core import goals as _g
    out: list[tuple[str, int, int]] = []
    for row in (_g.table().get("buckets") or []):
        box = dict(row)
        out.append((str(box.get("key")), int(box.get("from") or 0),
                    int(box.get("to") or 0)))
    return out or [("0-30", 0, 30), ("31-60", 31, 60), ("61-90+", 61, 200)]


def _bucket_key(want: list[tuple[str, int, int]], minute: int) -> str:
    for key, lo, hi in want:
        if lo <= minute <= hi:
            return key
    return want[-1][0]


def _sum(box: dict, *, buckets: dict | None = None) -> Out:
    """🔴 상태 표 → 스코어 분포·승무패·오버·선제골 팀 승률 + §3 의 네 칸."""
    out = Out()
    scores: dict[tuple[int, int], float] = {}
    first_n = first_win = 0.0
    # 🔴 §3 — **팀별** 선제골 후 승리(조건부). `first` 1=홈 · 2=원정
    led = {"home": 0.0, "away": 0.0}
    led_win = {"home": 0.0, "away": 0.0}
    for (h, a, first), p in box.items():
        scores[(h, a)] = scores.get((h, a), 0.0) + p
        if first:
            first_n += p
            if (h > a and first == 1) or (a > h and first == 2):
                first_win += p
            side = "home" if first == 1 else "away"
            led[side] += p
            if (h > a and side == "home") or (a > h and side == "away"):
                led_win[side] += p
    tot = sum(scores.values()) or 1.0
    out.scores = {k: round(v / tot, 6) for k, v in sorted(scores.items())}
    out.home = round(sum(v for (h, a), v in scores.items() if h > a) / tot, 6)
    out.draw = round(sum(v for (h, a), v in scores.items() if h == a) / tot, 6)
    out.away = round(1.0 - out.home - out.draw, 6)
    out.over = {f"{x}": round(sum(v for (h, a), v in scores.items()
                                  if (h + a) > x) / tot, 4)
                for x in (0.5, 1.5, 2.5, 3.5, 4.5)}
    out.first_wins = (round(first_win / first_n, 4) if first_n > 0 else None)
    # 🔴🔴 §3 네 칸 — **같은 분포에서** 뽑는다
    out.xg = {"home": round(sum(h * v for (h, _a), v in scores.items())
                            / tot, 4),
              "away": round(sum(a * v for (_h, a), v in scores.items())
                            / tot, 4)}
    out.no_goal = {"home": round(sum(v for (h, _a), v in scores.items()
                                     if h == 0) / tot, 4),
                   "away": round(sum(v for (_h, a), v in scores.items()
                                     if a == 0) / tot, 4)}
    out.by_bucket = {side: {k: round(float(v), 4) for k, v in rows.items()}
                     for side, rows in dict(buckets or {}).items()}
    out.first_then_win = {
        side: (round(led_win[side] / led[side], 4) if led[side] > 0 else None)
        for side in ("home", "away")}
    out.why = (f"분 단위 해석 계산 {MINUTES}분 · 상태 표 {len(box)}칸 · "
               f"합 {tot:.4f}")
    return out
