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
    # ⚠️ **두 자리로 줄었다**(지시 2026-10-18) — ⑯ 종합 평 프롬프트를 **변수
    #    만**으로 줄이면서 대회 힌트 줄이 걷혔다. 전략(⑤-b2)은 묻지 않는다.
    from app.core.stages import s4b_gapsearch as gs
    assert "comp_hint(ref)" in inspect.getsource(gs.ask)


def test_글자를_베끼지_않았다() -> None:
    """🔴 사본 금지(#1) — 네 자리가 **같은 함수**를 부른다(글을 옮겨 적지 않는다)."""
    import pathlib
    for f in ("app/core/stages/s4b_gapsearch.py",):
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


def test_자동_등록이_손표를_가리지_않는다() -> None:
    """🔴🔴 **바뀐 사실**(2026-10-16) — 자동 등록 파일이 **손 표를 가렸다**.

    ⚠️ 종전엔 맨 `Champions League` 가 `league:fotmob42`(자동 등록)로 갔다 —
       `key_of` 가 자동 등록을 **③ 글자 표기보다 먼저** 보기 때문이다. 같은 병이
       오늘 `Liga MX`(→ `league:fotmob230`)에서 다시 났다.
    🔴 그래서 **손 표에 있는 번호의 자동 파일 13개를 치웠다**(원본이 둘이면
       안 된다 · 사본 금지). 이제 그 이름들은 **손 표**로 선다.
    """
    from app.core import competition as c
    key, _why = c.key_of(competition="Champions League")
    assert key == "league:UCL", key
    assert comp_hint(R("Champions League")) != ""
    # 🔴 번호로도 같은 곳으로 간다
    assert c.key_of(league_id=42)[0] == "league:UCL"
    assert c.key_of(league_id=230)[0] == "league:MEX1"
