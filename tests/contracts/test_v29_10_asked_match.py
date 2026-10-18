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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **대회 일정 퇴로** — LLM 이 죽어도 경기를 찾는다(지시 2026-10-15)
# ══════════════════════════════════════════════════════════════════


def test_일정_퇴로가_배선돼_있다() -> None:
    """🔴 만든 것은 부르는 곳이 있어야 한다(규율 #2)."""
    said = __import__("pathlib").Path(
        "app/core/stages/s1_resolve.py").read_text()
    assert "async def _by_schedule(" in said, "🔴 퇴로가 없다"
    assert "got = await _by_schedule(" in said, "🔴 안 불린다"


def test_일정_퇴로는_LLM_을_안_쓴다() -> None:
    """🔴 이 퇴로의 존재 이유 — 공급자가 죽어도 도는 길이다."""
    import inspect

    from app.core.stages import s1_resolve
    src = inspect.getsource(s1_resolve._by_schedule)
    for bad in ("llm.ask", "_spell", "solar"):
        assert bad not in src, f"🔴 퇴로가 `{bad}` 를 쓴다"
    assert "verify.same_team" in src, "🔴 이름 문을 안 쓴다"
    assert "_UPSERT_GAME" in src, "🔴 적는 SQL 이 사본이다"


def test_일정_창은_한_곳에_있다() -> None:
    from app.core.stages import s1_resolve
    assert s1_resolve.SCHED_BACK_H > 0 and s1_resolve.SCHED_AHEAD_H > 0


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **한글로 물어도 통과한다 — 영어로 바꿔 견준다**(사용자 지시 2026-10-18)
# ══════════════════════════════════════════════════════════════════
#
#  > fc서울,강원fc 라인업 … **영어로 질문하는걸로 고쳐라**
#
#  ⚠️ 실측 2026-10-18: 한글 질문이 **맞는 경기를 두 번 거부했다** —
#     `물음 전북 현대 모터스 ↔ 확정 Jeonbuk Hyundai Motors FC vs Jeju SK` ·
#     `물음 파지아노 오카야마 ↔ 확정 Fagiano Okayama FC vs Vissel Kobe`.
#     두 이름 다 `config/teams_54.yaml`·이름표가 **알고 있었다**(열쇠까지 났다).

K1 = Ref(home_name="Jeonbuk Hyundai Motors FC", away_name="Jeju SK",
         home="team:000314", away="team:000313")


def test_한글로_물어도_같은_팀이면_통과한다(monkeypatch) -> None:
    """🔴 ② 영어 풀이 — 이름표가 아는 이름은 **LLM 없이** 풀린다.

    🔴 돌연변이: ② 를 지우면 한글 질문이 다시 거부된다.
    ⚠️ `findwriter.ask` 를 막아 두고 돈다 — 이름표만으로 돼야 한다(LLM 0).
    """
    from app.core import findwriter

    def _never(*a, **k):                        # noqa: ANN002, ANN003
        raise AssertionError("🔴 이름표가 아는 이름인데 LLM 을 불렀다")
    monkeypatch.setattr(findwriter, "ask", _never)
    ok, why = asked_match(Q("전북 현대 모터스"), K1)
    assert ok, why
    assert "영어로 바꿔 맞췄다" in why and "Jeonbuk" in why, why
    # 🔴 상대만 한글로 물어도 된다(어느 쪽이든 하나 맞으면 통과)
    assert asked_match(Q("", "제주 SK"), K1)[0]
    # 🔴🔴 **느슨해지지 않는다** — 다른 팀을 한글로 물으면 **거부**한다
    bad, why2 = asked_match(Q("울산 HD"), K1)
    assert not bad, why2
    assert "영어 풀이도 안 맞았다" in why2, why2


def test_라틴_이름은_영어_풀이를_안_돈다(monkeypatch) -> None:
    """🔴 ② 는 ① 이 떨어졌을 때 **라틴이 아닌 이름에만** 돈다(비용·통로 하나).

    ⚠️ 돌연변이: 라틴 검사를 지우면 남의 경기마다 이름 풀이가 돌아 LLM 을 태운다.
    """
    from app.core.stages import s1_resolve as s1

    def _never(said):                           # noqa: ANN001
        raise AssertionError(f"🔴 라틴 이름에 영어 풀이를 돌렸다 — {said}")
    monkeypatch.setattr(s1, "_en_of", _never)
    assert not asked_match(Q("Suwon FC", "Pohang Steelers"), K1)[0]
