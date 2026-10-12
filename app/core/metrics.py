"""🔴🔴 **평가 지표 한 곳** — 지시서 2026-10-12(엔진 교체) §1.

> 주지표: **로그 손실**. 병기: RPS · 방향 적중률 · 상위 30/20/10% 선택 적중률
> (같은 경기 수) · 브라이어(참고). 비교는 전부 **짝지은 차이 + 부트스트랩 95%**.
> 판정 규칙(고정): 구간상 낫다 → **채택** · 0 을 품는다 → **단순한 쪽 유지** ·
> 나쁘다 → **폐기**.

🔴 왜 한 곳인가 — 종전에는 브라이어·방향 적중률이 `tools/backfill_score.py`·
   `tools/score_cards.py`·`tools/judge_models.py` 에 **세 벌** 있었다. 사본은
   한쪽만 고쳐지고, 그러면 두 보고가 **다른 수**를 말한다(#1 사본 금지).
🔴 이 파일은 **수를 짓지 않는다** — 받은 확률과 결과만 센다.
⚠️ `app/` 에 두는 까닭: 운영 카드 채점(`analyze.score_finished`)도 같은 지표를
   써야 한다. 🔴 그러나 **원장으로 규칙을 고치지 않는다**(검증 전용 · CLAUDE.md).
"""
from __future__ import annotations

import math
import random

#: 🔴 결과 칸의 뜻 — 0 홈 · 1 무 · 2 원정(저장소 전체가 이 순서다)
HOME, DRAW, AWAY = 0, 1, 2

#: 🔴 선택 적중률을 재는 구간(지시 §1) — **같은 경기 수**로 견준다
BANDS: tuple[float, ...] = (0.30, 0.20, 0.10)


def logloss(p: list[float], hit: int) -> float:
    """🔴🔴 **주지표** — 맞힌 칸의 확률에 로그를 씌운 손실(작을수록 좋다)."""
    return -math.log(max(1e-9, min(1.0, float(p[int(hit)]))))


def brier(p: list[float], hit: int) -> float:
    """🔴 참고 지표 — 세 칸의 제곱 오차 합."""
    return sum((float(p[i]) - (1.0 if i == int(hit) else 0.0)) ** 2
               for i in range(3))


def rps(p: list[float], hit: int) -> float:
    """🔴🔴 **RPS**(ranked probability score) — 승·무·패의 **순서를 아는** 손실.

    🔴 왜 필요한가: 브라이어는 *"원정이 났는데 홈을 높게 봤다"* 와 *"원정이 났는데
       무를 높게 봤다"* 를 거의 같게 센다. RPS 는 **한 칸 빗나감**을 덜 벌한다 —
       축구 승무패 평가의 표준이다.
    ⚠️ 칸 순서가 홈·무·원정이어야 뜻이 산다(이 파일의 `HOME/DRAW/AWAY`).
    """
    cum_p = 0.0
    cum_y = 0.0
    out = 0.0
    for i in range(2):                      # 🔴 마지막 칸은 둘 다 1 이라 뺀다
        cum_p += float(p[i])
        cum_y += 1.0 if int(hit) == i else 0.0
        out += (cum_p - cum_y) ** 2
    return out / 2.0


def direction_hit(p: list[float], hit: int) -> bool:
    """🔴 **방향 적중** — 가장 높은 칸이 결과와 같나."""
    if not p:
        return False
    return int(max(range(3), key=lambda i: float(p[i]))) == int(hit)


def boot_ci(vals: list[float], *, n: int = 2000, seed: int = 7
            ) -> tuple[float, float]:
    """🔴 부트스트랩 95% 구간. ⚠️ 씨앗을 고정한다 — 같은 표본은 같은 구간이다."""
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    rnd = random.Random(seed)
    got = []
    for _ in range(int(n)):
        said = [vals[rnd.randrange(len(vals))] for _ in vals]
        got.append(sum(said) / len(said))
    got.sort()
    return got[int(0.025 * n)], got[int(0.975 * n)]


