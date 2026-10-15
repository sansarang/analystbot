"""🔴🔴 **⑯ 검열의 거짓 양성** — 사용자 지시 2026-10-15 *"왜 llm 평문이 지어내냐"*.

실측(오늘 실행 전부 · 위반 54건):
  · 길이 초과 **27건**(227~279자) → 🔴 상한을 **300** 으로 올렸다
  · (라) **19건 전부 거짓 양성** — `S01-home은`·`S01-home의`·`S01-away가`(조사) ·
    `S01`(집안 접두)
  · (다) 5건 중 **4건 거짓 양성** — `UEFA Champions League`(대회 이름) ·
    `WW DD`(폼 글자)

🔴 이 계약은 **그 네 모양이 다시 위반으로 잡히면** 빨개진다.
"""
from __future__ import annotations

from app.core.stages import s6_verdict as V

BOX = [
    "확률 — 홈 33.3% · 무 33.3% · 원정 33.3%",
    "  변수 `S01-home` [recent_pattern] 자리 ['axis1'] — 최근 5경기 W W D D",
    "  변수 `S01-away` [recent_pattern] 자리 ['axis1'] — 최근 3경기 W L L",
    "대회 — AFC Champions League Two",
]


def _bad(*said: str) -> list:
    got = V.Verdict(sentences=list(said), refs=["확률"] * len(said),
                    pick="draw", score="1-1")
    return V.judge(got, BOX)[1]


def test_vd14_josa() -> None:
    """VD14 🔴 **조사가 붙은 변수 번호**를 (라) 가 잡지 않는다."""
    for one in ("S01-home은", "S01-home의", "S01-away가", "S01-home이",
                "S01-home과"):
        bad = _bad(f"{one} 최근 흐름이 약하다.")
        assert not [x for x in bad if "(라)" in x], f"🔴 {one} — {bad}"


def test_vd15_family_prefix() -> None:
    """VD15 🔴 **집안 접두**(`S01` ↔ `S01-home`)는 같은 것으로 센다."""
    assert not [x for x in _bad("S01 집안이 균등을 만들었다.") if "(라)" in x]


def test_vd16_not_a_person() -> None:
    """VD16 🔴 **대회 이름·폼 글자**를 사람 이름으로 세지 않는다."""
    for one in ("AFC Champions League Two 라 로테이션이 크다.",
                "최근 WW DD 흐름이다."):
        assert not [x for x in _bad(one) if "(다)" in x], one


def test_vd17_sent_max() -> None:
    """VD17 🔴 문장 상한은 **300 자 이상**이다(실측 최장 279자)."""
    assert V.SENT_MAX >= 300, f"🔴 SENT_MAX={V.SENT_MAX}"


def test_vd18_still_catches() -> None:
    """VD18 🔴 그래도 **진짜 지어냄**은 잡는다 — 없는 번호·없는 수."""
    assert [x for x in _bad("S09-home 이 홈을 밀었다.") if "(라)" in x]
    assert [x for x in _bad("홈 승률이 42%p 다.") if "(가)" in x]
