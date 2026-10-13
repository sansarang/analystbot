"""🔴🔴 **§8-2 앙상블 — 격자 혼합**(통합 지시서 2026-10-13 밤).

> `G = Σ w_k·G_k` (`w_k ≥ 0`, `Σ=1`) → **모든 시장 줄은 G 하나에서**.

🔴 **왜 격자를 섞나** — 승무패만 섞으면 오버/핸디캡/BTTS 를 **다시 지어내야** 한다.
   격자를 섞으면 모든 줄이 **한 분포**에서 나온다(C2 와 같은 규율).
   ⚠️ 대조 판(승무패만 평균)과 **같은 수**가 나오는지 계약이 센다.
🔴 **EN2** 판 없이 섞지 않는다 · **EN3/EN7** 가중치는 음수가 아니고 합이 1 이다 ·
   **EN4** `0-0` 칸이 있어야 한다 · **EN6** 합이 1 이 아닌 격자는 **안 받는다**.
🔴 구성 격자가 하나라도 **없으면 섞지 않는다** — 남은 것으로 **재정규화하지
   않는다**(§9: *"구성 격자 누락 시 M1 단독 + 🔴 앙상블 미적용(사유)"*).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 격자 규격 — 0~10골(지시 §8-1). 그 밖은 **꼬리로 적고** 정규화한다.
MAXG = 10

#: 🔴 합이 1 인지 보는 눈금(소수 여섯째 · EN3)
EPS = 1e-6


def normalise(grid: dict) -> tuple[dict, str]:
    """🔴 0~10골로 자르고 **꼬리 무게를 적은 뒤** 다시 1 로 맞춘다."""
    box = {(int(h), int(a)): float(v) for (h, a), v in dict(grid or {}).items()}
    keep = {k: v for k, v in box.items() if k[0] <= MAXG and k[1] <= MAXG}
    tail = sum(v for k, v in box.items() if k not in keep)
    total = sum(keep.values())
    if total <= 0:
        return {}, "🔴 격자가 비었다 — 정규화할 것이 없다"
    out = {k: v / total for k, v in keep.items()}
    return out, (f"0~{MAXG}골로 자르고 **꼬리 {tail:.6f}** 를 적은 뒤 정규화"
                 f"(칸 {len(out)}개)")


def blend(grids: list[dict], weights: list[float]) -> tuple[dict, str]:
    """🔴🔴 `Σ w_k·G_k`. 못 섞으면 **빈 표 + 사유**(EN3·EN4·EN6·EN7)."""
    box = list(grids or [])
    w = [float(x) for x in (weights or [])]
    if not box or len(box) != len(w):
        return {}, f"🔴 격자 {len(box)}개 · 가중치 {len(w)}개 — **짝이 안 맞는다**"
    if any(x < 0 for x in w):
        return {}, f"🔴 **음수 가중치**가 있다({w}) — EN7"
    if abs(sum(w) - 1.0) > EPS:
        return {}, f"🔴 가중치 합이 **{sum(w):.6f}** 다(1 이어야 한다 · EN3·EN7)"
    out: dict = {}
    for one, weight in zip(box, w, strict=True):
        said = {(int(h), int(a)): float(v)
                for (h, a), v in dict(one or {}).items()}
        total = sum(said.values())
        if abs(total - 1.0) > 1e-4:
            return {}, (f"🔴 **정규화되지 않은 격자**(합 {total:.6f}) — "
                        f"`normalise` 를 먼저 지나야 한다(EN6)")
        if (0, 0) not in said:
            return {}, "🔴 격자에 **`0-0` 칸이 없다** — EN4"
        for k, v in said.items():
            out[k] = out.get(k, 0.0) + weight * v
    return out, ("혼합 — w " + " · ".join(f"{x:.2f}" for x in w)
                 + f" · 칸 {len(out)}개 · 합 {sum(out.values()):.6f}")


def plate_of(*, league: str, as_of) -> tuple[dict, str]:
    """🔴🔴 **EN2** — 그 리그의 가중치 판(엄격히 이전 · L3). 없으면 **빈 표**."""
    from app.core import versions as _v
    got, why = _v.pick(_v.path_of("ensemble", league), as_of=as_of)
    if not got:
        said, why2 = _v.pick(_v.path_of("ensemble", "all"), as_of=as_of)
        return dict(said or {}), (f"{why} · 전체 판 — {why2}")
    return dict(got), why


def of(grids: dict, *, plate: dict) -> tuple[dict, str]:
    """🔴 판의 가중치로 섞는다. **판이 없거나 격자가 빠지면 섞지 않는다**."""
    w = dict(dict(plate or {}).get("w") or {})
    if not w:
        return {}, ("🔴 **앙상블 미적용** — 가중치 **판이 없다**(EN2 · "
                    "M1 단독으로 간다)")
    want = sorted(w)
    missing = [k for k in want if not dict(grids or {}).get(k)]
    if missing:
        return {}, (f"🔴 **앙상블 미적용** — 구성 격자 **누락** {missing}"
                    f"(남은 것으로 **재정규화하지 않는다**)")
    box = [dict(grids[k]) for k in want]
    got, why = blend(box, [float(w[k]) for k in want])
    if not got:
        return {}, f"🔴 **앙상블 미적용** — {why}"
    return got, ("**앙상블** " + " + ".join(f"{k} {float(w[k]):.2f}"
                                           for k in want) + f" · {why}")


def mix(triples: dict, w: dict) -> tuple[list[float], str]:
    """🔴🔴 **승무패 세 수의 선형 혼합** — 격자 혼합과 **같은 답**이다.

    🔴 `markets_of(Σ w_k·G_k) = Σ w_k·markets_of(G_k)`(계약이 센다). 그래서
       카드의 **그림자 줄**은 격자를 다시 만들지 않고 이 함수로 센다.
    ⚠️ 구성 확률이 하나라도 **없으면 섞지 않는다**(재정규화 금지 · §9).
    """
    box = dict(triples or {})
    want = sorted(dict(w or {}))
    missing = [k for k in want if not box.get(k)]
    if missing:
        return [], (f"🔴 **그림자 미산출** — 구성 확률 **누락** {missing}"
                    f"(재정규화하지 않는다)")
    out = [0.0, 0.0, 0.0]
    for k in want:
        one = [float(x) for x in box[k]]
        for i in range(3):
            out[i] += float(w[k]) * one[i]
    total = sum(out)
    if total <= 0:
        return [], "🔴 **그림자 미산출** — 합이 0 이다"
    return [x / total for x in out], (
        "그림자 " + " + ".join(f"{k} {float(w[k]):.2f}" for k in want))
