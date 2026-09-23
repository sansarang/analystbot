"""[v1.4 STEP 8] ⑧ p_code — **시장 뼈대 + 조정. 그리고 픽은 여기서 갈린다.**

🔴 양쪽 확률을 시장에서 받아 조정을 **반대칭으로** 얹고, 더 높은 쪽을 고른다.
   `p_code_pick` 은 그 픽 기준이라 언제나 절반 이상이다.
   ⚠️ 축구는 무승부 질량이 있어 `1 − 홈` 이 원정이 **아니다** — 그래서 한쪽을
      빼서 만들지 않고 ②가 낸 `p["away"]` 를 그대로 받는다.
   [SIDE-2 2026-09-23] 종전에는 ①이 픽을 정하고 여기서 그 쪽 확률만 냈다.
   ①은 전 괴리 구간에서 시장보다 나쁜데(FORKS F-22) 확률은 시장에서 나오므로,
   둘이 갈리면 **고른 쪽 승률이 50% 미만**이 됐다(실측 30일 29.3%).
   사전값(`p_prior`)은 **더하지 않는다** — 그것은 ③ 게이트와 카드 서술의 몫이다
   (`prior.py` 규약 · CLAUDE.md).
🔴 `model_w = 0` 축(`p_model`)은 **자리만** 두고 쓰지 않는다.
⚠️ 단위: `sum_adj_pp` 는 %p, `p_code_pick` 은 0~1 이다.
"""
from __future__ import annotations

import logging

from app.flow import rules as R

logger = logging.getLogger(__name__)

NODE = "n08_pcode"

P_MIN, P_MAX = 0.05, 0.95


def _ours_markets(model_probs: dict | None) -> dict:
    """`scoring.mlb_market_probs` 모양 → ⑪이 읽는 모양으로 옮긴다.

    🔴 **계산하지 않는다.** 분포의 원본은 `scoring` 이고 여기서는 이름만 맞춘다
       (사본 금지). 없는 마켓은 **넣지 않는다** — ⑪이 `None` 을 보고 건너뛴다.
    ⚠️ 라인 키가 JSON 을 거치면 문자열이 된다("7.5") — 숫자로 되돌린다.
    """
    mp = model_probs or {}
    out: dict = {}

    def _line(k):
        try:
            return float(k)
        except (TypeError, ValueError):
            return None

    for k, d in (mp.get("totals") or {}).items():
        line = _line(k)
        if line is None or not isinstance(d, dict):
            continue
        if d.get("Over") is not None:
            out.setdefault("total_over", {})[line] = float(d["Over"])
        if d.get("Under") is not None:
            out.setdefault("total_under", {})[line] = float(d["Under"])

    # 핸디는 **쪽이 네 가지**다(home_minus·away_plus·away_minus·home_plus).
    #   ⑪은 라인 하나에 확률 하나를 읽으므로 홈 기준(`home_minus`)만 싣는다 —
    #   원정 라인은 부호가 뒤집힌 같은 사건이라 ⑪이 배당 쪽에서 가른다.
    for k, d in (mp.get("spreads") or {}).items():
        line = _line(k)
        if line is None or not isinstance(d, dict):
            continue
        if d.get("home_minus") is not None:
            out.setdefault("ah", {})[line] = float(d["home_minus"])

    # 🔴 [MOD-1 2026-09-19] 팀토탈. ⑪의 후보 이름은
    #    `team_total_home_over` 꼴이다(`n11_value._structure_candidates`) —
    #    그 이름을 여기서 **새로 짓지 않고** 그쪽 규칙에 맞춘다.
    for side in ("home", "away"):
        for k, d in ((mp.get("team_totals") or {}).get(side) or {}).items():
            line = _line(k)
            if line is None or not isinstance(d, dict):
                continue
            for way in ("Over", "Under"):
                if d.get(way) is not None:
                    key = f"team_total_{side}_{way.lower()}"
                    out.setdefault(key, {})[line] = float(d[way])
    return out


