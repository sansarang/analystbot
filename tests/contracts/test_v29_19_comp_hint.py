"""🔴🔴 **대회 유형에 맞춘다** — 사용자 지시 2026-10-15.

> 딥서치·llm 서치할 때 **대륙경기, 그에 맞게 서치해야 한다** · 변수 관련 모든
> 사항도 **그 경기에 맞게** 해야 한다

🔴 글자는 `querywriter.comp_hint` **하나**가 만든다(사본 금지) — 유형은 표가
   든다(`competition.row_of(key)["kind"]`).
"""
from __future__ import annotations

import inspect

from app.core.querywriter import comp_hint
from app.core.schema import MatchRef


def R(comp: str) -> MatchRef:
    return MatchRef(id="m", sport="soccer", home="team:100001",
                    away="team:100002", home_name="h", away_name="a",
                    competition=comp, competition_short=comp,
                    kickoff_utc="2026-10-15T10:00:00+00:00")


def test_대륙_대회를_가린다() -> None:
    for comp in ("AFC Champions League Two", "UEFA Champions League",
                 "AFC Champions League Elite"):
        said = comp_hint(R(comp))
        assert "대륙 대회다" in said, (comp, said[:80])
        for one in ("두 팀 나라 말", "조별 순위", "로테이션", "장거리 이동"):
            assert one in said, (comp, one)


def test_리그는_리그로_본다() -> None:
    said = comp_hint(R("Championship"))
    assert "리그다" in said and "대륙 대회 일정과 섞지 않는다" in said, said


def test_못_알아보면_빈_글자다() -> None:
    """🔴 지어내지 않는다(#4) — 모르는 대회에 대륙 지시문을 붙이면 거짓이다."""
    assert comp_hint(R("무슨무슨 컵 2026")) == ""


def test_네_자리가_그_글자를_쓴다() -> None:
    """🔴 배선 — 딥서치 질의 · LLM 표적 질의 · 전략 · 종합 평."""
    from app.core import querywriter as qw
    from app.core import strategy_llm as sl
    from app.core.stages import s4b_gapsearch as gs
    from app.core.stages import s6_verdict as vd
    assert "comp_hint(ref)" in inspect.getsource(qw.ask)
    for mod, fn in ((gs, "ask"), (sl, "ask"), (vd, "ask")):
        src = inspect.getsource(getattr(mod, fn))
        assert "comp_hint(ref)" in src, f"🔴 {mod.__name__}.{fn} 가 안 쓴다"


def test_글자를_베끼지_않았다() -> None:
    """🔴 사본 금지(#1) — 네 자리가 **같은 함수**를 부른다(글을 옮겨 적지 않는다)."""
    import pathlib
    for f in ("app/core/stages/s4b_gapsearch.py", "app/core/strategy_llm.py",
              "app/core/stages/s6_verdict.py"):
        said = pathlib.Path(f).read_text(encoding="utf-8")
        assert "대륙 대회다" not in said, f"🔴 {f} 가 글자를 베꼈다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **AFC 컵도 같은 대회다** — 사용자 지적 2026-10-15
# ══════════════════════════════════════════════════════════════════


def test_afc_컵이_대륙_대회로_잡힌다() -> None:
    """⚠️ 실측 2026-10-15: `AFC Cup`·`AFC 컵` 은 **못 알아봤다**(지시문이 빈
    글자) — ACL2 가 2024 년에 AFC 컵을 대체한 대회다."""
    from app.core import competition as c
    for name in ("AFC Cup", "AFC 컵", "에이에프씨컵"):
        key, _why = c.key_of(competition=name)
        assert key == "league:ACL2", (name, key)
        assert "대륙 대회다" in comp_hint(R(name)), name


def test_afc_가_uefa_로_안_간다() -> None:
    """🔴 실측 2026-10-15: `AFC Champions League 2` 가 `champions league` 글자로
    **UEFA UCL** 에 걸렸다 — 남의 대회 기준을 쓰면 수가 전부 거짓이 된다."""
    from app.core import competition as c
    for name in ("AFC Champions League 2", "AFC Champions League Two"):
        assert c.key_of(competition=name)[0] == "league:ACL2", name
    assert c.key_of(competition="UEFA Champions League")[0] == "league:UCL"


def test_자동_등록_열쇠는_지시문이_없다() -> None:
    """⚠️ 전부터 그렇다(내 수정과 무관) — 맨 `Champions League` 는
    `league:fotmob42`(자동 등록)로 가고 그 행에 `kind` 가 없어 **빈 글자**다.
    🔴 지어내지 않는 쪽이 맞다 — 유형을 모르면 지시문을 붙이지 않는다."""
    from app.core import competition as c
    key, _why = c.key_of(competition="Champions League")
    assert key.startswith("league:fotmob"), key
    assert comp_hint(R("Champions League")) == ""
