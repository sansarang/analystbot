"""🔴🔴 **§5 라인업 보정 — M1 경계 모듈**(라인업 지시서 2026-10-13).

> M1(legacy-4axis) 코드는 **K0 고정**. 라인업 보정은 M1 격자 계산 **직전 λ** 에
> 거는 경계 모듈로만. `log λ홈 += Σ g_k·L_k` · `log λ원정 −= Σ g_k·L_k`
> → 팀 총골 기대 **±2% 정규화** → 격자 재계산.

🔴 **왜 경계인가** — 진단(2026-10-13): 평소 XI → 확정 XI 가 평균 5.2자리 바뀌어도
   확률은 **0.2~0.7%p** 밖에 안 움직였다. 까닭은 M1 축0 이 **11명 로그 가치 합**
   (수준값 ≈18)이라 두세 자리 교체가 그 합을 **0.3%** 만 바꾸고, 그것이 β×비중
   0.075 를 지나 λ 를 **0.25%** 움직였기 때문이다. 🔴 그 안을 고치면 얼린 M1 을
   고치는 것이므로, **밖에서 λ 에 직접** 건다.
🔴 신호는 **전부 차분값**이다(§4) — 수준값은 이미 M1 안에 있다.
🔴 **직교화** — 각 신호에서 *축0 차로 설명되는 몫*을 뺀다(`L⊥ = L − (a + b·축0Δ)`).
   그래야 보정이 *"누가 강팀인가"* 를 **두 번** 말하지 않는다.
🔴 **판 없이 보정 없음**(LF4) · **상한 초과 판은 무효**(LF2 · 계수 폭주 방지).
⚠️ 실측: M1 은 λ 를 **그대로 내준다**(`legacy.old_engine.OldOut.lam`) — 그래서
   격자에서 λ 를 역산하는 어댑터는 **필요 없다**(§5 의 퇴로를 안 쓴다).
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

#: 🔴 후보 신호 — §4 와 **재료 교체판 v2**(사용자 결정 2026-10-13 저녁 2번).
#   L1·L2·L5 는 **구간 ±**(`player_pm`) 재료, L6·L7·L8 은 **박스 기록**
#   (`player_box` · 90분당 xG+xA) 재료다. 전부 **차분값**이고 직교화를 지난다.
SIGNALS: tuple[str, ...] = ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")

#: 🔴 상한 감시 — `|g_k · sd(L_k)|` 가 이보다 크면 그 판은 **무효**다(§5)
CAP = 0.15

#: 🔴 팀 총골 기대를 이만큼 넘게 바꾸지 않는다(§5 "±2% 정규화")
TOTAL_BAND = 0.02

#: 🔴 핵심 주전 수 — L4 가 보는 상위 몇 명인가(§4)
KEY_TOP = 3

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **지운 자리 — L1~L5(구간 ± 재료)**(사용자 결정 2026-10-13 저녁)
# ══════════════════════════════════════════════════════════════════
#
#  🔴 `raw_of`(L1 pdiff · L2 absΔ · L3 starterΔ · L4 keyoutΔ · L5 benchΔ)와
#     `bench_shift_of` 를 **지웠다** — 재료(구간 ± `player_pm`)가 교체됐고
#     부르는 곳이 사라졌다(규율 2: *"안 이어진 코드는 없는 코드보다 나쁘다"*).
#  ⚠️ 그 판의 측정은 **남아 있다** —
#     `docs/fable/stages/2026-10-13_lineup_to_m1.md`(로그 손실 · 분포 · 계수)와
#     커밋 `974143ec`. 🔴 결론: 규칙은 `B+L1` 을 통과시켰지만 움직이는 폭이
#     **0.12%p · ≥3%p 0건** 이어서 사용자가 **배선하지 않기로** 했다.
#  🔴 그 재료의 뿌리 문제: 선수 ± 반분 상관 **+0.09(J1) · +0.06(K1)**(문턱 0.3).


def _front(box: dict) -> tuple[dict, set]:
    """🔴 가치 v2 표 → `(값, 공격으로 센 선수들)`. ⚠️ 뒷선은 **공격에 안 센다**."""
    value = dict(dict(box or {}).get("value") or {})
    kind = dict(dict(box or {}).get("kind") or {})
    front = {k for k in value if str(kind.get(k, "공격")) == "공격"}
    return value, front


def raw_v2_of(*, home: dict, away: dict, box: dict) -> tuple[dict, str]:
    """🔴🔴 **신호 v2** — L6·L7·L8(전부 홈−원정 차). `(값, 사유)`.

    | 신호 | 무엇 |
    |---|---|
    | L6 | 오늘 XI **공격 기여 합**(90분당 xG+xA) 차 |
    | L7 | 평소 XI 의 **공격 기여 상위 3명** 중 빠진 수 차 |
    | L8 | (빠진 평소 주전 기여 − 들어온 선수 기여) 차 |

    🔴 **뒷선(GK·DF)은 공격 합에 0 으로 들어간다** — 그 수는 출전 분 비중이고
       xG 단위가 아니다(`player_box` PB3). ⚠️ 수비 가치는 **후속 과제**다.
    ⚠️ 표가 없으면 **빈 값 + 사유**다(0 으로 메우지 않는다 · #3).
    """
    value, front = _front(box)
    if not value:
        return {}, "🔴 **선수 가치 v2 표가 없다** — L6·L7·L8 을 못 쟀다"

    def _sum(ids) -> float:
        return sum(float(value.get(str(p), 0.0)) for p in (ids or [])
                   if str(p) in front)

    def _side(one: dict) -> dict:
        said = dict(one or {})
        xi = [str(p) for p in (said.get("xi") or [])]
        usual = [str(p) for p in (said.get("usual") or [])]
        gone = [p for p in usual if p not in set(xi)]
        came = [p for p in xi if p not in set(usual)]
        top = sorted([p for p in usual if p in front],
                     key=lambda p: -float(value.get(p, 0.0)))[:KEY_TOP]
        return {"attack": _sum(xi),
                "keyout": float(len([p for p in top if p not in set(xi)])),
                "abs": _sum(gone) - _sum(came), "n_usual": len(usual)}

    h, a = _side(home), _side(away)
    got = {"L6": h["attack"] - a["attack"], "L7": h["keyout"] - a["keyout"],
           "L8": h["abs"] - a["abs"]}
    thin = [s for s, one in (("home", h), ("away", a)) if not one["n_usual"]]
    if thin:
        for k in ("L7", "L8"):
            got.pop(k, None)
    why = (f"L6 {got.get('L6', 0.0):+.3f} · L7 "
           + (f"{got['L7']:+.0f}" if "L7" in got else "⬜")
           + " · L8 " + (f"{got['L8']:+.3f}" if "L8" in got else "⬜")
           + " · ⚠️ **뒷선(GK·DF)은 공격 합에 안 센다**(출전 분 비중이라 단위가 "
             "다르다 — 수비 가치는 후속 과제)"
           + (f" · 🔴 평소 XI 가 없다({', '.join(thin)}) → L7·L8 **못 쟀다**"
              if thin else ""))
    return got, why


def ortho(raw: dict, *, axis0: float, plate: dict) -> tuple[dict, str]:
    """🔴🔴 직교화 — `L⊥ = L − (a + b·축0Δ)`. 판에 `a·b` 가 없는 신호는 **버린다**.

    🔴 **LF1** — 직교화하지 않은 신호는 보정에 **못 들어온다**(판이 문이다).
    """
    box = dict(dict(plate or {}).get("ortho") or {})
    out: dict[str, float] = {}
    lost: list[str] = []
    for k, v in dict(raw or {}).items():
        one = dict(box.get(k) or {})
        if "a" not in one or "b" not in one:
            lost.append(k)
            continue
        out[k] = float(v) - (float(one["a"]) + float(one["b"]) * float(axis0))
    why = (f"직교화 {len(out)}개(축0Δ {float(axis0):+.3f})"
           + (f" · 🔴 **직교화 계수가 없는 신호 {lost} 는 버렸다**" if lost
              else ""))
    return out, why


def plate_of(*, league: str, as_of) -> tuple[dict, str]:
    """🔴🔴 **LF4** — 그 리그의 판. 고르는 규칙은 `versions` 하나다(엄격히 이전)."""
    from app.core import versions as _v
    box = _v.path_of("lineupfix", league)
    got, why = _v.pick(box, as_of=as_of)
    return dict(got or {}), why


def check(plate: dict) -> tuple[bool, str]:
    """🔴🔴 **LF2** — `|g_k · sd(L_k)| > 0.15` 면 그 판은 **무효**다."""
    box = dict(plate or {})
    g = dict(box.get("g") or {})
    sd = dict(box.get("sd") or {})
    if not g:
        return False, "🔴 **판이 없다**(계수 `g` 가 비었다) — 보정하지 않는다"
    bad = {k: abs(float(v) * float(sd.get(k) or 0.0)) for k, v in g.items()
           if abs(float(v) * float(sd.get(k) or 0.0)) > CAP}
    if bad:
        return False, ("🔴 **상한 초과 — 판 무효**(계수 폭주): "
                       + " · ".join(f"{k} |g·sd| {v:.3f} > {CAP}"
                                    for k, v in sorted(bad.items())))
    said = " · ".join(f"{k} g {float(v):+.3f}(|g·sd| "
                      f"{abs(float(v) * float(sd.get(k) or 0.0)):.3f})"
                      for k, v in sorted(g.items()))
    return True, f"판 확인 — {said}"


def apply(lam: dict, *, raw: dict, plate: dict, axis0: float = 0.0
          ) -> tuple[dict, str]:
    """🔴🔴 §5 — M1 의 λ 에 라인업 보정을 건다. `(새 λ, 사유)`.

    🔴 **판이 없거나 상한을 넘으면 λ 를 그대로 돌려준다**(LF2·LF4) — 손값으로
       메우지 않는다. 🔴 직교화되지 않은 신호는 들어오지 못한다(LF1).
    🔴 팀 총골 기대는 **±2% 안**으로 되돌린다(보정은 *"어느 쪽이 더 센가"* 를
       말하는 것이고 *"골이 몇 개 날 것인가"* 를 바꾸는 것이 아니다).
    """
    got = {"home": float(dict(lam or {}).get("home") or 0.0),
           "away": float(dict(lam or {}).get("away") or 0.0)}
    if got["home"] <= 0 or got["away"] <= 0:
        return got, "🔴 λ 가 없다 — **라인업 보정 미산출**"
    ok, why_plate = check(plate)
    if not ok:
        return got, f"**라인업 보정 미산출** — {why_plate}"
    box = dict(plate or {})
    adopted = [k for k in (box.get("adopted") or []) if k in SIGNALS]
    said, why_o = ortho({k: v for k, v in dict(raw or {}).items()
                         if k in adopted}, axis0=axis0, plate=box)
    if not said:
        return got, f"**라인업 보정 미산출** — {why_o} · {why_plate}"
    g = dict(box.get("g") or {})
    # 🔴 L5 는 λ 가 아니다 — **시뮬 60분 뒤 배율**로만 쓴다(§4·§5)
    move = sum(float(g.get(k) or 0.0) * float(v)
               for k, v in said.items() if k != "L5")
    out = {"home": got["home"] * math.exp(move),
           "away": got["away"] * math.exp(-move)}
    was, now = sum(got.values()), sum(out.values())
    scale = max(1.0 - TOTAL_BAND, min(1.0 + TOTAL_BAND,
                                      (was / now) if now > 0 else 1.0))
    out = {k: v * scale for k, v in out.items()}
    hit = abs(sum(out.values()) / was - 1.0)
    why = (f"**라인업 보정** logλ {move:+.4f}(" + " · ".join(
        f"{k} {float(said[k]):+.3f}×g {float(g.get(k) or 0.0):+.3f}"
        for k in sorted(said) if k != "L5")
        + f") · λ {got['home']:.3f}/{got['away']:.3f} → "
          f"{out['home']:.3f}/{out['away']:.3f} · 총골 {hit:+.2%}"
        + (f" · 🔴 ±{TOTAL_BAND:.0%} 띠에 **눌렸다**"
           if hit >= TOTAL_BAND - 1e-9 else "")
        + f" · {why_o} · {why_plate}")
    if "L5" in said:
        why += (f" · ⬜ L5 {float(said['L5']):+.3f} 는 λ 가 아니라 **60분 뒤 "
                f"배율**이다(여기서 안 걸었다)")
    return out, why
