"""[v1.1 5단계] 가치 게이트 — 추천의 2차 문. **사후 전용, 판정 비개입.**

확률만 보면 "높은데 먹을 게 없는 픽"을 통과시키고 "경계 확률인데 가치 있는 픽"을
버린다.

  실측 사례 (2026-08-30):
    PHI    0.66 × 1.39 = 0.92  → 확률은 통과인데 **헛통과**
    BAL    0.63 × 1.70 = 1.07  → 경계 확률인데 **헛탈락**
    닛폰햄  0.61 × 1.43 = 0.87  → 같은 유형

🔴 **기존 추천 체계를 바꾸지 않는다.** 확률 게이트(야구 58/63, 축구 55/60/75)와
   확신도 거부권으로 [추천]/[보드만]/[잠정]이 정해지는 현행 로직은 그대로다.
   이 모듈은 **그 위에 얹는 표기**이며, 배당이 없으면 아무 일도 하지 않는다.

⚠️ 배당은 판정·폼·서술 입력으로 흐르지 않는다 (4단계와 같은 격리 원칙).
"""
from __future__ import annotations

#: 가치 하한 — 이 문서 범위에서 바꾸지 않는다.
VALUE_MIN = 1.05

# 카드 분류
CLS_EDGE = "엣지"
CLS_RECOMMENDED = "추천"
CLS_VALUE_WARN = "가치주의"
CLS_BOARD_ONLY = "보드만"

#: 별표 사다리 (야구 기준). 우세팀 확률로 계산한다.
_STAR_LADDER = ((0.68, "★★★★★"), (0.63, "★★★★"), (0.58, "★★★"),
                (0.53, "★★"), (0.0, "★"))


def stars(p: float | None, *, provisional: bool = False) -> str:
    """확률 → 별점. 잠정 카드는 뒤에 "(잠정)"을 병기한다."""
    if p is None:
        return ""
    mark = next(s for lo, s in _STAR_LADDER if p >= lo)
    return f"{mark} (잠정)" if provisional else mark


def value(p: float | None, odds: float | None) -> float | None:
    """p × 배당. 배당이 없으면 None — **0이 아니다.**

    0으로 두면 "가치 없음"과 "모름"이 같아져, 배당 수집 실패가 곧 탈락이 된다.
    """
    if p is None or odds is None:
        return None
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    return round(float(p) * o, 4) if o > 1.0 else None


def required_odds(p: float | None) -> float | None:
    """이 확률에서 가치 하한을 넘기려면 필요한 배당. 배당 미수집 카드에 쓴다."""
    if not p:
        return None
    return round(VALUE_MIN / float(p), 2)


def passes_value(p: float | None, odds: float | None) -> bool | None:
    """가치 게이트 통과 여부. **None은 "판정 불가"(배당 미수집)다.**

    ⚠️ None을 False로 취급하면 배당 수집 실패가 추천을 막는다 — 지시문이
       금지한 동작이다. 호출부는 None을 "게이트 건너뜀"으로 다뤄야 한다.
    """
    v = value(p, odds)
    return None if v is None else v >= VALUE_MIN


def classify(*, probability_ok: bool, vetoed: bool, p: float | None,
             odds: float | None, edge_status: str | None = None) -> str:
    """카드 4분류. 순서가 규율이다.

    거부권 → 확률 → 가치 → 엣지 순으로 본다. 거부권이 확률보다 먼저인 이유는
    확신도 '하'가 확률이 아무리 높아도 탈락이기 때문이다(기존 규율).
    엣지는 **추천을 대체하지 않고** 그 위에 붙는 라벨이다.
    """
    if vetoed or not probability_ok:
        return CLS_BOARD_ONLY
    ok = passes_value(p, odds)
    if ok is False:
        return CLS_VALUE_WARN          # 확률 통과·가치 미달 — 추천 아님
    # ok is True 이거나 None(배당 미수집) → 추천 자격 유지
    if edge_status == "confirmed":
        return CLS_EDGE                # 6단계 딥서치를 통과한 것만
    return CLS_RECOMMENDED


def label(cls: str, *, divergence_pp: float | None = None) -> str:
    """카드에 붙일 라벨 문자열."""
    if cls == CLS_EDGE:
        gap = f" +{divergence_pp:.1f}%p" if divergence_pp else ""
        return f"[🎯엣지{gap}]"
    if cls == CLS_VALUE_WARN:
        return "[⚠️가치주의]"
    if cls == CLS_RECOMMENDED:
        return "[✅추천]"
    return ""
