"""🔴🔴 **보드 없음 결론 규칙 (가)** — 사용자 결정 2026-10-13(갈림길 답).

> 갈림길 답 = **(가)**. 카드 결론 줄에 박는다(`⏸ 보류 — 보드가 없다` 삭제).
> 등급 상한(조건부)은 그대로 적용.
>
> (가) 확신 구간 **상위 30% 안** + 대회 상한 없음 → **간다** · 구간 안 + 상한
>     조건부 → **조건부** · 구간 **밖** → **접는다**

🔴 **보드(마켓 줄)를 읽지 않는다** — 결론은 **봇 확률**과 **측정된 구간표**
   (`bands`) 하나로 선다(계약 CL7 이 이 파일에서 그 낱말들을 센다). ⚠️ `bands.CUTS` 는 백필 460경기에서 잰 분위다(손값이 아니다).
🔴 **상한**은 대회 백필이 끝났나로 정한다 — `club_continental` 인데 그 대회의
   **바닥 계수 판**(`config/base_model.yaml`)이 없으면 *"백필 미완"* 이고 상한은
   **조건부**다(§5-6: *"대회마다 백필 판정이 끝나기 전에는 … 등급 상한 조건부"*).
⚠️ 이 모듈은 **확률을 만들지 않는다** — 글자와 세 갈래만 정한다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 세 갈래(카드가 이 글자를 적는다)
PICKS: tuple[str, ...] = ("간다", "조건부", "접는다")

#: 🔴 백필이 끝나야 상한이 풀리는 대회 유형
CAP_KINDS: tuple[str, ...] = ("club_continental", "national_friendly")


def cap_of(kind: str) -> tuple[str, str]:
    """🔴 그 대회의 **등급 상한**. `("조건부"|"", 사유)`."""
    from app import rules
    from app.core import competition as _cp
    said = str(kind or "")
    got_kind = _cp.kind_require(said)[0]
    if got_kind not in CAP_KINDS:
        return "", f"상한 없음(대회 유형 `{got_kind or '미등록'}`)"
    box = dict(rules.base_model(said) or {})
    if box.get("n"):
        return "", (f"상한 없음 — `{said}` 백필이 끝났다(바닥 계수 표본 "
                    f"{box.get('n')}경기)")
    return "조건부", (f"🔴 **대회 백필 미완** — `{said}` 의 바닥 계수 판이 없다 "
                      f"→ 등급 상한 **조건부**(§5-6)")


def of(top: float | None, *, kind: str,
       fold_why: str = "") -> tuple[str, str]:
    """🔴🔴 규칙 (가) — `(간다|조건부|접는다, 사유)`. 확률이 없으면 `("", 사유)`.

    🔴 `fold_why` 가 오면 **상한이 접는다**다(P5 시장 괴리 + ⬜ 입력) — 규칙 (가)가
       `간다`·`조건부`를 내도 **접는다**로 내린다. 그 사유를 함께 적는다.
    """
    from app.core import bands
    if top is None:
        return "", "⬜ **결론 없음** — 확률이 없다(구간을 못 잰다)"
    said_band = bands.of(float(top))
    cap, why_cap = cap_of(kind)
    if not said_band:
        return "접는다", (f"🔴 **접는다** — 최고 확률 {float(top):.1%} 가 "
                          f"**확신 구간 밖**이다(상위 30% 문턱 "
                          f"{bands.CUTS[-1][1]:.1%}) · {why_cap}")
    if fold_why:
        return "접는다", (f"🔻 **접는다**(상한) — 확신 구간 **{said_band}**"
                          f"(최고 {float(top):.1%})인데 {fold_why} · {why_cap}")
    if cap:
        return "조건부", (f"**조건부** — 확신 구간 **{said_band}**"
                          f"(최고 {float(top):.1%}) · {why_cap}")
    return "간다", (f"**간다** — 확신 구간 **{said_band}**"
                    f"(최고 {float(top):.1%}) · {why_cap}")


def line(top: float | None, *, kind: str, fold_why: str = "") -> str:
    """🔴 카드 결론 줄 한 줄(규칙 (가)를 글자로)."""
    pick, why = of(top, kind=kind, fold_why=fold_why)
    head = {"간다": "✅", "조건부": "🟡", "접는다": "🔻"}.get(pick, "⬜")
    # ⚠️ 글자에 **그 두 낱말을 적지 않는다** — 계약 CL7 이 이 모듈에서 그 글자
    #    **0건**을 센다(규칙이 시장을 읽지 않는다는 뜻이고, 설명이 그 낱말을
    #    담으면 계약이 무의미해진다). 🔴 대신 *"봇 확률만"* 이라고 적는다.
    return (f"{head} {why} · 🔴 **보드 없음 결론 규칙 (가)**(사용자 결정 "
            f"2026-10-13) — **봇 확률만** 쓴다")
