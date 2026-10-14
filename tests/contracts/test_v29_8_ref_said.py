"""🔴🔴 **근거는 서술형이다** — 사용자 지시 2026-10-15.

> 근거는 ???? **서술형으로 바꿔라**

꼬리표(`axis1·S01`)를 그대로 찍지 않는다. 묶음에서 **그 글자를 품은 줄**을
찾아 그 줄의 글자로 풀어 쓴다. 🔴 새 글자를 짓지 않고, 묶음에 없는 꼬리표는
**없다고 적는다**(#3 조용한 0 금지).
"""
from __future__ import annotations

from app.core.stages import s6_verdict as vd

BOX = [
    "확률 — 홈 44.1% · 무 26.1% · 원정 29.8%",
    "λ(기대 득점) — 홈 1.453 · 원정 1.150 · 합 2.602",
    "스코어 상위 — 1-1 12.4% · 1-0 10.1%",
    "변수 11개 — 확률에 닿는 자리(축·λ상수)에 든 것만:",
    "  변수 `S01-home` [recent_pattern] 자리 ['axis1', 'hypo'] — 최근 5경기 "
    "L L L L W · 득점 평균 1.8(보정 1.0)",
    "  변수 `IR12-home` [team_stats] 자리 ['axis1'] — Norwich City FC 무승 4경기",
    "  axis1 — 홈 -0.0620 · 원정 0.9550 · 차 -1.0170 · 근거 변수 ['S01-home']",
]


def test_변수_꼬리표는_그_변수_글자로_풀린다() -> None:
    said = vd.ref_said("S01-home", BOX)
    assert "변수 S01-home" in said, said
    assert "최근 5경기" in said, "🔴 묶음 줄의 글자가 안 들어왔다"
    assert "`" not in said, "🔴 꼬리표를 그대로 찍었다"


def test_축_꼬리표는_차값과_함께_풀린다() -> None:
    said = vd.ref_said("axis1", BOX)
    assert "축1" in said and "-1.0170" in said, said


def test_여러_꼬리표는_한_문장으로_이어진다() -> None:
    said = vd.ref_said("axis1·IR12-home", BOX)
    assert "축1" in said and "변수 IR12-home" in said, said
    assert said.endswith("에서 왔다"), said


def test_확률_λ_같은_줄도_서술형이_된다() -> None:
    said = vd.ref_said("확률·λ", BOX)
    assert "확률 줄" in said and "λ(기대 득점) 줄" in said, said


def test_묶음을_안_가리키는_근거는_그렇게_적는다() -> None:
    """🔴 조용히 넘기지 않는다 — (라) 검열이 잡는 그 자리다."""
    said = vd.ref_said("IR99", BOX)
    assert "묶음의 어느 줄도 안 가리킨다" in said, said


def test_근거를_문장_통째로_줘도_열쇠를_긁는다() -> None:
    """⚠️ 실측 2026-10-15: solar 는 꼬리표가 아니라 **문장**을 돌려줬다."""
    said = vd.ref_said("axis1 — 홈 -0.0620 원정 0.9550 차 -1.0170 S01-home", BOX)
    assert "축1(차 -1.0170)" in said, said
    assert "변수 S01-home" in said, said
    assert "묶음의 어느 줄도" not in said, "🔴 서술형 근거를 못 읽었다"


def test_긴_열쇠가_짧은_열쇠를_가로채지_않는다() -> None:
    said = vd.ref_said("S01-home", BOX)
    assert "변수 S01-home" in said, said


def test_근거가_비면_칸으로_남는다() -> None:
    assert vd.ref_said("", BOX) == "⬜ 근거 없음"
    assert vd.ref_said("⬜ 근거 없음", BOX) == "⬜ 근거 없음"


def test_카드_글에_꼬리표_나열이_안_남는다() -> None:
    """🔴 `said_of` 가 찍는 줄에 **번호 나열**이 없어야 한다."""
    got = vd.Verdict(sentences=["확률은 홈 44.1%다."], refs=["axis1"])
    said = vd.said_of(got, BOX, provider="solar")
    assert "· 근거 — 축1(차 -1.0170)" in said, said
    assert "근거 `axis1`" not in said, "🔴 옛 꼴이 남았다"


def test_상한을_넘기면_몇_개를_뺐는지_적는다() -> None:
    """🔴 조용한 0 금지 — 토막을 자르면 그 사실이 남아야 한다."""
    said = vd.ref_said("확률 λ 스코어 상위 axis1 S01-home IR12-home", BOX)
    assert "외 " in said and "개" in said, said


def test_읽는_순서는_묶음_순서다() -> None:
    said = vd.ref_said("axis1 S01-home", BOX)
    assert said.index("변수 S01-home") < said.index("축1"), said
