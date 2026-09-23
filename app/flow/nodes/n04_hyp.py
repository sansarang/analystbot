"""[v1.4 STEP 5] ④ 가설 — **무엇을 찾을지 먼저 정한다. LLM 을 부르지 않는다.**

🔴 CLAUDE.md "페이블처럼 분석한다": 가설은 코드가 세운다. 게이트 라벨 하나가
   들어가면 확인 변수 목록이 나온다 — 같은 라벨이면 언제나 같은 목록이다.
🔴 변수 목록·핵심 표시는 `config/rules.yaml` 의 `flow.adjust_prior_pp` 가
   원본이다. 여기 이름을 손으로 적지 않는다(사본 금지).
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import (AGREE, BOARD, DOUBT, OVER, PRIOR_ONLY,
                             R_NEUTRAL, REFUTED_MEANS_BY_GATE)

logger = logging.getLogger(__name__)

NODE = "n04_hyp"

#: `동의` 에서 보는 파생 재료. 🔴 승패 근거가 아니라 **득점 환경**이다
#  (FORKS F-11: 최근 폼은 승패 예측력이 0 에 가깝다).
_DERIV_VARS = {"baseball": ("starter_recent3", "bullpen_3d", "lineup_out"),
               "soccer": ("xi_confirmed", "rotation_risk")}

#: 소스 힌트 — ⑤ 수집이 어디를 볼지 고르는 데 쓴다.
_HINT = {"baseball": "공식(statsapi·KBO·NPB) + 뉴스RSS",
         "soccer": "FotMob matchDetails"}


def _vars_of(sport: str, names) -> list:
    table = R.vars_for(sport)
    out = []
    for n in names:
        spec = table.get(n) or {}
        out.append({"var": n, "is_core": bool(spec.get("core")),
                    "source_hint": _HINT.get(sport, "")})
    return out


def _prior_strength(state) -> tuple:
    """사전값이 우리 픽을 **얼마나 세게** 보는가. `(확률, 0.5에서의 거리)`.

    🔴 [HYC-4] 조사 순서를 정하는 근거다 — 사전값이 셀수록 그것을 깨뜨릴
       **핵심 변수**를 먼저 묻는다. 약하면 굳이 핵심부터 묻지 않는다.
    ⚠️ 못 읽으면 `(None, 0.0)` — 지어내지 않는다.
    """
    prior = getattr(state, "n01_prior", None) or {}
    side = getattr(state, "hyp_side", None) or "home"   # [SIDE-2] 조사 방향
    p = prior.get(f"p_{side}")
    try:
        pf = float(p)
    except (TypeError, ValueError):
        return (None, 0.0)
    return (pf, round(abs(pf - 0.5), 4))


def _move_of(state) -> dict | None:
    """[MOV-H] 이 경기에 **접목할 만한** 이동인가. 아니면 None.

    🔴 켜진 종목에서만 본다(`flow.move.sports`). 사용자 지시 순서가 MLB
       부터이고, KBO·NPB 는 원자료가 노이즈라 ODD-S 배포 뒤에 켠다.
    ⚠️ **못 잰 이동을 0 으로 읽지 않는다** — `move_pp` 가 None 이면 모름이다.
    """
    mv = (getattr(state, "n02_market", None) or {}).get("move") or {}
    pp = mv.get("move_pp")
    if pp is None:
        return None
    lg = str(getattr(state, "league", "") or "").lower()
    sp = str(getattr(state, "sport", "") or "").lower()
    on = {str(x).lower() for x in (R.get("move.sports") or [])}
    if not ({lg, sp} & on):
        return None
    try:
        if abs(float(pp)) < float(R.get("move.min_pp", 1.0)):
            return None
    except (TypeError, ValueError):
        return None
    return dict(mv)


def _move_first(rows: list) -> list:
    """이동을 설명할 수 있는 변수를 **앞으로** 옮긴다.

    ⚠️ 목록은 `flow.move.explains` 가 원본이다 — 이름을 여기 적지 않는다.
    ⚠️ 빼지 않고 **순서만** 바꾼다. 빼면 ⑥ 분모가 달라진다.
    """
    want = [str(x) for x in (R.get("move.explains") or [])]
    rank = {n: i for i, n in enumerate(want)}
    return sorted(rows, key=lambda v: rank.get(v.get("var"), len(rank)))


def _ordered_vars(sport: str, strength: float) -> list:
    """[HYC-4] **경기별** 조사 목록. 목록은 config 가 주고 **순서**를 여기서 정한다.

    🔴 사전값이 셀수록 핵심(`core`)을 앞에 둔다 — 셀수록 그것을 깨뜨릴 근거가
       먼저 필요하다. 약하면 원래 순서(config 표기 순)를 지킨다.
    ⚠️ 변수 이름을 손으로 적지 않는다 — `config/rules.yaml` 이 원본이다.
    """
    rows = _vars_of(sport, tuple(R.vars_for(sport).keys()))
    if strength >= float(R.get("hyp.strong_prior", 0.10) or 0.10):
        rows.sort(key=lambda v: (not v.get("is_core"),))
    return rows


async def run(state, ctx):
    """④ 가설.

    🔴 [F-17 2026-09-23 사용자 지시 "둘다 해라"] **질문은 사전값에서 나온다.**
       종전에는 게이트(=사전값−시장 괴리)가 질문을 골랐다. 실측 7일:
