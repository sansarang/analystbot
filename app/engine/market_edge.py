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


# ═══════════════ [PA-22 2026-09-17 · 지시문 2단계] 시장 확률 위생
#
# 🔴 **검사 위치를 나눈다.** 지시문은 "p_mkt 합이 100±0.5 아니면 폐기"라고
#    적었는데, 그건 **디빅된 확률**을 전제한 문장이다. 우리가 저장하는 것은
#    배당 **원값**이라 합이 마진만큼 100 을 넘는 것이 정상이다.
#    실측 2026-09-17 (48h · h2h 묶음 523개):
#      합 100±0.5 안 0 · 밖 523 · 내재확률 합 101.5 ~ 105.1 ~ 109.0 %
#    지시문 숫자를 원값에 그대로 걸면 **배당이 523/523 전부 폐기**되고
#    전 경기가 보드 고정이 된다 — "조용한 0"이 바로 그 모양이다.
#    → 사용자 결정 2026-09-17: 원값은 마진 범위 · 디빅 후 합 100±0.5.

#: 원값 마진 허용 범위(%). 하한 100 초과 — 마진 0 인 북은 실제로 없다.
#  상한은 실측(최대 109.0)에 여유를 둔 값이다.
MARGIN_MIN_PCT, MARGIN_MAX_PCT = 100.5, 115.0

#: 디빅 뒤 합 허용 오차(지시문 2단계 숫자 그대로).
DEVIG_TOL = 0.005


def break_even(odds) -> float | None:
    """[MKT-4 2026-09-17] **요구 확률** — 그 배당이 본전이 되는 확률(1/배당).

    🔴 **디빅 확률과 다른 값이다.** 디빅은 마진을 **뺀** 시장의 진짜 생각이고,
       요구 확률은 마진을 **포함한** 우리가 넘어야 할 선이다. 둘을 한 이름으로
       부르면 다시는 못 가른다.
       실측 예(목표 분석 2026-09-17): KIA 1.49 → 디빅 62.3% · 요구 **67.1%**.
       우리 63% 는 방향은 맞지만(62.3 ≈ 63) **값은 없다**(63 < 67.1).
    ⚠️ 1.0 이하·숫자 아님이면 **None** 이다. 그 규약의 원본은
       `pick_ledger._implied_prob` 다 — 여기서 다시 적지 않는다(사본 금지).
       ⚠️ 모듈 최상단에서 들이면 순환이다(`pick_ledger` 가 이 모듈을 쓴다).
    """
    from app.engine.pick_ledger import _implied_prob

    p = _implied_prob(odds)
    return None if p is None else round(p, 4)


def price_edge_pp(p_ours: float | None, odds) -> float | None:
    """[MKT-4] **가격 대비 엣지**(%p) = 우리 확률 − 요구 확률.

    음수면 "방향은 맞아도 가격이 엣지를 다 먹었다"는 뜻이다.
    🔴 게이트를 바꾸지 않는다 — 이 값은 **보여주는 숫자**다.
    """
    be = break_even(odds)
    if be is None or p_ours is None:
        return None
    return round((float(p_ours) - be) * 100, 1)


def margin_pct(odds: dict | None) -> float | None:
    """배당 원값의 내재확률 합(%). 못 재면 None — 0 으로 읽지 않는다."""
    raw = []
    for v in (odds or {}).values():
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 1.0:
            raw.append(1.0 / f)
    if len(raw) < 2:
        return None
    return round(sum(raw) * 100, 2)


def margin_ok(odds: dict | None) -> bool:
    """마진이 정상 범위인가. 🔴 **범위 밖은 만들어진 값이거나 못 쓸 값이다.**

    ⚠️ 이 검사를 통과 못 하면 `market_missing` 이다 — 확률을 지어내지 않는다.
    """
    m = margin_pct(odds)
    return m is not None and MARGIN_MIN_PCT <= m <= MARGIN_MAX_PCT


