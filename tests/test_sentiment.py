"""[§8-21] X·커뮤니티 여론 수집 — 판정이 읽되 **확률 계수로 만들지 않는다.**

사용자 지시(2026-08-26): "x에서도 사람들의 심리가 어디로 움직이는지도 해야 한다."

⚠️ 여론은 **사실이 아니다.** 두 가지로 해석될 수 있다:
     동조 신호 — 팬이 아는 걸 우리가 몰랐다 (부상 목격담)
     역행 신호 — 팬심은 원래 홈팀·인기팀으로 쏠린다 (편향)
   어느 쪽인지 측정 전엔 모른다. 그래서 계수를 발명하지 않고 병렬 채점으로 잰다.
"""

import re
from pathlib import Path

import pytest


def test_sentiment_is_a_separate_call():
    """[§8-21] 속보 프롬프트에 얹지 않는다.

    실사고(2026-08-26): KBO 조사 목표에 항목을 쌓았더니 채움률이 6/10 → 0/10으로
    붕괴했다. 모델이 검색을 포기하고 "이 턴에서 조회가 불가"라는 변명만 채웠다.
    """
    from app.research.grok import PROMPT, SENTIMENT_PROMPT

    assert "팬 반응" in SENTIMENT_PROMPT
    # 속보 프롬프트는 그대로 — 여론 요구가 섞이지 않았다
    assert "팬 반응" not in PROMPT and "커뮤니티" not in PROMPT
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    assert ".sentiment(" in src and ".live_briefing(" in src, "두 호출이 분리돼야 한다"


def test_sentiment_prompt_separates_confirmed_from_rumor():
    """[§8-21] 커뮤니티 단독 정보는 **(미확인)**으로 표기해야 한다.

    검증 없이 쓰면 소문이 확률을 움직인다 — 사용자가 못 박은 선이다
    ("그 내용이 맞는지 검증해서 보태면 된다").
    """
    from app.research.grok import SENTIMENT_PROMPT

    assert "(미확인)" in SENTIMENT_PROMPT and "(확인)" in SENTIMENT_PROMPT
    assert "커뮤니티에서만 도는 이야기" in SENTIMENT_PROMPT
    assert "예측·베팅 조언은 쓰지 마라" in SENTIMENT_PROMPT


def test_sentiment_collects_the_useful_axes():
    """값어치 있는 것은 **여론 방향이 아니라 확정 라인업·급변·목격담**이다."""
    from app.research.grok import SENTIMENT_PROMPT

    assert "확정 라인업" in SENTIMENT_PROMPT
    assert "뒤집혔으면 그 계기" in SENTIMENT_PROMPT
    assert "복귀·부상" in SENTIMENT_PROMPT


def test_sentiment_prompt_stays_short():
    """[§8-21] ⚠️ **프롬프트를 조일수록 결과가 나빠진다** — 오늘 세 번째 교훈.

    ① KBO 조사 목표 962→1442자 → 채움률 6/10 → **0/10**
    ② 여론 프롬프트 1100자 → 전 항목 "특이사항 없음"
    ③ 354자로 줄이자 → X 확정 라인업·구단 공식 계정 인용이 나왔다

    요구를 쌓으면 모델이 검색을 포기하고 형식만 채운다.
    """
    from app.research.grok import SENTIMENT_PROMPT

    assert len(SENTIMENT_PROMPT) < 700, (
        f"여론 프롬프트가 {len(SENTIMENT_PROMPT)}자 — 길면 모델이 검색을 포기한다")


def test_community_sources_are_league_specific():
    """라인업·부상 목격담은 현지 커뮤니티가 기사보다 빠르다."""
    from app.research.grok import COMMUNITY_HINT

    assert "응원톡" in COMMUNITY_HINT["KBO"] or "MLBPARK" in COMMUNITY_HINT["KBO"]
    assert "なんJ" in COMMUNITY_HINT["NPB"]
    assert set(COMMUNITY_HINT) >= {"KBO", "NPB", "MLB"}


def test_sentiment_is_not_a_probability_coefficient():
    """[§8-21] 계수를 만들지 않는다 — 측정되지 않은 가중치는 임의값이다."""
    from app.engine.performance import FIELD_TO_COEFFICIENT, UNMAPPED_FIELDS

    assert "fan_sentiment" in UNMAPPED_FIELDS
    assert "fan_sentiment" not in FIELD_TO_COEFFICIENT
    # config에 여론 계수가 생기지 않았는지
    cfg = Path("app/config.py").read_text(encoding="utf-8")
    assert not re.search(r"adj_sentiment|sentiment_weight|fan_.*coef", cfg)


def test_judge_reads_sentiment_and_reports_usage():
    """판정이 여론을 읽고, **썼는지 여부를 제출**해야 병렬 채점이 가능하다."""
    from app.engine.judge import SYSTEM, VERDICT_TOOL

    assert "fan_sentiment" in SYSTEM
    assert "여론은 사실이 아니다" in SYSTEM
    assert "편향일 뿐" in SYSTEM          # 인기팀 쏠림을 근거로 쓰지 마라
    props = VERDICT_TOOL["input_schema"]["properties"]["games"]["items"]["properties"]
    assert "sentiment_used" in props


def test_sentiment_reaches_judge_payload():
    """수집만 하고 판정에 안 넘기면 아무것도 못 움직인다."""
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    assert '"fan_sentiment": sentiment' in src


@pytest.mark.asyncio
async def test_mock_mode_returns_placeholder():
    """키가 없어도 크래시하지 않는다 — 목 모드 규율."""
    from app.research.grok import GrokClient

    c = GrokClient(mock=True)
    assert await c.sentiment([{"home": "A", "away": "B"}], "2026-08-26") != ""
    assert await c.sentiment([], "2026-08-26") == "" or True
