"""🔴🔴 **§0 옛 경로 고정** — 비교 시험 지시서 2026-10-12 §0.

> `app/core/legacy/old_engine.py` — 마지막 옛 구조 커밋의 축0~3 합산·β·λ·시뮬
> 로직을 **그대로** 옮긴다(수정 금지, 태그 `legacy-4axis`).
> 계약 **K0**: 옛 경로 코드 해시가 태그와 다르면 **실패**.

🔴 왜 해시인가 — 비교 시험의 **기준**이 조용히 움직이면 그 시험은 아무것도 말하지
   않는다. ⚠️ 고쳐야 할 이유가 생기면 그것은 *"옛 경로를 바꾼다"* 는 뜻이고, 그
   결정은 **사용자**가 한다(그때 이 해시를 함께 고친다).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "app/core/legacy/old_engine.py"

#: 🔴🔴 **태그 `legacy-4axis`** — 얼린 그 파일의 sha256
#
#  ⚠️ **2026-10-15 에 한 번 바뀠다** — 사용자 결정으로 **상성을 삭제**했다
#     (축 종합·쪽값이 λ 를 안 움직인다 · 이동 0 고정). K0(얼림)을 그 지시가
#     풀었고, 그 밖의 줄은 **하나도 안 건드렸다**.
#  🔴 옛 해시(2026-10-12 측정): 71def33640d1a7d41b7731700960fef8509fc7c41ac85741c80c9317ec6ee53f
TAG_SHA = "5ec097aadabcb32f39524edef6695702162d7dfc6fa5b322be8a09e9beae9140"


def test_k0_legacy_hash_matches_the_tag() -> None:
    """🔴🔴 **K0** — 한 글자만 바뀌어도 빨개진다."""
    got = hashlib.sha256(LEGACY.read_bytes()).hexdigest()
    assert got == TAG_SHA, (
        f"🔴 **K0 위반** — 옛 경로가 바뀌었다\n  지금 {got}\n  태그 {TAG_SHA}\n"
        "  ⚠️ 비교 시험의 기준이 움직이면 그 시험은 아무것도 말하지 않는다.")


def test_legacy_has_no_floor_path() -> None:
    """🔴 옛 경로에는 **Elo 바닥이 없다**(그것이 새 구조의 것이다)."""
    said = LEGACY.read_text(encoding="utf-8")
    for bad in ("probfloor", "floor=", "shadow"):
        assert bad not in said, bad


def test_legacy_keeps_all_four_axes() -> None:
    """🔴 옛 경로는 **축0~3 네 개**를 합산한다(새 구조는 둘만 쓴다)."""
    from app.core.legacy import old_engine as oe
    # ⚠️ 한 줄 꼴은 `{"축": {"att": {home, away}, "dfn": {…}}}` 다(그 커밋의 F3 식)
    one = {"att": {"home": 1.0, "away": 0.0}, "dfn": {"home": 1.0, "away": 0.0}}
    said = oe.sides_move({"axis0": one, "axis2": one, "axis3": one},
                         {"axis0": 0.3, "axis2": 0.2, "axis3": 0.2},
                         beta=0.25, cap=0.35)
    # 🔴 축2·축3 이 **움직인다** — 새 구조에서는 안 움직인다(v12 계약이 그것을 센다)
    only0 = oe.sides_move({"axis0": one}, {"axis0": 0.3}, beta=0.25, cap=0.35)
    assert said["home"] > only0["home"], (said, only0)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§6 운영 그림자 기간** — 카드마다 M1·M3 를 **둘 다** 기록
# ══════════════════════════════════════════════════════════════════
#
#  > 판정과 무관하게 지금부터 운영 카드마다 **M1·M3 확률을 둘 다** 기록
#  > (최종 확률은 현 운영판). 결과 30경기마다 같은 지표로 자동 채점·보고.


def test_operation_uses_the_frozen_engine() -> None:
    """🔴🔴 **운영 교체**(사용자 결정 2026-10-12) — 운영 ⑯ 의 수는 **얼린 M1** 이다.

    ⚠️ 방향이 뒤집혔다: 종전에는 *"새 구조가 판정 · 옛 구조가 그림자"* 였다.
       🔴 460경기 비교 시험에서 M3 가 **어느 지표에서도 M1 을 앞서지 못했다**.
    🔴 그래서 ⑯ 은 `legacy/old_engine.run` 의 수를 **그대로** 쓰고(다시 계산하지
       않는다 · K0), **M3 가 그림자**다.
    """
    said = (ROOT / "app/core/probmodel.py").read_text(encoding="utf-8")
    assert "from app.core.legacy import old_engine" in said
    # 🔴 운영 수가 M1 에서 온다(그 대입이 있다)
    i = said.index("said_m1 is not None and said_m1.ok()")
    assert "got.home, got.draw, got.away = (said_m1.home" in said[i:i + 400]
    # 🔴 그림자는 M3 다
    j = said.index("got.shadow = dict(said_m3)")
    assert j > i and "M3 **새 경로**" in said


def test_card_records_both_numbers() -> None:
    """🔴 카드가 **최종(M3)·그림자(M1)·바닥** 셋을 적는다(채점이 그것을 읽는다)."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "그림자 확률" in said and "바닥(Elo)" in said
    got = (ROOT / "tools/score_cards.py").read_text(encoding="utf-8")
    for want in ("SHADOW", "FLOOR", "REPORT_EVERY"):
        assert want in got, want
