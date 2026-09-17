"""[U11 2026-09-15] T-60 재판정 — diff 를 **다시 계산에 넣는다.**

🔴 `fotmob.diff_xi` 는 이미 `bench_notable`·`surprise_in` 을 냈다. 그런데
   `_lineup_recheck` 는 그것을 **game_trace 에 적고 끝났다.** 확정 라인업이
   예상과 달라도 `p_code` 도 등급도 그대로였다 — T-60 재판정이 이름뿐이었다.

🔴 **원래 값을 덮지 않는다.** `adj`·`p_code`·`grade` 는 그대로 두고 `*_after`
   를 따로 남긴다. 덮으면 "판정이 어떻게 바뀌었나"를 잃는다.

⚠️ 순수 함수다. DB·HTTP 를 부르지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: diff 가 만든 조정의 이름. 원장·카드가 이 이름으로 읽는다.
KEY_IN = "라인업복귀"
KEY_OUT = "라인업결장"

#: 🔴 [PA-27-b] 확정 XI 가 **대체하는** 축. 이름은 `prob.ADJ_RULES` 의 키다 —
#   여기서 뜻을 새로 만들지 않는다.
KEY_BASE_OUT = "주전결장"


def _by_name(players: dict | None, names) -> list:
    """이름 목록 → 선수 dict. 못 찾으면 **빈 dict**(중요도 1.0 중립)."""
    box = players or {}
    return [box.get(str(n)) or {} for n in (names or [])]


def _market_of(p_code: float | None, adj: dict | None):
    """`p_code = p_market + Σ축소(adj)` 를 되짚어 시장값을 얻는다.

    🔴 시장값을 **다시 읽지 않는다** — 재판정이 배당을 또 긁으면 요청이 는다.
    ⚠️ 상한에 걸린 값이면 되짚기가 정확하지 않다. 그때도 상한이 다시 걸리므로
       결과는 같은 쪽으로 수렴한다.
    """
    from app.engine import prob as P

    if p_code is None:
        return None
    return float(p_code) - sum(P.shrink_and_cap(adj).values()) / 100.0


def reweigh(*, adj: dict | None, p_code: float | None, diff: dict | None,
            players: dict | None = None, grade: str | None = None,
            sport: str = "soccer", team_total_value=None,
            snippet: bool = False, settings=None) -> dict:
    """확정 라인업 차이 → `{adj_after, p_code_after, grade_after, changed, why}`.

    `diff` 는 `fotmob.diff_xi` 모양: `{side: {bench_notable[], surprise_in[]}}`.

    🔴 **복귀는 결장의 반대가 아니다.** 예상 결장이 실제로 뛰면 `+`(U8 의
       ×1.5×1.5), 예상 선발이 빠지면 `−`(×1.5). 한 규칙으로 뭉치면 둘 중
       하나가 거꾸로 간다.
    🔴 diff 가 비어 있으면 **아무것도 안 바꾼다.** `changed=False` 로 남긴다.
    """
    from app.engine import adjust as A
    from app.engine import prob as P

    base_adj = dict(adj or {})
    out = {"adj_after": base_adj, "p_code_after": p_code,
           "grade_after": grade, "changed": False, "why": "diff 없음"}
    if not diff:
        return out

    add: dict[str, float] = {}
    notes = []
    for side, box in (diff or {}).items():
        # 원정 쪽 변화는 홈 확률 기준으로 **부호가 뒤집힌다**.
        sign = 1.0 if side == "home" else -1.0
        ins = _by_name(players, (box or {}).get("surprise_in"))
        outs = _by_name(players, (box or {}).get("bench_notable"))
        if ins:
            v = A.contrib_return(ins, team_total_value=team_total_value) * sign
            add[f"{KEY_IN}:{side}"] = round(v, 2)
            notes.append(f"{side} 복귀 {len(ins)}명 {v:+.1f}%p")
        if outs:
            v = A.contrib_out(outs, team_total_value=team_total_value) * sign
            add[f"{KEY_OUT}:{side}"] = round(v, 2)
            notes.append(f"{side} 결장 {len(outs)}명 {v:+.1f}%p")
    if not add:
        out["why"] = "diff 는 있으나 변화 인원 0"
        return out

    # 🔴 [PA-27-a 2026-09-17] **새로 더한 것에만 잡음 제외를 건다.**
    #    종전에는 `merged` 전체에 걸어서 **기존 가감까지 지웠다** —
    #    실측: adj={'주전결장': -1.5} 에 홈 결장 1명을 더하니 둘 다 1.5 라
    #    문턱(2.0) 아래로 떨어져 `adj_after={}` 가 됐고, 확률이 시장으로
    #    되돌아가 **0.55 → 0.5575 로 올랐다.** 결장을 확인했는데 홈이
    #    유리해지는 거꾸로 된 신호다.
    #    ⚠️ 기존 가감은 **이미 이 규칙을 통과해** adj_pp 에 들어온 값이다.
    #       U8 의 "contrib < 2%p 제외"는 adj 를 **만들 때** 거는 규칙이지
    #       재판정 때 소급해 다시 거는 규칙이 아니다.
    #    🔴 잡음 제외는 U8 규칙 그대로 — 축소 **앞**이다.
    add_kept, dropped = A.drop_small(add)
    # 🔴 [PA-27-b 2026-09-17] **확정 XI 가 예상치를 대체한다. 얹지 않는다.**
    #    `주전결장`(이력의 주전이 오늘 명단에 없다)과 `라인업결장`(예상 XI 에
    #    있던 선수가 공식 XI 에 없다)은 기준선이 다르지만 **같은 선수가 양쪽에
    #    걸린다** — 함께 두면 한 사람을 두 번 센다.
    #    실측 재현: {'주전결장': -1.5, '라인업결장:home': -3.0} 이 함께 남았다.
    #    딥서치 근거(2026-09-17): "예상 라인업은 구단이 팀을 발표할 때까지만
    #    유효하고 그 뒤에는 **확정 11명으로 대체된다**"(Sportmonks). 현대 Elo
    #    계열도 확정 라인업을 얹지 않고 갈아끼운다(PlayerElo · FanPick).
    #    ⚠️ **결장이 실제로 확인됐을 때만** 대체한다. 공식 XI 가 없거나
    #       복귀만 있으면 종전대로 `주전결장` 을 유지한다 — 모르면 안 바꾼다.
    #    ⚠️ 결장과 무관한 축(이동연전·휴식 등)은 건드리지 않는다.
    replaced = None
    if any(k.startswith(KEY_OUT) for k in add_kept) and KEY_BASE_OUT in base_adj:
        base_adj = {k: v for k, v in base_adj.items() if k != KEY_BASE_OUT}
        replaced = KEY_BASE_OUT
    kept = {**base_adj, **add_kept}
    # 🔴 `prob.p_code` 를 그대로 쓴다 — 승률 상한이 여기서 다시 걸린다.
    p_after = P.p_code(_market_of(p_code, base_adj), kept, sport,
                       settings=settings)
    grade_after = grade
    if p_after is not None:
        from app.engine import confidence as C

        if p_after >= C.CODE_HIGH_P:
            grade_after = C.HIGH
        elif p_after >= C.CODE_MID_P:
            grade_after = C.MID
        else:
            grade_after = C.LOW
        grade_after = C.cap_by_snippet(grade_after, snippet)

    if replaced:
        notes.append(f"{replaced} → 확정 XI 로 대체")
    out.update({"adj_after": kept, "adj_dropped_after": dropped,
                "replaced_axis": replaced,
                "p_code_after": p_after, "grade_after": grade_after,
                "changed": True, "why": " · ".join(notes),
                "axes_after": A.axes(kept)})
    logger.info("[rejudge] %s → p_code %s → %s · 등급 %s → %s",
                out["why"], p_code, p_after, grade, grade_after)
    return out


def starter_changed(before: str | None, after: str | None) -> dict:
    """[야구 전용] 예고 선발 ↔ 실제 선발.

    ⚠️ 축구의 XI diff 와 **이름이 다르다.** 섞으면 안 된다 — 야구는 한 명이고
       축구는 열한 명이다.
    """
    b = (before or "").strip()
    a = (after or "").strip()
    if not b or not a:
        return {"changed": False, "why": "예고 또는 실제가 없다",
                "before": b or None, "after": a or None}
    return {"changed": b != a, "before": b, "after": a,
            "why": f"{b} → {a}" if b != a else "예고대로"}
