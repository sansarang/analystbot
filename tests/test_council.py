"""[변수 평의회 2026-09-06] 심의는 판정 **앞**에 서는 재료 단계다.

🔴 재판정이 아니다. "원판정 → 심의 → 최종" 이 아니라, 심의 결과가 자료1~11 과
   같은 상에 올라가고 판정이 **한 번** 결론을 낸다.
   그래서 이동 상한·잡음 판별·우세 반전 처리가 전부 필요 없다.
"""
from __future__ import annotations

import pytest

from app.engine import council


def _jg(tags=1, **kw):
    st = {"home": [{"확인": "공식", "유형": "retirement", "제목": "은퇴식"}]} if tags else {}
    jg = {"sport": "kbo", "game_id": 1, "home": "SSG Landers",
          "away": "Doosan Bears", "situation_tags": st,
          "research": {"home_news": [{"title": "김성현 은퇴식 특별 엔트리 등록"}]}}
    jg.update(kw)
    return jg


def test_targets_are_games_with_situation_tags():
    """🔴 "상황판정이 무관인 경기"가 아니다 — 그건 판정 뒤에나 안다.

    심의는 판정 앞에 서므로 **태그가 수집된 경기**가 대상이다.
    """
    games = [_jg(1), _jg(0), _jg(1)]
    assert len(council.targets(games)) == 2


def test_slate_cap_is_enforced_and_loud():
    """상한 초과는 조용히 자르지 않는다 — 나머지가 심의 없이 간다는 사실이 로그로."""
    from app.config import get_settings

    cap = int(get_settings().council_slate_cap)
    got = council.targets([_jg(1) for _ in range(cap + 3)])
    assert len(got) == cap


def test_deliberation_never_produces_percentage_points():
    """🔴 심의가 만드는 것은 **사실**이지 %p 가 아니다.

    프롬프트는 %p 를 **금지하는 문장**으로만 언급한다. 출력 계약(JSON)에는
    숫자 칸이 없어야 한다 — 칸이 있으면 모델이 채운다.
    """
    assert "확률이나 %p 를 말하지 마라" in council.DELIBERATE
    assert "불명" in council.DELIBERATE
    # 출력 JSON 계약에 숫자 칸이 없다.
    contract = council.DELIBERATE.split("JSON 만 출력한다:")[-1]
    for banned in ("%p", "확률", "p_home", "크기", "조정"):
        assert banned not in contract, f"출력 계약에 {banned} 칸이 있다"


def test_investigation_forbids_invention():
    """기사에 없으면 '없음'이 답이다 — 지어내면 심의 전체가 오염된다."""
    assert "없음" in council.INVESTIGATE
    assert "추측" in council.INVESTIGATE


def test_payload_is_a_material_not_a_conclusion():
    """자료2 확장으로 들어간다 — 프롬프트 구조를 바꾸지 않는다."""
    jg = _jg(1, council={"조사": {"라인업변화": "선발 출전"}, "조사경로": "perplexity",
                         "심의": {"기전": "라인업변화", "방향": "홈",
                                  "확실성": "뒷받침", "사유": "타순이 밀렸다"}})
    blk = council.payload(jg)
    assert set(blk) == {"상황·심의"}
    assert blk["상황·심의"]["방향"] == "홈"
    assert "%p" not in str(blk)


def test_payload_empty_without_council():
    assert council.payload({}) == {}


def test_card_line_marks_unresolved_deliberation():
    """심의 후에도 불명이면 그 이력이 남는다 — 떠넘김이 아니다."""
    jg = {"council": {"심의": {"방향": "불명", "기전": "없음",
                               "사유": "기사에 기용 변화 언급이 없다"}}}
    line = council.card_line(jg)
    assert "불명" in line and "기사에 기용 변화" in line


def test_prompt_tells_judge_it_is_material_not_verdict():
    from app.engine.prompts import MATCHUP

    assert "상황·심의" in MATCHUP
    assert "재료일 뿐 결론이 아니다" in MATCHUP
    assert "불명" in MATCHUP


@pytest.mark.asyncio
async def test_no_redis_means_no_call():
    """캡 없는 AI 호출을 만들지 않는다."""
    assert await council._cap_ok(None, "2026-09-06") is False
    assert await council._once_ok(None, "kbo", 1, "2026-09-06") is False


@pytest.mark.asyncio
async def test_run_skips_when_no_situation_tags():
    assert await council.run(_jg(0), "2026-09-06", None) is None


def test_council_runs_before_judgement_not_after():
    """🔴 계약 — 심의 호출이 프롬프트 렌더 **앞**에 있어야 한다.

    뒤에 있으면 재판정 구조가 되고, 그건 사용자가 명시적으로 거부한 설계다.
    """
    import inspect

    from app.engine.matchup import judge_matchup

    src = inspect.getsource(judge_matchup)
    assert "council" in src
    assert src.index("_council") < src.index("render_matchup_prompt"), (
        "심의가 판정 뒤에 있다 — 재판정 구조가 됐다")
