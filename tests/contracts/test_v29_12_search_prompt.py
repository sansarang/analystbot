"""🔴🔴 **검색 전문가 프롬프트** — 사용자 지시 2026-10-15.

> 그외 변수에 필요한것도 서치 못하냐? 솔라에게 **서치 전문가 프롬프트**를
> 주면 안 되냐? **코드 수정하지 말고**

⚠️ 실측 2026-10-15(Svay Rieng vs Shanghai Shenhua): 모델에게 문지기 규칙을
   안 알려 줘서 `… AFC Champions League Two`(낱말 8개)가 **매 하위마다**
   막혔고, 라인업·결장 질의가 한 번도 안 나가 3+5 통합이 **0건**이 됐다.
"""
from __future__ import annotations

import inspect

from app import llm as rules
from app.core.stages import s4b_gapsearch


def _prompt() -> str:
    """🔴🔴 **LLM 질의 프롬프트의 원본** — 2026-10-17 부터 `s4b_gapsearch.ask`.

    ⚠️ 종전엔 `querywriter.ask`(딥서치의 질의 쓰기)였다. 딥서치를 지우면서
       그 함수도 지웠다 — LLM 이 질의를 쓰는 곳은 **이제 하나**다.
    """
    return inspect.getsource(s4b_gapsearch.ask)


def test_낱말_수는_규칙이_있는_곳에서_온다() -> None:
    """🔴 사본 금지(#1) — 프롬프트가 `6` 을 손으로 적으면 규칙이 바뀔 때 어긋난다."""
    src = _prompt()
    assert "_rules.WORDS_MIN" in src and "_rules.WORDS_MAX" in src, src[:200]
    assert (rules.WORDS_MIN, rules.WORDS_MAX) == (1, 6)


def test_문지기_금지_항목을_알려_준다() -> None:
    src = _prompt()
    for one in ("site:", "따옴표", "연도", "대회 정식명을 쓰지 마라"):
        assert one in src, f"🔴 `{one}` 를 안 알려 준다"


def test_변수_여덟_갈래를_덮으라고_말한다() -> None:
    """🔴 라인업·결장만이 아니라 **다른 변수 재료도** 찾게 한다."""
    src = _prompt()
    for one in ("로테이션", "감독 부임 후 성적", "팀내 불화", "원정 일정",
                "복귀", "징계"):
        assert one in src, f"🔴 `{one}` 가 목표에 없다"


def test_배당_예측_사이트를_빼라고_말한다() -> None:
    """⚠️ 실측: 받은 문서 7건이 전부 배당·예측·스코어 사이트였다(기사 0건)."""
    assert "배당·예측·스코어 사이트는" in _prompt()


def test_현지어를_두_팀_나라_말로_요구한다() -> None:
    assert "두 팀의 나라 말로도" in _prompt()


def test_문지기_자체는_안_건드렸다() -> None:
    """🔴 *"코드 수정하지 말고"* — 규칙은 그대로다."""
    assert rules.query_ok("Svay Rieng injury news") is True
    assert rules.query_ok(
        "Svay Rieng starting lineup AFC Champions League Two") is False
    assert rules.query_ok("Shenhua news 2026") is False


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **득실점으로 수비 불안·공격력을 말한다** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════


def test_전략_전문가가_득실점을_근거로_삼는다() -> None:
    """⚠️ 실측: 재료(`S01`)를 넘겼는데도 모델이 **라인업 이탈만** 보고 수비를
    판단한 실행이 있었다(실점 3.2 ↔ 0.8 을 안 들었다)."""
    import inspect

    from app.core import strategy_llm as sl
    src = inspect.getsource(sl.ask)
    assert "실점" in src and "수비 불안" in src, src[-600:]
    assert "득점" in src and "공격력" in src
    assert "라인업 이탈만 보고 수비를 판단하지 마라" in src


def test_종합_평도_득실점으로_말한다() -> None:
    import inspect

    from app.core.stages import s6_verdict as vd
    src = inspect.getsource(vd.ask)
    assert "수비 불안과 공격력을 득실점으로 말한다" in src, src[-600:]
    # 🔴 그 수를 쓰라고 했으니 **써도 된다**고 함께 적혀 있어야 한다
    assert "묶음의 득점·실점 평균" in src


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **라인업 기사를 찾는다**(지어내지 않는다) — 사용자 결정 2026-10-15
# ══════════════════════════════════════════════════════════════════


def test_질의가_예상_라인업_기사를_노린다() -> None:
    """⚠️ 실측 2026-10-15(Tampines vs Machida · T−2h): XI 0/2 라 축0 을 못 세고
    전략 변수도 0 이어서 확률이 **균등 그대로** 남았다.

    🔴 종전엔 `querywriter.ask`(딥서치 질의)가 이 말을 했다. **딥서치를 지우면서
       (사용자 지시 2026-10-17) 그 함수도 지웠다** — 그래서 질의를 쓰는 곳이
       하나가 됐고, 이 규칙은 그 하나가 들고 있어야 한다(안 옮기면 조용히 잃는다).
    """
    src = _prompt()
    assert "예상 라인업 기사를 노린다" in src, src[-700:]
    for one in ("predicted lineup", "probable XI", "予想スタメン", "首发预测"):
        assert one in src, one


def test_딥서치_질의_쓰기는_사라졌다() -> None:
    """🔴🔴 **지운 길이 조용히 되살아나지 않는다** — 사용자 지시 2026-10-17.

    > 딥서치 삭제!!!!

    ⚠️ `querywriter.ask` 는 ②③ 딥서치의 질의 쓰기였다. 그것이 돌아오면 코드가
       다시 질의 다발을 만들게 된다 — 질의를 쓰는 곳은 **LLM 하나**다.
    """
    from app.core import querywriter as qw
    assert not hasattr(qw, "ask"), (
        "🔴 `querywriter.ask`(딥서치 질의 쓰기)가 되살아났다")
    # 🔴 남아야 하는 것 — 글자 검사·robots·`site:`(⑤-b3 2단과 LLM 서치가 쓴다)
    for one in ("keep", "hosts", "check_hosts", "site_queries", "comp_hint"):
        assert hasattr(qw, one), f"🔴 `querywriter.{one}` 이 같이 지워졌다"


def test_표적_질의도_포메이션_칸에_그것을_쓴다() -> None:
    import inspect

    from app.core.stages import s4b_gapsearch as gs
    src = inspect.getsource(gs.ask)
    assert "`포메이션` 칸이 있으면 예상 라인업 기사를 노린다" in src
    # 🔴 **지어내기 금지**가 같은 자리에 적혀 있어야 한다
    assert "지어내지 마라" in src and "찾는 것은 **기사**다" in src


def test_라인업을_모델_기억으로_만들지_않는다() -> None:
    """🔴🔴 절대규칙 — 사실은 **문서에서만** 온다. 프롬프트가 명단을 달라고
    하면 안 된다(확정 판정은 fotmob 경기 페이지 표식만 쓴다)."""
    import inspect

    from app.core.stages import s4b_gapsearch as gs
    src = inspect.getsource(gs.ask)
    for bad in ("명단을 네가 적어", "예상 XI 를 만들어", "라인업을 추측해"):
        assert bad not in src, bad