def devig_ok(probs: dict | None) -> bool:
    """디빅 결과 합이 1 인가(지시문 2단계의 100±0.5). 못 재면 False."""
    if not probs:
        return False
    try:
        return abs(sum(float(v) for v in probs.values()) - 1.0) <= DEVIG_TOL
    except (TypeError, ValueError):
        return False


def placeholder_suspect(probs: dict | None, others: list | None) -> bool:
    """다른 경기가 **소수점까지 같은 확률**이면 자리표(placeholder)를 의심한다.

    🔴 실사고: SEA@ATH 40.9/59.1 이 두 경기에 그대로 들어왔다. 서로 다른
       경기가 소수 넷째 자리까지 같을 수는 없다 — 소스가 값을 못 줘서
       앞 경기 값을 되풀이한 것이다.
    ⚠️ **폐기하지 않는다. 표시만 한다** — 우연히 같을 가능성이 0은 아니고,
       판단은 원장을 보는 사람이 한다.
    """
    if not probs:
        return False
    me = tuple(sorted((k, round(float(v), 4)) for k, v in probs.items()))
    for o in (others or []):
        if not o:
            continue
        try:
            it = tuple(sorted((k, round(float(v), 4)) for k, v in o.items()))
        except (TypeError, ValueError):
            continue
        if it == me:
            return True
    return False


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

    # 시장이 다른 쪽을 우세로 보는가.
    # 🔴 방향만 보면 과하게 걸린다. 실측 2026-08-31 드라이런:
    #    Arsenal 우리 원정 47% vs 시장 원정 46.9% — 확률은 사실상 같은데
    #    argmax만 갈려 "시장이 더 확신"으로 분류되고 확신도가 강등됐다.
    #    시장이 **의미 있는 폭으로** 다른 쪽을 선호할 때만 센다.
    market_side = max(("home", "away"), key=lambda s: imp.get(s, 0.0))
    lead = imp.get(market_side, 0.0) - market_p
    opposite = market_side != favored and lead * 100 >= DIVERGENCE_PP

    if opposite or diff <= -DIVERGENCE_PP:
        out["classification"] = CLS_MARKET_AHEAD
        out["note"] = ("⚠️ 시장이 더 확신 — 검토 필요 "
                       f"(우리 {p_ours:.0%} vs 시장 {market_p:.0%}"
                       + (f", 시장은 {market_side} 선호 +{lead * 100:.1f}%p"
                          if opposite else "") + ")")
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


def our_side_prob(jg: dict) -> float | None:
    """우세 쪽에 대한 **우리** 확률.

    🔴 **`1 - p_home`은 축구에서 원정 확률이 아니다.** 무승부가 있어 셋으로
       갈리기 때문이다. 실측 2026-08-31 드라이런: Lecce vs Roma 원정 40%를
       68%(=1-0.32)로 읽어 괴리가 +3.4%p 대신 +31.4%p로 부풀었고, 그대로면
       "다 아는 픽"이 최상급 엣지 후보로 올라갔을 것이다.

       축구는 `p_away`를 그대로 쓴다. 야구는 무승부가 없어 2분이므로
       `1 - p_home`이 맞다.
    """
    m = jg.get("matchup") or {}
    favored = m.get("우세")
    if favored not in ("home", "away"):
        return None
    p_home = jg.get("p_claude")
    if p_home is None:
        return None
    if favored == "home":
        return float(p_home)
    # 3분(축구)이면 원정 확률이 따로 있다 — 있으면 그것이 답이다.
    for src in (jg, m):
        pa = (src or {}).get("p_away")
        if pa is not None:
            return float(pa)
    return 1.0 - float(p_home)          # 2분(야구)


def apply(jg: dict, odds: dict | None = None) -> dict:
    """판정 확정 후 호출. jg에 분류 결과를 얹고 요약을 돌려준다.

    ⚠️ **판정 확률(p_claude)을 바꾸지 않는다.** 이 단계는 분류·표기이며
       확률에 손대지 않는다. 확신도만 (a)에서 1단계 강등한다 — 그것이
       거부권 경로로 이어져 추천 자격을 잃게 하는 설계다.
    """
    p_ours = our_side_prob(jg)
    favored = (jg.get("matchup") or {}).get("우세")
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
