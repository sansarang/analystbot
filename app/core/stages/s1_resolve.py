"""🔴🔴 **v6 s1 — 경기 확정.** `Question → MatchRef | Ambiguous`(§5).

지시서 §5 s1: *"기존 이름표·열쇠 사다리·오픈월드 ⑥단·`window.inside` 를
`adapt.py` 로 감싸 `MatchRef` 를 만든다. 확정 기준(두 팀 일치·36시간 창·정확히
1개)은 그대로."*

⚠️ 후보가 둘 이상이면 `Ambiguous` 를 돌려 **사용자에게 묻는다** — 하나를 골라 주면
   남의 경기를 분석할 수 있고 그 카드는 통째로 거짓이다(§17-g-3 · M14).
"""
from __future__ import annotations

from typing import Any

from app.core import adapt
from app.core.schema import Ambiguous, DropReason, MatchRef, Question
from app.core.state import RunState


async def run(q: Question, *, pool: Any, state: RunState,
              net: Any = None) -> MatchRef | Ambiguous:
    """🔴 질문 → 그 경기 하나. ⚠️ 못 고르면 `Ambiguous`(예외를 안 던진다)."""
    from app import queries, resolve
    try:
        look = await resolve.match_of(
            pool, team=q.team or q.raw, opponent=q.opponent or "",
            net=net)
    except Exception as exc:                                # noqa: BLE001
        state.drop("s1", DropReason.NO_DOC, f"입구가 터졌다: {exc!r}")
        return Ambiguous(why=f"🔴 입구가 터졌다 — {exc!r}")
    for said in (getattr(look, "steps", None) or ()):
        state.note(f"s1 {said}")
    if not getattr(look, "ok", False):
        reason = getattr(getattr(look, "reason", None), "value", "?")
        return Ambiguous(
            why=f"🔴 경기를 확정하지 못했다 — `{reason}`",
            candidates=[f"{r.get('away')} @ {r.get('home')} · {r.get('league')}"
                        for r in (getattr(look, "candidates", None) or ())][:6])
    raw = look.ref
    got = adapt.ref_of(
        raw, competition_short=queries.competition_short(
            getattr(raw, "competition", "")),
        # 🔴 쌓인 표에 없던 경기면 ⑥단을 탔다 — 상한이 그것을 본다(§7)
        openworld=bool(getattr(look, "openworld", False)))
    if got is None:
        return Ambiguous(
            why=("🔴 경기를 찾았는데 **열쇠나 킥오프가 비었다** — 그 값으로는 "
                 "창을 자를 수 없다(절대규칙 2)"))
    state.match_key = got.id
    return got
