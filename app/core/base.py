"""🔴🔴 **① 기준 확률 · ② 라인업 보정** — 네 층 지시서 §3·§4.

## 이 파일이 하는 일

| 층 | 함수 | 입력 → 출력 |
|---|---|---|
| ① | `we()` | Elo 차 → 기대 득점률(§3-1 공식 그대로) |
| ① | `triple_of()` | Elo 차 + **그 대회 유형 계수** → 승·무·패 |
| ② | `strength_of()` | 선수 가치 목록 → `Σ log(가치)`(§4-4) |
| ② | `adjust()` | `ΔS` → 보정 확률 + 선수별 기여표(§4-5·6) |

🔴 **LLM 을 부르지 않는다**(§1 "①②④는 결정적 계산이다").
🔴 **실행 중 적합하지 않는다**(§3-2) — 계수는 `config/base_model.yaml` 에서만 온다.
⚠️ 계수가 없으면 숫자를 내지 않는다. "기준 없음 — 사유"가 맞는 결과다.
"""
from __future__ import annotations

import logging
import math

from app import rules
from app.core.schema import AdjProb, BaseProb, LineupDelta, ProbTriple, TeamKey

logger = logging.getLogger(__name__)

#: 🔴 §4-1 — 평소 XI 를 세는 최근 경기 수. ⚠️ 표본이 이보다 적으면 ② 를 건너뛴다
USUAL_XI_MATCHES = 5
MIN_USUAL_SAMPLE = 3
#: 🔴 §4-3 — 값 없는 선수를 채운 수가 이보다 많으면 ② 는 **표시만** 한다
MAX_ESTIMATED = 3
# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **Elo 부분만 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*
# ══════════════════════════════════════════════════════════════════════
#
#  🔴 이 파일에는 **두 가지**가 섞여 있었다:
#       ① Elo → 승·무·패 : `we`(기대승률) · `_logistic` · `triple_from` ·
#          `triple_of`(순서형 로짓) · `base_prob` — **지웠다**
#       ② 선수 전력(§4)  : `strength_of` · `fill_values` · `pct_change` ·
#          `adjust` · `_share` — **남긴다**(Elo 를 안 쓴다 · 오늘 XI 가 평소
#          XI 보다 얼마나 약/강한가를 **선수 가치**로 센다)
#  ⚠️ ② 는 `s2b_base._adjust`·`_deltas` 가 부른다 — 지우면 라인업 보정이 죽는다.



# ══════════════════════════════════════════════════════════════════
# ② 라인업 보정
# ══════════════════════════════════════════════════════════════════


def strength_of(values: list[float]) -> float:
    """🔴 §4-4 — `S = Σ log(가치)`. 포지션 가중은 **없이 시작한다**(지시서 원문).

    ⚠️ 0·음수 가치는 **버린다**(로그가 없다) — 버린 수는 호출부가 센다.
    """
    return float(sum(math.log(v) for v in values if v and v > 0))


def fill_values(names: list[str], table: dict[str, float],
                pool: list[float]) -> tuple[list[float], int, list[str]]:
    """🔴 §4-3 — 값 없는 선수는 **그 팀 평소 XI 가치의 하위 25%** 로 채운다.

    `(가치들, 채운 수, 채운 이름들)`. ⚠️ 채운 선수가 3명을 넘으면 호출부가 ② 를
    **표시만** 한다(판정에 쓰지 않는다).
    """
    floor = _quantile(sorted(v for v in pool if v > 0), 0.25)
    out: list[float] = []
    filled: list[str] = []
    for nm in names:
        got = table.get(nm)
        if got and got > 0:
            out.append(float(got))
            continue
        if floor <= 0:
            continue                    # 🔴 채울 바닥값조차 없다 — 그 선수는 빠진다
        out.append(floor)
        filled.append(nm)
    return out, len(filled), filled


def _quantile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    i = max(0, min(len(xs) - 1, int(round(q * (len(xs) - 1)))))
    return float(xs[i])


def pct_change(now: float, usual: float) -> float:
    """🔴 평소 대비 전력 변화율(%) — `ΔS` 를 사람 말로 바꾼 것뿐이다."""
    if usual == 0:
        return 0.0
    return round(100.0 * (now - usual) / abs(usual), 2)


