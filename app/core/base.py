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


def we(dr: float) -> float:
    """🔴 §3-1 — `We = 1 / (10^(−dr/400) + 1)`. ⚠️ `dr` 은 **Elo 점수 차**다.

    실측 검사(계약): `dr=0 → 0.5` · `dr=+400 → 0.909`.
    """
    return 1.0 / (10.0 ** (-float(dr) / 400.0) + 1.0)


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def triple_of(kind: str, dr: float) -> tuple[ProbTriple | None, str]:
    """🔴 §3-2 — 순서형 로짓으로 `dr` 을 승·무·패로 나눈다. `(확률, 사유)`.

    🔴 **같은 대회 유형 계수만** 쓴다(§3 "다른 대회 값 금지"). 없으면 `(None, 사유)`.
    ⚠️ 계수가 `venue: home_only` 면 **중립 경기에 쓰지 않는다** — 그 자료(중립 줄)가
       결과순으로 적혀 있어 적합에서 빠졌다(`config/base_model.yaml` 머리말).
    """
    m = rules.base_model(kind)
    if not m:
        return None, f"`{kind}` 대회 유형의 계수가 없다 — 적합한 적이 없다"
    try:
        c1, c2, b = float(m["c1"]), float(m["c2"]), float(m["b_dr"])
    except (KeyError, TypeError, ValueError):
        return None, f"`{kind}` 계수 칸이 깨졌다({sorted(m)})"
    if float(m.get("logloss", 0.0)) >= float(m.get("logloss_base", 1e9)):
        return None, (f"`{kind}` 모형이 기준선보다 나쁘다"
                      f"({m.get('logloss')} ≥ {m.get('logloss_base')})")
    eta = b * float(dr) / 100.0
    lo, hi = _logistic(c1 - eta), _logistic(c2 - eta)
    hi = max(hi, lo)
    home, draw, away = 1.0 - hi, hi - lo, lo
    tot = home + draw + away
    got = ProbTriple(home=round(home / tot, 6), draw=round(draw / tot, 6),
                     away=round(1.0 - round(home / tot, 6) - round(draw / tot, 6), 6))
    return got, (f"순서형 로짓 `{kind}`(표본 {m.get('n')}경기 · 적합 "
                 f"{m.get('fitted_at')} · logloss {m.get('logloss')})")


def base_prob(*, kind: str, home_elo: float | None, away_elo: float | None,
              neutral: bool, source: str, data_date: str) -> BaseProb:
    """🔴 ① 한 경기의 기준 확률. ⚠️ 못 만들면 **사유를 담은 빈 BaseProb** 다."""
    if home_elo is None or away_elo is None:
        miss = [n for n, v in (("홈", home_elo), ("원정", away_elo)) if v is None]
        return BaseProb(why=f"{'·'.join(miss)} 팀 Elo 를 못 받았다", comp_kind=kind,
                        source=source, data_date=data_date)
    dr = float(home_elo) - float(away_elo)
    said = we(dr)
    if neutral:
        # 🔴 중립 경기엔 계수를 쓰지 않는다 — 적합 자료가 홈 개최뿐이다
        return BaseProb(why=("중립 경기다 — 계수는 홈 개최 경기로만 적합했다"
                             "(`venue: home_only`) · 승무패를 나누지 않는다"),
                        home_elo=home_elo, away_elo=away_elo, dr=dr,
                        comp_kind=kind, source=source, data_date=data_date, we=said)
    probs, why = triple_of(kind, dr)
    return BaseProb(probs=probs, why=why, home_elo=home_elo, away_elo=away_elo,
                    dr=dr, comp_kind=kind, source=source, data_date=data_date,
                    we=said)


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

    🔴 그 계수는 `config/base_model.yaml` 의 `ds_to_dr` 다. 지금은 **없다** —
       가치가 붙은 과거 경기 자료를 받은 적이 없다(§3 "가치 데이터가 없으면 이 모형은
       만들지 않는다"). ⚠️ 그래서 `moved=False` 로 **표시만** 한다.
    """
    m = rules.base_model(kind)
    coef = m.get("ds_to_dr")
    moved = False
    probs = base.probs
    if coef is not None and base.probs is not None and base.dr is not None:
        step = float(coef) * (delta_s.get(str(home), 0.0) - delta_s.get(str(away), 0.0))
        got, said = triple_of(kind, base.dr + step)
        if got is not None:
            probs, moved, why = got, True, f"{why} · ΔS→dr {step:+.1f}점({said})"
    elif coef is None:
        why = (f"{why} · 🔴 ΔS→dr 환산 계수가 없다 — **확률을 움직이지 않았다**"
               f"(전력 변화율만 보인다)")
    return AdjProb(probs=probs, why=why, deltas=deltas, delta_s=delta_s,
                   strength_pct=strength_pct, moved=moved,
                   measured=bool(delta_s), estimated_players=estimated)
