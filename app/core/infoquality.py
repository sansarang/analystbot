"""🔴🔴 **§13 정보 품질 InfoQ** · **§14 판정 행동** — 지시서 2026-10-12(둘째).

> 0~5점: +1 확정 XI(양 팀 id) · +1 결장 사다리 한 칸 이상 성공(양 팀) ·
> +1 새 사실 72시간 ≥1 · +1 ContextRow 완전 · +1 벤치 id 확정.
> InfoQ ≤ 2 → 등급 **한 단계↓** · "조건부" 이상 불가 · 빠진 칸을 방아쇠로.

🔴 왜 — 같은 확률이라도 **재료가 비어 있으면** 그 확률을 믿을 근거가 약하다.
   ⚠️ 그렇다고 확률을 깎으면 그것은 **두 번 세는 것**이다(확률은 이미 자기 재료만
   썼다). 🔴 그래서 InfoQ 는 **등급만** 내린다(계약 C13-1: 확률 경로가 이 모듈을
   부르면 실패).
🔴 등급 사다리는 `app/core/stages/s7_judge.BREAK_LADDER` **하나다**(사본 금지).
⚠️ 못 센 칸과 **계산 불가 칸**(⬜ · 재현·백필의 기사 칸)을 가른다 — 섞으면
   재현 카드가 운영 카드보다 늘 낮은 점수를 받는다(#3 조용한 0 금지).
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 🔴 다섯 칸 — `(열쇠, 카드에 적을 이름)`. 지시의 그 목록이다.
BOXES: tuple[tuple[str, str], ...] = (
    ("xi_ids", "확정 XI(양 팀 id)"),
    ("ladder", "결장 사다리 한 칸 이상(양 팀)"),
    ("fresh", "새 사실 72시간 ≥1"),
    ("context", "ContextRow 완전(휴식·부하)"),
    ("bench_ids", "벤치 id 확정"),
)

#: 🔴 이 점수 이하면 등급을 내린다(§14)
THIN = 2

#: 🔴 그때 판정 칸의 상한 — 이보다 센 말은 못 쓴다
CAP = "조건부"


@dataclass
class InfoQ:
    """🔴 점수 한 묶음 — **빠진 칸과 못 센 칸을 이름으로** 든다."""

    score: int = 0
    missing: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    why: str = ""

    def thin(self) -> bool:
        return int(self.score) <= THIN


def score_of(box: dict) -> InfoQ:
    """🔴🔴 다섯 칸을 센다. `True` = 1점 · `False` = 0점 · `None` = **계산 불가**(⬜).

    ⚠️ `None` 을 0 으로 세지 않는다 — 재현·백필은 기사 칸을 만들 수 없다(§13).
    """
    got = InfoQ()
    said = dict(box or {})
    for key, name in BOXES:
        val = said.get(key)
        if val is None:
            got.unknown.append(name)
        elif val:
            got.score += 1
        else:
            got.missing.append(name)
    parts = [f"InfoQ **{got.score}/{len(BOXES)}**"]
    if got.missing:
        parts.append("빠진 칸 " + " · ".join(got.missing))
    if got.unknown:
        parts.append("⬜ 못 센 칸 " + " · ".join(got.unknown))
    got.why = " — ".join(parts)
    return got


def step_of(*, score: int) -> tuple[int, str]:
    """🔴 §14 — 내릴 칸 수. `(걸음, 사유)`. 넉넉하면 `(0, "")`."""
    if int(score) > THIN:
        return 0, ""
    return 1, (f"⚠️ **InfoQ {int(score)}/{len(BOXES)}** — 재료가 얇다 → 등급 "
               f"**한 단계↓** · `{CAP}` 이상 불가")


def cap_stance(said: str, *, score: int) -> str:
    """🔴🔴 **C14-1** — 얇으면 `간다` 가 남지 못한다. ⚠️ **내리기만** 한다."""
    if int(score) > THIN:
        return str(said)
    from app.core.stages.s7_judge import BREAK_LADDER   # noqa: F401 (사본 금지)
    if str(said) in ("간다", "조건 없음", ""):
        return CAP
    return str(said)


def apply(said, got: InfoQ):
    """🔴🔴 ㉑ 보드 판정 **뒤에** 등급을 내린다(확률·생존은 **그대로**다).

    🔴 사다리는 `s7_judge.BREAK_LADDER` 하나다 — 여기서 다시 적지 않는다.
    🔴 빠진 칸은 **방아쇠**로 등록한다(§14) — 채워지면 다시 센다.
    """
    from app.core.stages.s7_judge import BREAK_LADDER
    step, why = step_of(score=int(got.score))
    evals = list(said.evals)
    if step > 0:
        out = []
        for ev in evals:
            grade = ev.grade
            if grade in BREAK_LADDER:
                i = min(len(BREAK_LADDER) - 1,
                        BREAK_LADDER.index(grade) + step)
                grade = BREAK_LADDER[i]
            out.append(ev.model_copy(update={
                "grade": grade, "why": f"{ev.why} · {why}".strip(" ·")}))
        evals = out
    triggers = list(said.triggers) + [
        f"InfoQ — {name} 를 채우면 다시 센다" for name in got.missing[:4]]
    return said.model_copy(update={
        "stance": cap_stance(str(said.stance or ""), score=int(got.score)),
        "evals": evals, "triggers": triggers,
        "notes": list(said.notes) + [f"[㉑] {got.why}"
                                     + (f" · {why}" if why else "")]})