def adjust(base: BaseProb, *, kind: str, delta_s: dict[str, float],
           strength_pct: dict[str, float], deltas: list[LineupDelta],
           home: TeamKey, away: TeamKey, estimated: int, why: str) -> AdjProb:
    """🔴 §4-5 — `ΔS` → 보정 확률. ⚠️ **환산 계수가 없으면 확률을 안 움직인다.**

    > `ΔS` → `dr` 환산 계수는 §3 선수단 가치 모형에서 같이 추정. 추정 못 하면
    > *"평소 대비 전력 −x%"* 만 표시하고 **확률은 안 움직인다.**

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **계수가 생겼다 — 이제 확률을 움직인다**(사용자 지시 2026-10-06(6차) ②)
    ══════════════════════════════════════════════════════════════════

    > `ds_to_dr`(8.87 · R² 0.61)로 라인업 보정이 **확률을 움직이게** 한다. 카드 3c 에
    > *"라인업 보정 −1.2%p (환산 R² 0.61 · 표본 33)"* 형태로 **계수 신뢰도를 함께** 적는다.

    🔴 계수는 `config/base_model.yaml` 의 `ds_to_dr` 이고 `ds_fit` 이 그 **표본·R²** 를
       든다(`tools/fit_ds_to_dr.py` 가 적는다 — 실행 중 적합 금지).
    ⚠️ R² 는 **0.61** 이다(반쯤 설명한다) — 그래서 카드가 그 수를 **숨기지 않는다**.
       🔴 계수가 없으면 전처럼 *"전력 변화율만"* 이다.
    """
    m = rules.base_model(kind)
    coef = m.get("ds_to_dr")
    fit = dict(m.get("ds_fit") or {})
    moved = False
    probs = base.probs
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **확률을 움직이는 가지를 지웠다** — 사용자 지시 2026-10-17
    # ══════════════════════════════════════════════════════════════════
    #
    #  > **elo 지워라**
    #
    #  ⚠️ 이 가지는 `ΔS`(전력 변화)를 **Elo 점수 차(`dr`)로 환산**해 `triple_of`
    #     (순서형 로짓)로 승·무·패를 다시 내던 길이다. 🔴 Elo 를 지워
    #     `base.probs`·`base.dr` 이 **늘 `None`** 이므로 **영원히 안 돈다**.
    #  🔴 그래서 ② 는 이제 **전력 변화율만** 낸다(확률을 안 움직인다) — 그것이
    #     `measured=False` 이고, 결장 무게는 변수 쪽이 그대로 든다.
    #  ⚠️ 전력 변화율(`strength_pct`)·선수별 기여(`deltas`)는 **그대로 낸다** —
    #     카드가 그 줄을 적는다(지우면 라인업 보정이 통째로 사라진다).
    if coef is None:
        why = (f"{why} · 🔴 ΔS→dr 환산 계수가 없다 — **확률을 움직이지 않았다**"
               f"(전력 변화율만 보인다)")
    # 🔴🔴 `measured` 는 **움직였을 때만** 참이다 — §4 마지막 줄이 *"그 영향은 ② 의
    #    확률 이동량이 대신한다"* 라고 적었다. ⚠️ 못 움직였는데 결장 무게를 0 으로
    #    하면 그 영향이 **아무 데도 없어진다**(지우는 것이 아니라 옮기는 규칙이다).
    return AdjProb(probs=probs, why=why, deltas=deltas, delta_s=delta_s,
                   strength_pct=strength_pct, moved=moved,
                   measured=bool(moved), estimated_players=estimated)


def _share(deltas: list[LineupDelta], shift: float, *, home: str, away: str,
           delta_s: dict[str, float]) -> list[LineupDelta]:
    """🔴🔴 팀 전체의 `%p` 를 **선수 줄마다** 나눠 적는다(지시서 ② 카드 꼴).

    🔴 쪼개는 식은 이동을 만든 식과 **같다**:
       `step = coef × (ΔS_home − ΔS_away)` 이므로 한 줄의 몫은
       `(홈이면 +ΔS, 원정이면 −ΔS) ÷ (ΔS_home − ΔS_away)` 다. 그 몫에 `%p` 를 곱한다.

    ⚠️ **몫이 1 을 크게 넘는 줄에는 `%p` 를 안 적는다.** 실측 2026-10-06: 김민재가
       빠지고(ΔS −17.16) 황희찬이 들어온(+16.09) 경기에서 두 줄의 몫이 ±16 이었다 —
       서로 **상쇄되는 큰 항목**이고, 그것을 `−19%p`·`+18%p` 로 적으면 거짓으로 읽힌다.
       🔴 그때는 `ΔS` 만 적고 그 사실을 카드가 말한다.
    """
    denom = float(delta_s.get(home, 0.0)) - float(delta_s.get(away, 0.0))
    out: list[LineupDelta] = []
    for d in deltas:
        key = str(d.team)
        mine = float(d.delta_s) * (-1.0 if key == away else 1.0)
        if abs(denom) < 1e-6 or shift == 0.0:
            out.append(d)
            continue
        part = mine / denom
        if abs(part) > 1.5:
            # 🔴 상쇄되는 큰 항목 — 쪼개지 않는다(사실만 남긴다)
            out.append(d)
            continue
        out.append(d.model_copy(update={"delta_home_pct": round(shift * part, 2)}))
    return out