```
게이트      가설      경기   조사 변수
동의       H_deriv    48    3개 고정
가치의심     H_break    30    6개 고정
시장과대     H_fade     24    6개 고정
→ 게이트 5종 · 조합 7종 (조합 수 == 게이트 수 = 가설이 게이트의 함수)
```
       즉 **시장을 보기 전에는 무엇을 조사할지 몰랐다.** CLAUDE.md 가 금한
       자리이고("떼는 것은 조사 방향이다"), 같은 문서가 F-17 을 미착수로
       적고 있었다.

    🔴 **해석은 게이트가 계속 정한다**(사용자 결정 (가) 2026-09-23).
       질문만 떼고, "근거를 못 찾았다"가 무슨 뜻인지는 시장과 비교해 정한다 —
       시장이 우리보다 훨씬 높게 보는데 반대 근거가 없으면 시장이 맞다(철회).
       그래서 `refuted_means` 는 **게이트**로 고른다(아래 표).

    🔴 [HYC-4] 조사 목록도 경기별이다 — 사전값이 셀수록 핵심을 앞에 둔다.
       종전에는 `H_break` 40회가 전부 같은 6개·같은 순서였다.
    """
    sport = (state.sport or "").lower()
    gate = (state.n03_gate or {}).get("gate")
    # 🔴 [SIDE-2] 가설은 **사전값**을 무너뜨리는 것이다. 시장이 고른 쪽을
    #    무너뜨리려 들면 그 순간 조사가 시장의 함수가 된다(앵커링).
    side = state.hyp_side
    p_prior, strength = _prior_strength(state)

    move = None if gate == BOARD else _move_of(state)

    if gate == BOARD:
        hyp = {"id": "H_none", "text": "찾을 것이 없다", "vars": []}
    else:
        # 🔴 질문은 **하나**다. 게이트를 보지 않는다.
        hyp = {"id": "H_break",
               "text": f"우리 픽({side})을 무너뜨릴 근거"
                       + (" — 시장 전" if gate == PRIOR_ONLY else ""),
               "vars": _ordered_vars(sport, strength),
               "why": (f"사전값이 {side} 를 {p_prior:.1%} 로 본다 — "
                       f"그 판단을 깨뜨릴 근거부터 찾는다"
                       if p_prior is not None else
                       "사전값을 못 읽었다 — 목록 순서 그대로 찾는다")}
        # 🔴 [MOV-H 2026-09-23] **가격이 움직였으면 그 이유도 같이 찾는다.**
        #    사용자: "왜 이렇게 배당이 이동되었는지…**초기 가설과 접목**".
        #    ⚠️ 가설을 하나 더 만들지 않는다 — ⑤⑥이 `n04_hyp[0]` 만 읽으므로
        #       채점 분모가 조용히 달라진다. `H_break` 안에 싣는다.
        if move:
            pp = float(move["move_pp"])
            toward = state.home if pp > 0 else state.away
            hyp["move"] = move
            hyp["vars"] = _move_first(hyp["vars"])
            hyp["why"] += (f" · 시장이 {toward} 쪽으로 {abs(pp):.1f}%p "
                           f"움직였다({move.get('n_snaps')}벌)")
            # 🔴 [MOV-C 2026-09-23] **"이유 미상"을 쓰지 않는다**(사용자 지시).
            #    ②가 시각을 맞춰 원인을 붙였으면 그것을 적고, 못 붙였으면
            #    "자금"인지 "관측 없음"인지까지 구분해 적는다 — 찾아보지도
            #    않고 자금이라 부르면 `none` 에 이름만 바꾼 것이다.
            from app.flow import attribution as A

            line = A.summary(move.get("causes") or {})
            if line:
                hyp["why"] += f" · {line}"
                found = [c for m in (move["causes"]["moves"] or [])
                         for c in (m.get("causes") or [])]
                if found:
                    hyp["why"] += " — " + " / ".join(found[:2])
            else:
                hyp["why"] += " — 그 이유도 찾는다"

    # 🔴 [FIX-4a] **파생 마켓은 "걸 대상"이지 질문이 아니다.** 게이트가
    #    `동의`(사전값과 시장이 맞다)일 때만 파생을 건다 — 승패에 우위가
    #    없다는 판단이므로 그대로 둔다. ⑪이 종전에 전 마켓에서 max(edge)
    #    를 골라 핸디 edge −46%p 가 best 로 뽑히던 자리다.
    hyp["market"] = "total" if gate == AGREE else None

    # 🔴 [CNF-2 2026-09-20] **반증이 무슨 뜻인지는 가설이 정한다.**
    #    딥서치(FORKS F-19): absence of evidence 는 "그 주장이 참이었다면
    #    근거가 나왔을 것"인 만큼만 evidence of absence 다. 그러면 뜻은
    #    가설의 **주장**에 달린다 — 게이트가 주장을 정하므로 여기서 싣는다.
    #      H_fade  "시장 반대편을 세울 근거" → 없으면 시장이 맞다  → 철회
    #      H_break "우리 픽을 무너뜨릴 근거" → 없으면 픽이 단단하다 → 강화
    #      H_deriv 파생 재료                                      → 중립
    #    ⚠️ 종전 ⑥은 게이트와 무관하게 **철회 하나만** 적용했다. 그대로
    #       반증을 켜면 결장 0명인 건강한 라인업이 전부 철회된다.
    # 🔴 [F-17 (가)] **게이트가 정한다.** 가설 id 가 하나가 됐으므로 id 로는
    #    가를 수 없다. 표의 원본은 `labels.REFUTED_MEANS_BY_GATE` 다(사본 금지).
    hyp.setdefault("refuted_means",
                   REFUTED_MEANS_BY_GATE.get(gate, R_NEUTRAL))
    state.n04_hyp = [hyp]
    logger.info("[flow:n04] game=%s %s → %s · 변수 %d개 (핵심 %d)",
                state.game_id, gate, hyp["id"], len(hyp["vars"]),
                sum(1 for v in hyp["vars"] if v["is_core"]))
    return state
