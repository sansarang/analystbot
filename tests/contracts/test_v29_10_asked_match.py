"""🔴🔴 **남의 경기를 분석하지 않는다** — 사용자 지적 2026-10-15.

⚠️ 실사고 2026-10-15(MLS 11:30): `"Los Angeles FC Austin FC"` 와
   `"LA Galaxy Portland Timbers"` 가 **둘 다** `Avenir de La Marsa vs Etoile
   Métlaoui`(튀니지 Ligue I)로 확정됐다 — 그 행이 `games` 표에서 가장 최근에
   적힌 행이었고 물어본 경기는 표에 **없었다**. 입구가 *"못 찾았다"* 대신
   남의 경기를 `ok` 로 돌려줬고 봇은 16단계를 전부 돌렸다.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.stages.s1_resolve import asked_match


@dataclass
class Ref:
    home_name: str = ""
    away_name: str = ""
    home: str = ""
    away: str = ""


@dataclass
class Q:
    team: str = ""
    opponent: str = ""


TUNIS = Ref(home_name="Avenir de La Marsa", away_name="Etoile Métlaoui")


def test_그_사고를_막는다() -> None:
    ok, why = asked_match(Q("Los Angeles FC", "Austin FC"), TUNIS)
    assert not ok, "🔴 남의 경기가 통과했다"
    assert "물어본 팀이 그 경기에 없다" in why, why
    assert "Avenir de La Marsa" in why, "🔴 사유에 확정된 경기가 없다"


def test_LA_가_La_Marsa_에_걸리지_않는다() -> None:
    """🔴 이 사고의 뿌리 — 토막 `LA` 가 `La Marsa` 에 붙었다."""
    ok, _ = asked_match(Q("LA Galaxy", "Portland Timbers"), TUNIS)
    assert not ok, "🔴 `LA` 가 `La Marsa` 에 걸렸다"


def test_맞는_경기는_통과한다() -> None:
    ref = Ref(home_name="Chicago Fire FC", away_name="Philadelphia Union")
    ok, why = asked_match(Q("Chicago Fire", "Philadelphia Union"), ref)
    assert ok, why


def test_한쪽만_물어도_통과한다() -> None:
    """🔴 `"Norwich"` 처럼 한 팀만 물은 질문을 막지 않는다."""
    ref = Ref(home_name="Norwich City FC", away_name="Southampton FC")
    ok, why = asked_match(Q("Norwich"), ref)
    assert ok, why


def test_짧은_이름과_긴_이름은_같은_팀이다() -> None:
    """🔴 `Como` ↔ `Como 1907` — 느슨하게 만들면 안 되지만 이건 통과다."""
    ref = Ref(home_name="Feyenoord Rotterdam", away_name="Como 1907")
    assert asked_match(Q("Feyenoord", "Como"), ref)[0]


def test_이름_목록으로도_묻는다() -> None:
    """🔴 퇴로(`_try`)는 `Question` 이 없고 이름만 들고 있다."""
    ok, _ = asked_match(["LA Galaxy", "Portland Timbers"], TUNIS)
    assert not ok


def test_물을_이름이_없으면_검문하지_않는다() -> None:
    """🔴 슬레이트·보드가 고른 경기를 막아선 안 된다."""
    assert asked_match(Q("", ""), TUNIS)[0]
    assert asked_match([], TUNIS)[0]


def test_세_자리_전부에_문이_달렸다() -> None:
    """🔴 배선 — 확정 자리 셋(입구·철자 퇴로·⑥단) 전부가 이 문을 지난다."""
    said = __import__("pathlib").Path(
        "app/core/stages/s1_resolve.py").read_text()
    assert said.count("asked_match(") >= 4, "🔴 문이 덜 달렸다(정의 1 + 자리 3)"
