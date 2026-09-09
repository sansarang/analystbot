"""[MKT-5 2026-09-09] 우리와 시장의 괴리를 **변수**로 등록한다.

🔴 **왜 자료가 아니라 변수인가.** 시장 확률을 판정 입력(자료15)으로 줘 봤고
   A/B 가 막았다 (실판정 4경기 × 2회):
       |p − 시장| 중앙값 OFF 0.0163 → ON 0.0061 · 평균 0.0187 → 0.0060
       수축률 **+67.9%** · ON 반복이 전부 동일값(0.53/0.53 · 0.55/0.55 …)
   프롬프트에 "베끼지 마라 · 시장은 정답이 아니다"를 명시했는데도 판정이
   시장 숫자에 고정됐다. **앵커링이 지시보다 강하다.**

✅ 변수는 **판정이 끝난 뒤** 만들어진다. `p_home` 이 이미 확정된 다음이라
   오염 경로가 구조적으로 없다. 그리고 이 시스템은 변수를 이미
   원장에 적재하고(`variable_ledger`), 채점하며(`realized`/`actual`),
   **자료14가 다음 회차에 조사한다** — 사용자가 원한 "왜 갈렸는가"가 거기서 나온다.

📐 **경계는 실측이 정했다** (운영 원장, 시장값 있는 141경기):
       |차| 0~2%p   n=23  우리 47.8% · 시장 47.8%
       |차| 2~4%p   n=20  우리 55.0% · 시장 55.0%
       |차| 4~8%p   n=39  우리 51.3% · 시장 43.6%
       |차| 8%p+    n=59  우리 49.2% · 시장 **69.5%**
   **8%p 초과에서만 시장이 이긴다.** 그 아래에서 변수를 내면 잡음이고,
   잡음이 잦으면 변수 대장이 죽는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 이 값을 **넘을 때만** 변수를 낸다.
#  ⚠️ `settings.market_divergence_pp`(4.0)와 **다른 값이고 목적도 다르다** —
#     그것은 "추천할 만한가"(MKT-3 게이트), 이것은 "시장이 이기는 구간인가"다.
#     같은 값으로 묶으면 한쪽을 고칠 때 다른 쪽이 조용히 따라 움직인다.
DIVERGENCE_PP = 8.0

#: 8%p 초과 구간에서 **시장 방향이 맞았던 비율** (n=59, 운영 원장 실측).
#  같은 구간에서 우리는 49.2% 였다. 지어낸 수가 아니다.
MARKET_WIN_RATE_PP8 = 0.695


def divergence_variable(jg: dict) -> str | None:
    """괴리 변수 한 줄. 낼 것이 없으면 None.

    ⚠️ **기반영 M 은 0.0%p 다.** 판정이 시장을 보지 않았으므로 이 리스크는
       `p_home` 에 반영된 적이 없다. 0 이 아닌 값을 적으면 변수 예산
       (`check_budget`: M 합 ≤ |p−0.50|)을 거짓으로 잡아먹는다.
    ⚠️ 근거를 `시장 기준선` 으로 적어 **판정이 낸 변수와 출처가 구분**되게 한다.
    """
    mkt, ours = jg.get("p_market_send"), jg.get("p_claude")
    if mkt is None or ours is None:
        return None
    try:
        gap_pp = (float(ours) - float(mkt)) * 100.0
    except (TypeError, ValueError):
        return None
    if abs(gap_pp) <= DIVERGENCE_PP:
        return None
    # 괴리가 실현된다 = **시장이 맞았다**. 그러므로 방향은 시장 쪽이다.
    side = "홈" if float(mkt) > 0.5 else "원정"
    logger.info("[market-var] game=%s 괴리 %.1f%%p — 시장 %s 쪽 (변수 등록)",
                jg.get("game_id"), gap_pp, side)
    return (f"우리와 시장이 {abs(gap_pp):.1f}%p 갈렸다"
            f"(우리 {float(ours) * 100:.0f}% vs 시장 {float(mkt) * 100:.0f}%) — "
            f"발생 시 {side} 방향 약 {abs(gap_pp):.1f}%p · "
            f"발생 확률 {MARKET_WIN_RATE_PP8 * 100:.0f}% · "
            f"현재 p에 0.0%p 기반영 · 근거 시장 기준선")


def attach(jg: dict) -> bool:
    """판정의 `변수` 목록 끝에 괴리 변수를 덧붙인다. 붙였으면 True.

    🔴 **반드시 판정 뒤·변수 적재 앞에서 부른다.** 판정 앞에서 부르면
       프롬프트에 시장이 실려 앵커링이 되살아난다(MKT-4 A/B 참고).
    """
    line = divergence_variable(jg)
    if not line:
        return False
    m = jg.get("matchup")
    if not isinstance(m, dict):
        return False
    vs = list(m.get("변수") or [])
    if any("시장 기준선" in str(v) for v in vs):
        return False                      # 재판정에서 두 번 붙이지 않는다
    m["변수"] = vs + [line]
    return True


#: 괴리 변수를 다른 변수와 가르는 표식. `divergence_variable` 이 근거로 적는다.
SOURCE_TAG = "시장 기준선"


def is_divergence(raw: str) -> bool:
    """이 변수가 괴리 변수인가. 표식 하나로 가른다(사본 금지)."""
    return SOURCE_TAG in str(raw or "")


def realized_of(side: str | None, home_score, away_score) -> bool | None:
    """[MKT-6] 괴리가 현실화됐는가 = **시장 방향이 이겼는가**. 모르면 None.

    🔴 이 변수는 채점이 가장 쉽다 — 그런데 `variable_ledger.grade()` 는
       `subject_kind` 가 `pitcher`/`team` 일 때만 실측을 조회해서, 괴리 변수는
       `threshold_of → None` · `judge_realized(None, None) → unverifiable` 로
       **전건이 검증불가로 쌓였다.** 만들어 놓고 재지 않는 것은 이 저장소가
       가장 자주 데인 형태다.

    ⚠️ **모르는 것을 False 로 적지 않는다.** 점수가 없거나 무승부면 None 이다.
       NPB 는 무승부가 있고, 그때 "방향이 맞았다"고 할 수 없다.
    """
    if side not in ("home", "away") or home_score is None or away_score is None:
        return None
    try:
        h, a = int(home_score), int(away_score)
    except (TypeError, ValueError):
        return None
    if h == a:
        return None
    return (h > a) if side == "home" else (a > h)
