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

    merged = {**base_adj, **add}
    # 🔴 잡음 제외는 U8 규칙 그대로 — 축소 **앞**이다.
    kept, dropped = A.drop_small(merged)
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

    out.update({"adj_after": kept, "adj_dropped_after": dropped,
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
