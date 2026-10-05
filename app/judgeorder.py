"""🔴🔴 **v5-A §7 — 판정 순서.** `보강 → 1차 대입 → 반증 → 재대입 → 상한 → pick`.

작업지시 §4-7:

> 판정 순서 변경 — v5 §6 을 **"보강 → 1차 대입 → 반증 → 재대입 → 상한 → pick"**
> 으로(v5-A §7 표). **`enabled=false` 면 반증 단계를 건너뛰고 로그에
> `redteam:off` 한 줄.**

══════════════════════════════════════════════════════════════════
🔴 왜 순서가 바뀌나 — **반증은 등급 후보를 보고 묻는다**
══════════════════════════════════════════════════════════════════

v5-A §4: *"단계 3 시나리오 세트로 코드가 **1차 생존 계산**을 한 뒤, 생존 0.8
이상인 마켓이 하나라도 있을 때만."*
🔴 그래서 **대입이 먼저**다 — 등급 후보가 없으면 반증할 결론도 없고 비용을
   쓸 까닭도 없다.
⚠️ 그리고 반증 **뒤에 다시 대입**한다 — 추가된 시나리오가 그 마켓을 죽이는지
   세어야 등급이 바뀐다. 🔴 그 재대입에서 **M44**(생존율 상승 금지)를 본다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴 v5-A §7 표 **그대로**. ⚠️ 순서가 뜻이다 — 베끼지 않고 여기 한 번 적는다.
ORDER: tuple[str, ...] = ("보강", "1차 대입", "반증", "재대입", "상한", "pick")

#: 🔴 반증이 꺼졌을 때 로그에 남기는 **한 줄**(작업지시 §4-7).
OFF_NOTE = "redteam:off"

#: ⚠️ 반증이 없으면 **재대입도 없다** — 더한 것이 없으니 다시 셀 것이 없다.
_SKIP_WITH_REDTEAM: tuple[str, ...] = ("반증", "재대입")


def off_note() -> str:
    return OFF_NOTE


def redteam_on() -> tuple[bool, str]:
    """🔴 반증을 **돌 수 있나**(설정 스위치만 본다).

    ⚠️ *"돌 때인가"*(생존 0.8+)는 `redteam.due` 가 따로 본다 — 둘은 다른 질문
       이다(스위치 vs 조건).
    """
    from app import deepseek
    return deepseek.stage_on("stage4")


def steps(*, on: bool | None = None) -> tuple[str, ...]:
    """🔴 이 경기에 **실제로 밟는 순서**.

    ⚠️ `on` 은 시험용이다 — 운영에서는 `None` 이고 설정이 답한다.
    """
    got = bool(redteam_on()[0]) if on is None else bool(on)
    if got:
        return ORDER
    # 🔴 **꺼짐** — 반증·재대입을 뺀다. ⚠️ 그 사실을 로그에 남긴다(#3).
    logger.info("[judge] %s — 반증 단계를 건너뛴다(v5-A §7)", OFF_NOTE)
    return tuple(x for x in ORDER if x not in _SKIP_WITH_REDTEAM)


@dataclass
class Outcome:
    """🔴 판정 한 바퀴의 결과. ⚠️ **밟은 단계를 이름으로** 들고 온다(#3)."""

    scenarios: list = field(default_factory=list)
    survival_before: dict = field(default_factory=dict)
    survival_after: dict = field(default_factory=dict)
    steps: tuple = ()
    notes: list = field(default_factory=list)
    #: 🔴🔴 **M44** — 생존율이 올라갔으면 **카드 금지**다
    blocked: str = ""
    added: list = field(default_factory=list)
    #: 🔴 **폐기한 제안** — 지시 ③ 2026-10-05. ⚠️ `added` 가 0 인 것만으로는
    #   *"모델이 0개를 냈다"* 와 *"냈는데 다 버렸다"* 를 가를 수 없다 —
    #   고칠 곳이 프롬프트와 검증층으로 **다르다**(#3 조용한 0 금지).
    dropped: list = field(default_factory=list)


def run(inp, scenarios: list, *, grade, survivals=None, spent_in: int = 0,
        now=None, _net=None) -> Outcome:
    """🔴🔴 **§4-7 순서를 밟는다.** `grade(세트) → {마켓: 생존}`.

    ⚠️ `grade` 는 **호출부가 준다** — 여기서 §6 을 다시 짓지 않는다(#1 사본
       금지). 🔴 이 파일이 아는 것은 **순서**뿐이다.
    """
    from app import redteam
    out = Outcome(scenarios=list(scenarios or []), steps=steps())
    # ── ① 1차 대입
    first = dict(survivals or grade(out.scenarios) or {})
    out.survival_before = dict(first)
    out.survival_after = dict(first)
    if "반증" not in out.steps:
        out.notes.append(f"⚠️ {OFF_NOTE} — 반증 단계를 건너뛴다(v5-A §7)")
        return out
    # ── ② 반증
    got = redteam.run(inp, out.scenarios,
                      survivals=sorted(first.items(), key=lambda kv: -kv[1]),
                      spent_in=spent_in, now=now, _net=_net)
    out.notes.append(f"§4 반증 — {got.why}")
    out.added = list(got.added)
    out.dropped = list(getattr(got, "drops", ()) or [])
    if not got.added:
        return out
    # ── ③ 재대입
    out.scenarios = redteam.merge(out.scenarios, got.added)
    out.survival_after = dict(grade(out.scenarios) or {})
    # ── ④ 🔴🔴 **M44** — 올라가면 카드 금지
    ok, why = redteam.check_survival(out.survival_before, out.survival_after)
    out.notes.append(why)
    if not ok:
        out.blocked = why
    return out


def _clip(said: str, n: int) -> str:
    """🔴 표시 없이 자르지 않는다(출력 규격)."""
    said = " ".join(str(said or "").split())
    return said if len(said) <= n else said[:n] + f"…(+{len(said) - n}자)"


def card_block(out: Outcome) -> list[str]:
    """🔴 카드 하단 **`■ 반증`** 블록(v5-A §4 출력 예).

    ⚠️ 꺼져 있으면 **그 사실 한 줄**이다 — 블록을 숨기지 않는다(#3).
    """
    if "반증" not in (out.steps or ()):
        return [f"  {OFF_NOTE} — 반증 단계가 꺼져 있다(v5-A §7)"]
    from app import redteam
    if out.added:
        rows = [f"  (추가 {len(out.added)}개)"]
    elif out.dropped:
        # 🔴 **냈는데 버렸다** — 무엇을 왜 버렸나가 고칠 곳을 가리킨다
        말 = " · ".join(
            f"{r.get('id') or '?'}({_clip(str(r.get('why') or '까닭 미상'), 90)})"
            for r in out.dropped[:3])
        rows = [f"  (추가 없음 — 제안 {len(out.dropped)}개를 **폐기**했다: {말})"]
    else:
        rows = ["  (추가 없음 — 모델이 제안을 **0개** 냈다 · 폐기 0개)"]
    for market, before in sorted(out.survival_before.items()):
        after = float(out.survival_after.get(market, before))
        status = "proposed" if out.added else "covered"
        rows.append(redteam.card_line(market, status, before=float(before),
                                      after=after,
                                      by=[r.get("id") for r in out.added]))
    if out.blocked:
        rows.append(f"  {out.blocked}")
    return rows