def paired(cand: list[float], base: list[float], *, n: int = 2000) -> dict:
    """🔴🔴 **짝지은 차이** — 같은 경기에서 (후보 손실 − 기준 손실).

    `{mean, lo, hi, n}` — 음수면 후보가 **낫다**(손실이 작다).
    ⚠️ 길이가 다르면 예외다 — 다른 표본끼리 견주면 그 비교는 거짓이다.
    """
    if len(cand) != len(base):
        raise ValueError(f"🔴 짝이 안 맞는다 — 후보 {len(cand)} vs 기준 {len(base)}")
    diff = [float(a) - float(b) for a, b in zip(cand, base, strict=True)]
    if not diff:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"),
                "n": 0}
    lo, hi = boot_ci(diff, n=n)
    return {"mean": sum(diff) / len(diff), "lo": lo, "hi": hi, "n": len(diff)}


def verdict_of(got: dict) -> str:
    """🔴🔴 **판정 규칙(고정)** — 지시 §1. 결과를 보고 이 함수를 고치지 않는다.

    - 구간이 **전부 음수** → `채택`(후보가 낫다)
    - 구간이 **0 을 품는다** → `유지`(단순한 쪽을 둔다)
    - 구간이 **전부 양수** → `폐기`
    """
    lo, hi = float(got.get("lo", float("nan"))), float(got.get("hi", float("nan")))
    if math.isnan(lo) or math.isnan(hi):
        return "모름"
    if hi < 0:
        return "채택"
    if lo > 0:
        return "폐기"
    return "유지"


def wilson(hit: int, n: int) -> tuple[float, float]:
    """🔴 95% 구간 — 윌슨(작은 표본에서 정규 근사보다 낫다)."""
    if n <= 0:
        return (float("nan"), float("nan"))
    z = 1.959964
    p = hit / n
    d = 1.0 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, mid - half), min(1.0, mid + half))


def bands(rows: list[dict], *, keys: tuple[str, ...],
          fracs: tuple[float, ...] = BANDS) -> dict:
    """🔴🔴 **선택 적중률** — 모형마다 최고 확률 상위 구간의 실제 적중률.

    `{비율: {열쇠: {n, hit, rate, lo, hi}}}` — 🔴 구간마다 **같은 경기 수**다.
    ⚠️ `rows` 는 `{열쇠: [홈,무,원정], "hit": 0|1|2}` 꼴이다.
    """
    out: dict = {}
    n_all = len(rows)
    for frac in fracs:
        k = max(1, int(round(n_all * float(frac))))
        box: dict = {}
        for key in keys:
            said = sorted((r for r in rows if r.get(key)),
                          key=lambda r: -max(r[key]))[:k]
            hit = sum(1 for r in said if direction_hit(r[key], r["hit"]))
            lo, hi = wilson(hit, len(said))
            box[key] = {"n": len(said), "hit": hit,
                        "rate": (hit / len(said)) if said else float("nan"),
                        "lo": lo, "hi": hi}
        out[frac] = box
    return out


def calib(rows: list[dict], *, group: str, side: int = HOME,
          key: str = "p") -> dict:
    """🔴🔴 **하위 그룹 보정표**(지시 §1·§8) — 그룹별 **평균 예측 − 실제**.

    `{그룹: {n, pred, real, bias, lo, hi}}` — 양수면 그 그룹에서 봇이 그 칸을
    **높게** 본다(과대평가).
    ⚠️ 구간은 짝별 차(예측 − 결과 0/1)의 부트스트랩이다.
    """
    out: dict = {}
    seen: dict[str, list[float]] = {}
    for r in rows:
        p = r.get(key)
        if not p:
            continue
        said = str(r.get(group) or "")
        seen.setdefault(said, []).append(
            float(p[int(side)]) - (1.0 if int(r["hit"]) == int(side) else 0.0))
    for name, vals in seen.items():
        lo, hi = boot_ci(vals)
        out[name] = {"n": len(vals),
                     "bias": sum(vals) / len(vals), "lo": lo, "hi": hi}
    return out


def check_split(*, fit: set, eval: set) -> str:        # noqa: A002
    """🔴🔴 **계약 E1** — 적합 기간과 평가 기간이 겹치면 **예외**다.

    > 같은 데이터로 적합·평가한 수는 **보고 금지**(지시 §1).

    겹치지 않으면 빈 글자를 돌려준다(부를 자리에서 사유로 적는다).
    """
    both = {str(v) for v in (fit or set())} & {str(v) for v in (eval or set())}
    if both:
        raise ValueError(f"🔴 **E1 위반** — 적합·평가 기간이 겹친다: {sorted(both)}")
    return ""
