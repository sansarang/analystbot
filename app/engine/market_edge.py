"""[v1.1 4단계] 시장 괴리 3분류 + 엣지 후보. **판정 확정 후 사후 처리 전용.**

이 시스템의 상품은 "이길 팀 찾기"가 아니라 **"시장이 저평가한 팀 찾기"** 다.
수익의 원천은 적중률이 아니라 시장과의 정보 격차다.

  실측 근거 (2026-08-30):
    NC형  판정 68% vs 시장 52%(배당 1.81) — 괴리 +16%p, 검증 통과, **적중**
    PHI형 판정 66% vs 시장 65%            — 맞아도 남는 게 없는 "다 아는 픽"
    SF형  판정 55% vs 시장 역방향          — 시장이 옳았음, **패스가 정답**

🔴 **배당은 판정·폼·서술 입력으로 절대 흐르지 않는다.**
   이 모듈은 판정이 확정·저장된 **뒤에만** 호출되며, 판정 경로(team_form·
   matchup·prompts)는 이 모듈을 import 하지 않는다 — import 경계 테스트로 강제.
   섞이면 "우리 판정"이 사실은 시장을 베낀 것이 되고, 그 순간 괴리 측정 자체가
   무의미해진다.

⚠️ 배당이 없으면(`odds=None`) 아무것도 하지 않는다. 확률 게이트만으로 동작하는
   기존 설계 그대로다 — 배당 수집 실패가 추천을 막지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 괴리 임계 — 이 문서 범위에서 바꾸지 않는다 (완료 판정 후 별도 지시).
DIVERGENCE_PP = 8.0

# edge_status 값
EDGE_NONE = "none"
EDGE_CANDIDATE = "candidate"
EDGE_CONFIRMED = "confirmed"     # 6단계 딥서치 통과 후에만
EDGE_REJECTED = "rejected"

# 분류
CLS_MARKET_AHEAD = "market_divergence"   # (a) 시장이 더 확신 — 검토 필요
CLS_NEUTRAL = "neutral"                  # (b) |괴리| < 8%p
CLS_EDGE = "edge_candidate"              # (c) 우리가 더 확신


def implied_probs(odds: dict) -> dict | None:
    """배당 → 마진 제거한 암시 확률.

    `odds`: {"home": 1.81, "away": 2.05, "draw": 3.40} (draw는 축구만)

    ⚠️ **마진을 반드시 제거한다.** 1/배당을 그대로 쓰면 합이 1을 넘어(북메이커
       마진) 우리 확률과 비교할 수 없다. 실측: 합이 1.05~1.08이 보통이므로
       그대로 비교하면 시장을 5~8%p 과대평가한다 — 괴리 임계가 8%p인데
       그만큼을 마진이 먹어버린다.
    """
    if not odds:
        return None
    raw = {}
    for k, v in odds.items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 1.0:
            raw[k] = 1.0 / f
    if not raw or "home" not in raw or "away" not in raw:
        return None
    total = sum(raw.values())
    if total <= 0:
        return None
    # ⚠️ 각각 반올림하면 합이 1.0에서 어긋난다(2-way 최대 1e-4, 3-way 1.5e-4).
    #    괴리를 %p로 재는데 확률 합이 안 맞으면 그 %p가 미세하게 틀린다.
    #    **마지막 항을 잔차로 채워** 합을 정확히 맞춘다 (soccer_trial.normalize와 같은 처리).
    keys = list(raw)
    out = {k: round(raw[k] / total, 4) for k in keys[:-1]}
    out[keys[-1]] = round(1.0 - sum(out.values()), 4)
    return out


def classify(p_ours: float | None, favored: str | None,
             odds: dict | None) -> dict:
    """판정 vs 시장 3분류. 반환은 항상 dict — 배당이 없으면 값이 None이다.

    `p_ours`: **우세 쪽** 확률 (홈 픽이면 p_home, 원정 픽이면 1-p_home).
    `favored`: "home" | "away" | "박빙"
    """
    out = {"market_prob": None, "divergence_pp": None,
           "classification": None, "edge_status": EDGE_NONE, "note": None}
    imp = implied_probs(odds or {})
    if imp is None or p_ours is None or favored not in ("home", "away"):
        return out                      # 배당 미수집 — 확률 게이트만으로 간다
    market_p = imp.get(favored)
    if market_p is None:
        return out
    out["market_prob"] = market_p
    diff = round((p_ours - market_p) * 100, 1)
    out["divergence_pp"] = diff

    # 시장이 다른 쪽을 우세로 보는가 — 방향 불일치는 값 차이보다 강한 신호다
    market_side = max(("home", "away"), key=lambda s: imp.get(s, 0.0))
    opposite = market_side != favored

    if opposite or diff <= -DIVERGENCE_PP:
        out["classification"] = CLS_MARKET_AHEAD
        out["note"] = ("⚠️ 시장이 더 확신 — 검토 필요 "
                       f"(우리 {p_ours:.0%} vs 시장 {market_p:.0%}"
                       + (", 방향 반대" if opposite else "") + ")")
    elif diff >= DIVERGENCE_PP:
        out["classification"] = CLS_EDGE
        out["edge_status"] = EDGE_CANDIDATE
        # 6단계 딥서치가 관문이다. 그 전에는 승격하지 않는다 —
        # 검증 없는 엣지를 최상위 등급으로 내보내면 SF형에 걸린다.
        out["note"] = (f"🎯 엣지후보 · 검증대기 (우리 {p_ours:.0%} vs "
                       f"시장 {market_p:.0%}, +{diff:.1f}%p)")
    else:
        out["classification"] = CLS_NEUTRAL
    return out


def demote_confidence(conf: str | None) -> str | None:
    """확신도 1단계 강등 — 시장이 더 확신할 때. 'low'는 더 내리지 않는다."""
    return {"high": "medium", "medium": "low"}.get(conf, conf)


def apply(jg: dict, odds: dict | None = None) -> dict:
    """판정 확정 후 호출. jg에 분류 결과를 얹고 요약을 돌려준다.

    ⚠️ **판정 확률(p_claude)을 바꾸지 않는다.** 이 단계는 분류·표기이며
       확률에 손대지 않는다. 확신도만 (a)에서 1단계 강등한다 — 그것이
       거부권 경로로 이어져 추천 자격을 잃게 하는 설계다.
    """
    p_home = jg.get("p_claude")
    favored = (jg.get("matchup") or {}).get("우세")
    p_ours = None
    if p_home is not None and favored in ("home", "away"):
        p_ours = float(p_home) if favored == "home" else 1.0 - float(p_home)
    res = classify(p_ours, favored, odds)
    jg["market_prob"] = res["market_prob"]
    jg["divergence_pp"] = res["divergence_pp"]
    jg["edge_status"] = res["edge_status"]
    jg["market_note"] = res["note"]
    if res["classification"] == CLS_MARKET_AHEAD:
        jg["market_divergence"] = True
        before = jg.get("judge_confidence")
        jg["judge_confidence"] = demote_confidence(before)
        logger.info("[market] 시장 우위 — 확신도 강등 %s→%s game=%s",
                    before, jg["judge_confidence"], jg.get("game_id"))
    return res