async def run(state, ctx):
    """⑧ p_code — **확률을 내고, 그 확률이 픽을 정한다.**

    🔴 [SIDE-2 2026-09-23] 종전에는 ①이 정한 `pick_side` 의 시장 확률에
       조정을 더했다. ①은 시장보다 나쁘므로(FORKS F-22) 둘이 갈리면 산출이
       **"고른 쪽 승률 50% 미만"** 이 됐다 — 실측 30일 17/58 = 29.3%.
       이제 **홈 기준으로 계산하고 50% 를 넘는 쪽을 고른다.** 픽 확률은
       정의상 항상 0.5 이상이다.
    ⚠️ 되돌릴 길: `flow.pick_from: prior` 면 종전대로 ①이 픽을 정한다.
    """
    _p = (state.n02_market or {}).get("p") or {}
    p_home_mkt, p_away_mkt = _p.get("home"), _p.get("away")
    if p_home_mkt is None or p_away_mkt is None:
        # ⚠️ 시장이 없으면 픽도 못 정한다 — ①의 조사 방향을 그대로 둔다.
        #    `record.pick_of` 는 확률이 None 이라 어차피 원장에 안 적는다.
        state.pick_side = state.hyp_side
        state.n08_pcode = {"p_code_pick": None, "sum_adj_pp": 0.0,
                           "p_home": None, "p_away": None,
                           "p_model": None, "model_w": 0.0,
                           "reason": "시장 확률이 없다"}
        return state

    # 🔴 ⑦은 **홈 기준**으로 부호를 낸다(`_direction_of(d, "home")`).
    s_home = round(sum(a.get("pp", 0.0) for a in (state.n07_adjust or [])), 2)
    p_home = max(P_MIN, min(P_MAX, float(p_home_mkt) + s_home / 100.0))
    # 🔴 **축구는 `1 − 홈` 이 원정이 아니다**(무승부 질량). 양쪽을 따로 받아
    #    조정만 반대칭으로 얹는다. 야구는 `p_away = 1 − p_home` 이라 결과가
    #    같다 — 종목 분기를 새로 만들지 않는다.
    p_away = max(P_MIN, min(P_MAX, float(p_away_mkt) - s_home / 100.0))

    if str(R.get("pick_from", "probability")) == "prior":
        side = state.hyp_side or "home"
    else:
        side = "home" if p_home >= p_away else "away"
    state.pick_side = side

    p = p_home if side == "home" else p_away
    # ⚠️ 표시·⑫서술은 **픽 기준**을 본다 — 부호를 픽 쪽으로 돌려 싣는다.
    s = s_home if side == "home" else round(-s_home, 2)

    # 🔴 [2026-09-18] **파생 확률을 ⑪로 내려보낸다.** 여기까지 안 실으면
    #    ⑪의 구조 후보가 언제나 0 이고, `동의` 라벨이 만든 파생 가설이 쓰일
    #    자리가 없다(E2E 드라이런 2건이 그 상태였다).
    #    ⚠️ 우리가 계산하지 않는다 — `scoring` 이 낸 것을 이름만 맞춰 옮긴다.
    ours = _ours_markets((ctx.inject or {}).get("model_probs"))
    state.n08_pcode = {"p_code_pick": round(p, 4), "sum_adj_pp": s,
                       # 🔴 추적용 — 홈 기준 원값. 픽이 어떻게 갈렸는지 되짚는다.
                       "p_home": round(p_home, 4), "p_away": round(p_away, 4),
                       # 🔴 자리만 둔다. `model_w=0` 이라 항등이다.
                       "p_model": None, "model_w": 0.0,
                       "ours_markets": ours}
    if ours:
        logger.info("[flow:n08] game=%s 파생 확률 %s",
                    state.game_id, {k: len(v) for k, v in ours.items()})
    logger.info("[flow:n08] game=%s 시장(홈) %.4f %+.2f%%p → 홈 %.4f · 픽 %s %.4f",
                state.game_id, float(p_home_mkt), s_home, p_home, side, p)
    return state
