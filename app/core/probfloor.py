"""🔴🔴 **확률 변환 — λ 식 하나**(지시서 2026-10-12 엔진 교체 §3 · 적중률 1번).

⚠️ **2026-10-12 §3 로 바뀐 것**: 손값 β 로 바닥을 기울이던 `blend` 는 이 파일에서
   **걷었다**(그 식은 옛 구조의 비교용이라 `tools/backfill_score.py` 로 옮겼다).
   🔴 이 파일의 λ 는 이제 **적합된 계수**(`b0`·`b1`·`b2`·`h_league`·ρ)만 쓴다.
   `direction_hit` 도 걷었다 — 지표는 `app/core/metrics.py` 하나다(사본 금지).

> ③ **Elo → 바닥 λ/승무패**. ⑪ **축0·축1만**(Elo 대비 잔차).
> **축2·축3·⑩ 전략 판정은 확률 경로 밖**(표시·검증).

🔴 왜 — 444경기 백필(J1+K리그1 두 시즌 · as-of 재생):
```
축0 개선 +0.0007 · 축1 +0.0001 · 축2 **−0.0038** · 축3 **−0.0039**
봇 vs Elo만 브라이어 차 −0.0052(95% −0.0119~+0.0015) → **못 이긴다**
```
축2·축3 은 넣으면 **손실이 커진다**(잡음이다). 그래서 확률은 **Elo 를 바닥**으로
깔고 축0·축1 만 그 위의 **잔차**로 얹는다.

🔴🔴 **C1 개정**: 옛 C1 은 *"S3 입력에 Elo 가 없다"* 였다 — 이제 **Elo 가 바닥**이다.
   ⚠️ 나머지 금지는 **그대로**다: 동기·일정·감독 발언·맞대결·시장·LLM 문장은
   확률에 닿지 않는다.
⚠️ 이 파일은 **수를 짓지 않는다** — 바닥은 적합된 순서형 로짓(`base.triple_of`),
   잔차 비중·β 는 `config/matchup_model.yaml` 이 든다.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

#: 🔴🔴 **잔차로 쓰는 축** — 백필에서 개선이 **양수**였던 둘뿐이다.
#  ⚠️ 늘리려면 **백필 전진 선택에서 양수**임을 먼저 보여야 한다(지시 2번).
RESIDUAL_AXES: tuple[str, ...] = ("axis0", "axis1")


def floor_of(*, kind: str, dr: float | None) -> tuple[list[float] | None, str]:
    """🔴🔴 ③ — **Elo 바닥 승무패**. `([홈, 무, 원정], 사유)`. 없으면 `(None, 사유)`.

    🔴 입구는 `app/core/base.triple_of` **하나다**(사본 금지) — 대회 유형별로
       적합된 순서형 로짓이고, 그 적합이 없으면 바닥도 **없다**.
    ⚠️ `dr` 은 **경기 전** 등급 차다(누설 금지 · L1).
    """
    if dr is None:
        return None, "🔴 Elo 등급 차가 **없다** — 바닥을 만들지 않는다"
    from app.core import base as _base
    got, why = _base.triple_of(str(kind), float(dr))
    if got is None:
        return None, f"🔴 Elo 바닥 없음 — {why}"
    return ([float(got.home), float(got.draw), float(got.away)],
            f"Elo 바닥(순서형 로짓 · 등급 차 {float(dr):+.1f}) — {why}")


def solve_move(want: list[float] | None, *, mean: float, mul_home: float,
               mul_away: float, tries: int = 40
               ) -> tuple[float | None, str]:
    """🔴🔴 바닥 승무패를 **시뮬이 재현**하도록 λ 기울기(로그 오즈)를 푼다.

    `(이동, 사유)` — 못 맞추면 `(None, 사유)`.

    🔴 왜 — *"최종 확률 = 시뮬 결과"*(C2)와 *"Elo 가 바닥"*(C1 개정)을 **함께**
       세우려면, 바닥을 **λ 로 번역**해야 한다. 그 뒤에 축0·축1 잔차를 **같은 λ 에**
       얹으면 분포·오버·스코어가 전부 한 수를 쓴다.
    🔴 이분법으로 푼다(단조다: 이동이 커지면 홈 승 확률이 커진다).
    ⚠️ 상한(±0.9)에 닿아도 못 맞추면 **그 사실을 적는다**.
    """
    if not want:
        return None, "🔴 바닥이 **없다** — λ 기울기를 풀 수 없다"
    from app.core import sim as _sim
    target = float(want[0])

    def _home(move: float) -> float:
        got = _sim.run(float(mean) * float(mul_home) * math.exp(move),
                       float(mean) * float(mul_away) * math.exp(-move))
        return float(got.home)

    lo, hi = -0.9, 0.9
    if _home(lo) > target:
        return lo, (f"⚠️ 바닥 홈 {target:.1%} 가 **상한 밖**이다(이동 {lo:+.2f} "
                    f"에서 {_home(lo):.1%}) — 상한을 쓴다")
    if _home(hi) < target:
        return hi, (f"⚠️ 바닥 홈 {target:.1%} 가 **상한 밖**이다(이동 {hi:+.2f} "
                    f"에서 {_home(hi):.1%}) — 상한을 쓴다")
    for _ in range(int(tries)):
        mid = (lo + hi) / 2.0
        if _home(mid) < target:
            lo = mid
        else:
            hi = mid
    got = (lo + hi) / 2.0
    return got, (f"바닥 홈 {target:.1%} 를 맞추는 λ 기울기 {got:+.3f}"
                 f"(시뮬 {_home(got):.1%})")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§3 확률 변환 — 손값 β 를 지운 식 하나**(지시서 2026-10-12 §3)
# ══════════════════════════════════════════════════════════════════
#
#  > log λ홈  = b0 + b1·diff + b2·player_diff + h_league [+ 채택 항]
#  > log λ원정 = b0 − b1·diff − b2·player_diff
#  > 그 위에 **Dixon-Coles ρ**(리그별) → 스코어 격자 → 승무패·오버·핸디·BTTS
#  > **전부 같은 격자에서**.
#
#  🔴 왜 — 종전에는 λ 를 *"리그 평균 × 홈 배율 × exp(β×축합)"* 으로 만들었고 β 는
#     **손값**이었다(`matchup_model.yaml: beta 0.25` · `fit.provisional: true`).
#     그러면 *"무엇이 λ 를 움직였나"* 를 적합이 말하지 않는다.
#  🔴 이제 계수는 **포아송 최대우도**가 정하고 **판 파일**에 적힌다
#     (`data/probfloor/<리그>/<날>.yaml` · `tools/fit_probfloor.py`).
#  🔴 홈 이점은 `h_league` **한 자리**다(계약 P3) — 리그 배율을 따로 곱하지 않는다.
#  ⚠️ 승격 전까지 운영 ⑯ 은 **옛 식**으로 돈다(§0: 백필 판정을 통과한 판만 승격).

#: 🔴 격자 상한 — 한 팀 최대 골(그 위는 꼬리가 1e-6 보다 작다)
GRID_MAX = 12

#: 🔴 계수 판이 사는 표
COEF_TABLE = "probfloor"

#: 🔴 식에 들어가는 이름 — `fit_probfloor` 가 **이 목록만** 적합한다
COEF_NAMES: tuple[str, ...] = ("b0", "b1", "b2", "h_league", "rho")


def lambdas(*, diff: float, player_diff: float, coef: dict,
            extra_home: float = 0.0, extra_away: float = 0.0
            ) -> tuple[dict, str]:
    """🔴🔴 §3 — **λ 두 개**를 그 식 하나로 만든다. `({home, away}, 사유)`.

    🔴 `extra_*` 는 **§6 에서 채택된 항**만 들어오는 자리다(채택 안 된 항은 0 —
       계약 C6-2). ⚠️ 홈 이점은 `h_league` 로만 들어온다(계약 P3).
    """
    b0 = float(dict(coef).get("b0") or 0.0)
    b1 = float(dict(coef).get("b1") or 0.0)
    b2 = float(dict(coef).get("b2") or 0.0)
    h = float(dict(coef).get("h_league") or 0.0)
    log_h = b0 + b1 * float(diff) + b2 * float(player_diff) + h + float(extra_home)
    log_a = b0 - b1 * float(diff) - b2 * float(player_diff) + float(extra_away)
    out = {"home": math.exp(log_h), "away": math.exp(log_a)}
    said = (f"λ {out['home']:.3f}/{out['away']:.3f} ← b0 {b0:+.3f} · "
            f"diff {float(diff):+.3f}×b1 {b1:.3f} · 선수 차 "
            f"{float(player_diff):+.3f}×b2 {b2:.3f} · h_league {h:+.3f}")
    if extra_home or extra_away:
        said += f" · 채택 항 홈 {float(extra_home):+.3f}/원정 {float(extra_away):+.3f}"
    return out, said


def score_grid(*, lam_home: float, lam_away: float, rho: float = 0.0,
               nmax: int = GRID_MAX) -> dict:
    """🔴🔴 **스코어 격자 하나** — `{(홈골, 원정골): 확률}`(합 1.0).

    🔴 **Dixon-Coles ρ** 는 낮은 스코어 **네 칸**(0-0·1-0·0-1·1-1)만 고친다 —
       포아송 둘이 서로 모른다고 보면 **무승부가 모자란다**(실측된 축구의 성질).
    ⚠️ 고친 뒤 **다시 정규화**한다(합이 1 이어야 한다).
    """
    import math as _m

    def pois(k: int, lam: float) -> float:
        return _m.exp(-lam) * (lam ** k) / _m.factorial(k)

    out: dict = {}
    for h in range(int(nmax) + 1):
        for a in range(int(nmax) + 1):
            out[(h, a)] = pois(h, float(lam_home)) * pois(a, float(lam_away))
    r = float(rho)
    if r:
        lh, la = float(lam_home), float(lam_away)
        tau = {(0, 0): 1.0 - lh * la * r, (0, 1): 1.0 + lh * r,
               (1, 0): 1.0 + la * r, (1, 1): 1.0 - r}
        for key, mul in tau.items():
            out[key] = max(0.0, out[key] * mul)
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()}


def markets_of(grid: dict) -> dict:
    """🔴🔴 **P2** — 승무패·오버·핸디·BTTS 를 **그 격자 하나**에서 센다.

    ⚠️ 한 마켓이라도 다른 곳에서 세면 카드의 두 줄이 **서로 다른 말**을 한다.
    """
    out: dict = {"home": 0.0, "draw": 0.0, "away": 0.0,
                 "btts_yes": 0.0, "btts_no": 0.0,
                 "over": {}, "ah": {}}
    tot_lines = (0.5, 1.5, 2.5, 3.5, 4.5)
    over = dict.fromkeys(tot_lines, 0.0)
    # 🔴 **양쪽 줄을 다 센다** — 약팀이 홈일 수도 원정일 수도 있다(§11).
    #  ⚠️ 실사고 2026-10-12: 홈 줄만 만들어 `away+0.5` 에서 터졌다(e2e 가 잡았다).
    lines = (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)
    ah = {f"{side}{l:+.1f}": 0.0 for side in ("home", "away") for l in lines}
    for (h, a), p in dict(grid).items():
        if h > a:
            out["home"] += p
        elif h == a:
            out["draw"] += p
        else:
            out["away"] += p
        if h > 0 and a > 0:
            out["btts_yes"] += p
        else:
            out["btts_no"] += p
        for line in tot_lines:
            if h + a > line:
                over[line] += p
        for key in ah:
            side = "home" if key.startswith("home") else "away"
            line = float(key[4:])
            margin = (h - a) if side == "home" else (a - h)
            if margin + line > 0:
                ah[key] += p
    out["over"] = {k: round(v, 6) for k, v in over.items()}
    out["ah"] = {k: round(v, 6) for k, v in ah.items()}
    return out


def load_coef(*, league: str, as_of=None) -> tuple[dict | None, str]:
    """🔴🔴 계수 판을 읽는다 — **없으면 `(None, 사유)`**(손값으로 안 돈다 · §0).

    🔴 판을 고르는 곳은 `app/core/versions.py` 하나다(L3 · as_of 이전 최신).
    """
    from app.core import versions as _v
    box = _v.path_of(COEF_TABLE, str(league).replace(":", "_"))
    try:
        got, why = _v.pick(box, as_of=as_of)
    except ValueError as exc:
        return None, f"🔴 계수 판 없음 — {exc}"
    if not got or not all(str(n) in got for n in ("b0", "b1")):
        return None, (f"🔴 `{league}` **계수 판이 없다**({why}) — 확률을 만들지 "
                      f"않는다(`tools/fit_probfloor.py` 로 적합해야 한다)")
    return dict(got), f"계수 {why}"
