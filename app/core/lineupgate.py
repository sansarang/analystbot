"""🔴🔴 **라인업 신원 검문** — 사용자 지시 2026-10-11(라인업 신원 통일) ③.

> 멈춤 조건(상성 S2 진입 **전** 검문):
>   (a) 양 팀 각 11명 전원 id 확정
>   (b) GK 정확히 1명
>   (c) 오늘 XI 의 id 가 결장·명단 제외·교체 "없는 선수"·꺼진 무기 목록에 **하나도
>       없다**
> 어기면 상성·확률을 내지 않고 **"라인업 신원 미확정 — 누구"** 카드.
> **숫자를 낸 채 🔴만 다는 것 금지.**

⚠️ 왜 — 실사고 2026-10-11(가와사키–나고야 캡처): 브로더센·와키자카·나가이·이즈미가
   **선발이면서 동시에** 결장·교체·무기 꺼짐으로 들어갔다. 카드는 그 상태로 확률
   51% 를 **냈다**. 🔴 그 숫자는 서로 모순인 입력으로 만든 것이므로 내면 안 된다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴 (a) — 한 팀의 선발 수
XI_N = 11
#: 🔴 (b) — GK 는 **정확히** 이만큼
GK_N = 1


@dataclass
class Gate:
    """🔴 검문 결과. ⚠️ `ok=False` 면 **상성·확률을 내지 않는다**."""

    ok: bool = True
    why: str = ""
    #: 🔴 "누구"를 적는다 — 카드가 그 이름(또는 id)을 그대로 보인다
    names: list[str] = field(default_factory=list)

    def card(self) -> str:
        """🔴 카드가 그대로 쓰는 한 줄."""
        if self.ok:
            return ""
        return ("🔴🔴 **라인업 신원 미확정** — "
                + (", ".join(self.names) if self.names else "누구인지도 못 짚었다")
                + f" · {self.why}")


def check(*, ids: dict, pos: dict, clash: dict) -> Gate:
    """🔴🔴 ③ — 세 검문. `ids`·`pos`·`clash` 는 **팀 쪽**(`home`·`away`)별이다.

    `ids[side]`   — 오늘 선발의 **id 목록**(못 푼 자리는 빈 글자로 들어온다)
    `pos[side]`   — 그 XI 에서 **GK 로 읽힌 자리들**(캡처·fotmob 의 포지션)
    `clash[side]` — `{id: [걸린 목록 이름…]}` — 결장·명단 제외·없는 선수·꺼진 무기
    """
    bad: list[str] = []
    who: list[str] = []
    for side in ("home", "away"):
        rows = [str(x) for x in (dict(ids or {}).get(side) or [])]
        got = [x for x in rows if x.strip()]
        if len(got) != XI_N:
            bad.append(f"(a) `{side}` id 확정 {len(got)}명 — {XI_N}명이어야 한다")
            who += [f"{side} 못 푼 자리 {len(rows) - len(got)}개"] if rows else []
        n_gk = len([x for x in (dict(pos or {}).get(side) or [])
                    if str(x).upper() == "GK"])
        if n_gk != GK_N:
            bad.append(f"(b) `{side}` GK {n_gk}명 — 정확히 {GK_N}명이어야 한다")
    for side in ("home", "away"):
        for ident, rows in dict(dict(clash or {}).get(side) or {}).items():
            said = " · ".join(str(x) for x in (rows or []))
            bad.append(f"(c) `{side}` `{ident}` 가 선발인데 {said} 에도 있다")
            who.append(str(ident))
    if not bad:
        return Gate(ok=True)
    return Gate(ok=False, why=" / ".join(bad), names=list(dict.fromkeys(who)))


def clash_of(*, xi_ids: dict, boxes: dict) -> dict:
    """🔴 (c) 의 `clash` 를 만든다 — **id 로만** 견준다(이름 비교 금지).

    `xi_ids[side]` — 오늘 선발 id 목록
    `boxes[side]`  — `{목록 이름: [id …]}`(결장·명단 제외·없는 선수·꺼진 무기)
    """
    out: dict = {}
    for side in ("home", "away"):
        mine = {str(x) for x in (dict(xi_ids or {}).get(side) or []) if x}
        for name, rows in dict(dict(boxes or {}).get(side) or {}).items():
            for ident in {str(x) for x in (rows or []) if x}:
                if ident in mine:
                    out.setdefault(side, {}).setdefault(ident, []).append(
                        str(name))
    return out
