"""[v1.4 STEP 10] ⑪ 값 판정 — **가격에 값이 있는가.**

🔴 `edge = p_code − 1/배당`. 요구확률 자리에 `p_market`(devig)을 넣으면 edge 가
   늘 마진만큼 양수로 나온다 — 지시문 STEP 10 의 "흔한 오류"이고 거짓 픽의 뿌리다.
🔴 **승패 픽은 `동의` 게이트에서만** 만든다(v1.4 "시장 동의 시에만 추천").
   시장과대·가치의심에서는 구조(파생) 픽만 허용한다.
🔴 모델이 없는 파생 마켓은 `None` 이다 — **추측 확률로 픽을 만들지 않는다.**
🔴 [FIX-4 2026-09-20] 다섯 가지를 더 건다:
     a. 후보는 **④가 지정한 마켓 하나**뿐이다. 종전 `max(edge)` 전수 스캔은
        핸디 edge −46%p 를 best 로 뽑기도 했다(실측).
     b. **시장 동의** — 디빅한 시장 쪽과 우리 쪽이 같아야 후보다.
        open→현재 이동이 우리 반대면 철회. open 이 없으면 후보 0(fail closed).
     c. **edge 상한** — `flow.gate_pp.freeze`(12.0) 이상이면 "오류의심" 보드.
     d. **λ 절사** — `LambdaResult.clipped` 가 차 있으면 후보 0.
     e/f. 방향 증거가 픽 반대면 **철회**(라인을 옮기지 않는다).
⚠️ 문턱 `edge_min_pp` 는 `config/rules.yaml` 이 원본이다.
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import AGREE, PICK_BOARD, PICK_ML, PICK_STRUCT
from app.flow.odds_math import devig_2way, required_prob

logger = logging.getLogger(__name__)

NODE = "n11_value"


def _structure_candidates(state) -> list:
    """파생 마켓 후보. **코드 확률이 없으면 후보가 아니다.**

    🔴 총점·팀토탈·핸디의 우리 확률은 `model_probs`(scoring)가 원본이다.
       없으면 `None` 이고, 그때는 그 마켓을 건너뛴다 — 0.5 로 채우지 않는다.
    """
    der = (state.n02_market or {}).get("derivatives") or {}
    ours = (state.n08_pcode or {}).get("ours_markets") or {}
    out = []
    for name, book in (("total", der.get("total") or {}),
                       ("team_total_home", der.get("team_total_home") or {}),
                       ("team_total_away", der.get("team_total_away") or {})):
        line = book.get("line")
        for side in ("over", "under"):
            odds = book.get(side)
            if odds is None:
                continue
            p_ours = (ours.get(f"{name}_{side}") or {}).get(line)
            if p_ours is None:
                continue                      # 모델 없음 — 추측 금지
            out.append({"market": f"{name}_{side}", "line": line,
                        "odds": float(odds),
                        "edge_pp": round((float(p_ours) - required_prob(odds)) * 100, 2)})
    for ah in (der.get("ah") or []):
        p_ours = (ours.get("ah") or {}).get(ah.get("line"))
        if p_ours is None:
            continue
        out.append({"market": "ah", "line": ah.get("line"),
                    "odds": float(ah["odds"]),
                    "edge_pp": round((float(p_ours) - required_prob(ah["odds"])) * 100, 2)})
    return out


def _lambda_clipped(state) -> dict:
    """λ 가 범위에서 잘렸는가. 🔴 잘린 λ 위의 파생 확률은 믿을 수 없다."""
    mp = (state.n08_pcode or {}).get("model_probs") or {}
    return dict(mp.get("clipped") or {})


def total_direction(state) -> dict:
    """총점 방향 — **증거로만** 정한다(FIX-4e).

    🔴 어느 쪽이든 선발 악재·불펜 악재 → 오버 · 양 팀 선발 모두 호재 → 언더.
    🔴 픽 반대 방향 증거가 **1개라도** 있으면 철회한다(라인을 옮기지 않는다).
    """
    ev = {e["var"]: (e.get("direction") or {}) for e in (state.n05_evidence or [])}
    over = under = 0
    st = ev.get("starter_recent3") or {}
    bp = ev.get("bullpen_3d") or {}
    for side in ("home", "away"):
        if int(st.get(side, 0) or 0) < 0:
            over += 1
        if int(bp.get(side, 0) or 0) < 0:
            over += 1
    good = [int(st.get(s0, 0) or 0) for s0 in ("home", "away")]
    if good and all(v > 0 for v in good):
        under = sum(1 for v in good if v > 0)
    if over and under:
        return {"side": None, "for": 0, "against": over + under,
                "why": f"양방향 증거(오버 {over} · 언더 {under}) — 철회"}
    if over:
        return {"side": "over", "for": over, "against": 0, "why": f"오버 증거 {over}"}
    if under:
        return {"side": "under", "for": under, "against": 0, "why": f"언더 증거 {under}"}
    return {"side": None, "for": 0, "against": 0, "why": "방향 증거 없음"}


def _side_of(market: str) -> str:
    """`total_over` → `over`. 후보의 **자기 쪽**이다."""
    return str(market or "").rsplit("_", 1)[-1]


def _struct_grade(vote: dict, side: str) -> str:
    """[VAL-B] 투표는 **버리는 장치가 아니라 확신도**다.

    🔴 종전에는 투표가 한쪽 후보를 통째로 버렸다. 그래서 λ 가 가리키는
       반대쪽(+8.44%p)을 아무도 못 봤다(실물 g16449).
    ⚠️ 등급 문자열의 원본은 `config/rules.yaml` 이다 — 코드에 적지 않는다.
    """
    v = (vote or {}).get("side")
    if v is None:
        return str(R.get("value.no_vote_grade", "B"))
    if v == side:
        return "A" if (int(vote.get("for", 0)) >= 2
                       and int(vote.get("against", 0)) == 0) else "B"
    return str(R.get("value.vote_conflict_grade", "C"))


def _market_agrees(state, cand: dict, side: str) -> bool:
    """디빅한 시장 쪽과 우리 쪽이 같고, open→현재 이동이 반대가 아닌가.

    🔴 open 이 없으면 **False**(fail closed) — 이동을 모르면 검증이 아니다.
    """
    der = ((state.n02_market or {}).get("derivatives") or {}).get("total") or {}
    o_now, u_now = der.get("over"), der.get("under")
    o_open = (der.get("open") or {}).get("over") if isinstance(der.get("open"), dict) else None
    u_open = (der.get("open") or {}).get("under") if isinstance(der.get("open"), dict) else None
    if not o_now or not u_now or not o_open or not u_open:
        return False
    # ⚠️ `devig_2way` 는 **튜플**을 돌려준다(over, under 순). dict 가 아니다.
    i = 0 if side == "over" else 1
    p_now = devig_2way(float(o_now), float(u_now))[i]
    p_open = devig_2way(float(o_open), float(u_open))[i]
    # 🔴 시장이 우리와 같은 쪽을 보고(>0.5), open 대비 **우리 반대로 밀리지
    #    않았을** 때만 통과. open 이 없으면 위에서 이미 False 다(fail closed).
    return p_now > 0.5 and p_now >= p_open - 1e-9


CORE_VARS = ("starter_recent3", "bullpen_3d", "lineup_out")


def ml_direction_sum(state, side: str) -> tuple[int, list]:
    """승패 픽 쪽에서 본 **핵심 증거 방향의 합**(FIX-4f).

    🔴 합 < 0 이면 우리 픽에 불리한 증거가 더 많다는 뜻이고, 그때는 확률을
       깎지 않고 **보드로 내린다** — 불리한 근거 위에 픽을 세우지 않는다.
    """
    other = "away" if side == "home" else "home"
    tot, why = 0, []
    for e in (state.n05_evidence or []):
        if e.get("var") not in CORE_VARS:
            continue
        d = e.get("direction") or {}
        v = int(d.get(side, 0) or 0) - int(d.get(other, 0) or 0)
        if v:
            tot += v
            why.append(f"{e['var']} {v:+d}")
    return tot, why


async def run(state, ctx):
    """⑪ 값 판정."""
    side = state.pick_side
    odds = (state.n02_market or {}).get("odds") or {}
    p_code = (state.n08_pcode or {}).get("p_code_pick")
    gate = (state.n03_gate or {}).get("gate")
    edge_min = float(R.get("edge_min_pp", 2.0))

    ml_edge = None
    if p_code is not None and odds.get(side):
        ml_edge = round((float(p_code) - required_prob(odds[side])) * 100, 2)

    # 🔴 승패는 `동의` 에서만. 다른 게이트에서는 만들지 않는다.
    if gate == AGREE and ml_edge is not None and ml_edge >= edge_min:
        ml_dir, ml_why = ml_direction_sum(state, side)
        if ml_dir < 0:
            # 🔴 [FIX-4f] 픽에 불리한 방향 증거 — 라인을 옮기지 않고 철회한다.
            state.n11_value = {"ml_edge_pp": ml_edge, "pick_type": PICK_BOARD,
                               "structure": None, "n_candidates": 0,
                               "reject_reason": f"픽 반대 방향 증거 합 {ml_dir:+d}"
                                                f" ({' · '.join(ml_why)})"}
            logger.info("[flow:n11] game=%s 승패 철회 — 방향 합 %+d", state.game_id, ml_dir)
            return state
        state.n11_value = {"ml_edge_pp": ml_edge, "pick_type": PICK_ML,
                           "structure": None, "direction_sum": ml_dir}
        logger.info("[flow:n11] game=%s 승패 픽 · edge %+.2f%%p",
                    state.game_id, ml_edge)
        return state

    # ── [FIX-4] 구조 픽
    hyp = (state.n04_hyp or [{}])[0]
    want = hyp.get("market")
    cands = _structure_candidates(state)
    reject = None
    best = None
    if not want:
        reject = "가설이 마켓을 지정하지 않았다"
    elif _lambda_clipped(state):
        reject = f"λ 절사 {_lambda_clipped(state)} — 파생 확률을 믿을 수 없다"
    else:
        fam = [c for c in cands if str(c.get("market", "")).startswith(want)]
        vote = total_direction(state)
        # 🔴 [VAL-B 2026-09-23] **양쪽을 다 본다.** 종전에는
        #    `side_c = [c for c in fam if c["market"].endswith(vote["side"])]`
        #    로 투표 반대쪽을 통째로 버렸다. 실물 g16449 에서 λ 가 가리킨
        #    언더 **+8.44%p** 를 아무도 못 봤고, 버려진 오버 −13.14%p 만
        #    남아 거절됐다.
        #    ⚠️ 비그 때문에 "−13.14 의 반대 = +13.14" 가 아니다. 쪽마다
        #       `p − 1/배당` 을 따로 계산한 것이 `_structure_candidates` 다.
        if not str(R.get("value.both_sides", True)) or \
                R.get("value.both_sides", True) is False:
            fam = [c for c in fam
                   if vote["side"] and _side_of(c["market"]) == vote["side"]]
        no_vote_ok = bool(R.get("value.allow_no_vote", True))
        if not fam:
            reject = f"지정 마켓 `{want}` 후보 0"
        elif vote["side"] is None and not no_vote_ok:
            reject = f"총점 방향 미정 — {vote['why']}"
        else:
            best = max(fam, key=lambda c: c["edge_pp"])
            best_side = _side_of(best["market"])
            if not _market_agrees(state, best, best_side):
                reject = "시장 동의 실패(또는 open 없음 · 반대 이동)"
            elif best["edge_pp"] >= float(R.get("gate_pp.freeze", 12.0)):
                reject = f"edge {best['edge_pp']:+.2f}%p — 오류의심"
            elif best["edge_pp"] < edge_min:
                reject = f"edge {best['edge_pp']:+.2f}%p < {edge_min}"
            else:
                sg = _struct_grade(vote, best_side)
                if state.n09_conf is not None:
                    state.n09_conf["struct_grade"] = sg
                    # 🔴 갈린 사실을 **남긴다** — 30건 쌓이면 투표와 λ 중
                    #    어느 쪽이 나은지 숫자로 나온다.
                    state.n09_conf["struct_reason"] = (
                        f"방향 증거 찬 {vote['for']} · 반 {vote['against']}"
                        + ("" if vote["side"] in (None, best_side)
                           else f" · 투표({vote['side']})와 **반대**편 채택"))
                state.n11_value = {"ml_edge_pp": ml_edge, "pick_type": PICK_STRUCT,
                                   "structure": best, "n_candidates": len(cands),
                                   "struct_grade": sg, "direction": vote}
                logger.info("[flow:n11] game=%s 구조 픽 %s %+.2f%%p · 등급 %s",
                            state.game_id, best["market"], best["edge_pp"], sg)
                return state
    if reject:
        logger.info("[flow:n11] game=%s 구조 철회 — %s", state.game_id, reject)

    state.n11_value = {"ml_edge_pp": ml_edge, "pick_type": PICK_BOARD,
                       "structure": best, "n_candidates": len(cands),
                       "reject_reason": reject}
    logger.info("[flow:n11] game=%s 보드 — ml_edge %s · 구조 후보 %d",
                state.game_id, ml_edge, len(cands))
    return state
