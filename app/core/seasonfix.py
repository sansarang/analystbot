"""🔴🔴 **§4-2 S2-M1 — 시즌 초 수축**(통합 지시서 2026-10-13 밤 · M1 경계 모듈).

> `log(λ홈/λ원정)_new = s · log(λ홈/λ원정)_M1` ,
> `s = 1 − k·(1 − mean_retention)·(1 − games/8)` · 총골 보존(±2%) · **s ≥ 0.5**

🔴 **왜** — 시즌 초에는 **이번 시즌 자료가 거의 없다**(실측: 가시마 리그 9경기).
   그때 M1 은 **지난 시즌 팀**을 말하고 있고, 선수단이 많이 바뀐 팀(잔류율 낮음)
   일수록 그 말이 틀릴 확률이 높다 → 팀 간 차이를 **리그 평균 쪽으로** 줄인다.
🔴 **M1 은 K0 고정**이므로 이 모듈은 M1 이 낸 **λ 뒤**에 걸린다(경계 모듈).
🔴 **SF1** — 이번 시즌 9번째 경기부터 `s = 1`(수축 없음).
🔴 **SF2** — `k` 판이 없으면 **수축하지 않는다**(손값으로 메우지 않는다).
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

#: 🔴 시즌 초의 끝 — 이번 시즌 리그 경기 수가 이 수 이상이면 수축 없음(SF1)
FULL_GAMES = 8

#: 🔴 수축 상한 — 팀 간 차이를 **절반 밑으로는** 줄이지 않는다(지시 §4-2)
S_MIN = 0.5

#: 🔴 총골 기대를 이만큼 넘게 바꾸지 않는다(±2% 정규화)
TOTAL_BAND = 0.02


def s_of(*, games: int, mean_retention: float, k: float) -> tuple[float, str]:
    """🔴🔴 수축 계수 `s` 와 사유. `games ≥ 8` 이면 **1.0**(SF1)."""
    n = int(games or 0)
    if n >= FULL_GAMES:
        return 1.0, (f"수축 없음 — 이번 시즌 {n}경기(**9번째 경기부터 s=1** · "
                     f"{FULL_GAMES}경기 기준 · SF1)")
    ret = max(0.0, min(1.0, float(mean_retention)))
    raw = 1.0 - float(k) * (1.0 - ret) * (1.0 - n / float(FULL_GAMES))
    got = max(S_MIN, min(1.0, raw))
    return got, (f"s **{got:.3f}**(k {float(k):g} · 이번 시즌 {n}경기 · 잔류율 "
                 f"{ret:.2f}" + (f" · 🔴 상한 {S_MIN} 에 눌렸다"
                                 if raw < S_MIN else "") + ")")


def apply(lam: dict, *, s: float) -> tuple[dict, str]:
    """🔴 λ 의 **비(比)만** 수축한다 — 총골 기대는 **보존**(±2%)."""
    got = {"home": float(dict(lam or {}).get("home") or 0.0),
           "away": float(dict(lam or {}).get("away") or 0.0)}
    if got["home"] <= 0 or got["away"] <= 0:
        return got, "🔴 λ 가 없다 — **수축 미적용**"
    ratio = math.log(got["home"] / got["away"])
    half = 0.5 * (float(s) - 1.0) * ratio
    out = {"home": got["home"] * math.exp(half),
           "away": got["away"] * math.exp(-half)}
    was, now = sum(got.values()), sum(out.values())
    scale = max(1.0 - TOTAL_BAND, min(1.0 + TOTAL_BAND,
                                      (was / now) if now > 0 else 1.0))
    out = {kk: v * scale for kk, v in out.items()}
    hit = abs(sum(out.values()) / was - 1.0)
    return out, (f"**시즌 초 수축** s {float(s):.3f} · λ {got['home']:.3f}/"
                 f"{got['away']:.3f} → {out['home']:.3f}/{out['away']:.3f}"
                 f" · 총골 {hit:+.2%}"
                 + (f" · 🔴 ±{TOTAL_BAND:.0%} 띠에 **눌렸다**"
                    if hit >= TOTAL_BAND - 1e-9 else ""))


def plate_of(*, league: str, as_of) -> tuple[dict, str]:
    """🔴🔴 **SF2** — 그 리그의 `k` 판(엄격히 이전 · L3). 없으면 **빈 표**."""
    from app.core import versions as _v
    got, why = _v.pick(_v.path_of("seasonfix", league), as_of=as_of)
    return dict(got or {}), why


def bend(lam: dict, *, games: int, mean_retention: float, plate: dict
         ) -> tuple[dict, str]:
    """🔴 판의 `k` 로 수축한다. **판이 없으면 λ 를 그대로** 돌려준다(SF2)."""
    k = dict(plate or {}).get("k")
    if k is None:
        return dict(lam or {}), ("🔴 **시즌 초 수축 미적용** — `k` **판이 없다**"
                                 "(손값으로 메우지 않는다 · SF2)")
    s, why = s_of(games=games, mean_retention=mean_retention, k=float(k))
    if s >= 1.0:
        return dict(lam or {}), why
    got, why2 = apply(lam, s=s)
    return got, f"{why2} · {why}"
