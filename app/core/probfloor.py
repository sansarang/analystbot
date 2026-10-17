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
# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **Elo 바닥 쪽을 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*
# ══════════════════════════════════════════════════════════════════════
#
#  🔴 `floor_of`(Elo → 바닥 승무패) · `lambdas`(바닥을 λ 로 번역) ·
#     `compute`(바닥 + 잔차 → 확률) · `load_coef`(적합 계수) — 넷이 한 묶음이고
#     **전부 Elo 바닥 경로**다. 🔴 오늘 지은 계약(`test_bl1`)이 `compute` 가
#     지운 `base.triple_of` 를 부르는 것을 잡았다 — **라이브에서 카드가 죽는
#     자리**였다.
#  🔴 **남긴 것** — `score_grid`(저장된 격자를 글로) · `markets_of`(그 격자
#     하나에서 핸디·오버·BTTS 를 센다). 둘은 Elo 를 안 쓴다.
#     ⚠️ 지금 격자(`card.scores`)는 **비어 있다**(λ 를 지웠다) → 카드가 ⬜ 로
#        적는다. 그 둘을 지우면 격자가 생겼을 때 셀 곳이 없어진다.

# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **상성·시뮬과 함께 지웠다** — 사용자 지시 2026-10-17
# ══════════════════════════════════════════════════════════════════════
#
#  > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**
#
#  🔴 아래 함수들은 λ(기대 득점)를 세우던 재료다 — 리그 평균·홈/원정 배율·
#     λ 기울기 이분법. 승무패가 `flat_prob`(1/3 균등 + 변수)로 바뀌고
#     λ·오버·스코어가 비워지면서 **부르는 곳이 0** 이 됐다(#2).
#  ⚠️ `app/core/sim.py`(몬테카를로) 모듈은 **안 지웠다** — `tools/` 의 백필·
#     비교 측정 도구들이 그 모형을 읽는다(운영이 안 부를 뿐이다).



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


#: 🔴🔴 **λ 후보 항**(지시 §4·§9) — 전진 선택이 **이 목록만** 흔든다.
#  ⚠️ `pb_home` 은 더하는 항이 아니라 **diff 를 깎는 상호작용**이다(§9 F1).
#  🔴 `bench_d` 는 여기 **없다** — λ 식이 아니라 시뮬 60분 이후 배율이다(§8 · C8-2).
TERMS: tuple[str, ...] = ("rest_d", "load_d", "cup_d", "pb_home",
                          "abs_d", "form3_d")

#: 🔴 항 → 계수 이름(지시 §4 의 그 글자) · `pb_home` 은 c3 상호작용이다
TERM_COEF: dict[str, str] = {"rest_d": "c1", "load_d": "c2", "cup_d": "c5",
                             "abs_d": "c4", "form3_d": "c6",
                             "pb_home": "c3"}


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


#: 🔴 카드가 쓰는 기준선 — 바꾸면 카드 글이 바뀐다(스냅샷이 빨개진다)
AH_LINES = (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)
TOTAL_LINES = (0.5, 1.5, 2.5, 3.5, 4.5)
#: 🔴🔴 **국내 보드의 0.5 단위 전부**(의심 검증 v2 §1-2 · 정수 기준선은 승·무·패
#   세 갈래다). ⚠️ 카드는 위 `AH_LINES` 만 쓴다 — 이 넓은 표는 **근사 보드**
#   (`tools/fit_board_hist.py`)가 *"50% 에 가장 가까운 기준선"* 을 고를 때 쓴다.
AH_LINES_FULL = tuple(x / 2 for x in range(-6, 7))
TOTAL_LINES_FULL = tuple(x / 2 for x in range(1, 12))


def markets_of(grid: dict, *, ah_lines: tuple | None = None,
               total_lines: tuple | None = None) -> dict:
    """🔴🔴 **P2** — 승무패·오버·핸디·BTTS 를 **그 격자 하나**에서 센다.

    ⚠️ 한 마켓이라도 다른 곳에서 세면 카드의 두 줄이 **서로 다른 말**을 한다.
    🔴 `ah_lines`·`total_lines` 는 **세는 기준선만** 바꾼다(세는 규칙은 하나다) —
       근사 보드가 0.5 단위 **전부**를 물어야 해서 열어 뒀다(§1-4). 기본값은
       카드가 쓰는 표이므로 **카드 글은 안 바뀐다**.
    """
    out: dict = {"home": 0.0, "draw": 0.0, "away": 0.0,
                 "btts_yes": 0.0, "btts_no": 0.0,
                 "over": {}, "ah": {}}
    tot_lines = tuple(total_lines or TOTAL_LINES)
    over = dict.fromkeys(tot_lines, 0.0)
    # 🔴 **양쪽 줄을 다 센다** — 약팀이 홈일 수도 원정일 수도 있다(§11).
    #  ⚠️ 실사고 2026-10-12: 홈 줄만 만들어 `away+0.5` 에서 터졌다(e2e 가 잡았다).
    lines = tuple(ah_lines or AH_LINES)
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
