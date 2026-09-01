"""5단계 — 폼·매치업 프롬프트. 지시문 문구를 바꾸지 않았는지 지킨다."""
from app.engine.prompts import MATCHUP, TEAM_FORM, fill


def test_team_form_prompt_keeps_tag_dictionary_and_opponent_rank():
    assert "감독교체, 트레이드/이적, 주축부상, 주축복귀, 내부불화, 순위경쟁절박, 연패분위기, 더비/라이벌전" in TEAM_FORM
    assert "상대팀의 현재 순위·승률" in TEAM_FORM
    assert "시즌 전체 통념" in TEAM_FORM
    assert "{{TEAM_NAME}}" in TEAM_FORM
    assert "{{GAMES_JSON}}" in TEAM_FORM
    assert "{{NEWS_HEADLINES}}" in TEAM_FORM


def test_matchup_prompt_keeps_clip_and_news_cap():
    assert "p_home은 0.32~0.68 범위를 벗어나지 않는다" in MATCHUP
    assert "확률을 최대 ±3%p까지만 조정" in MATCHUP
    assert "실적 데이터가 가리키는 우세 방향을 뉴스만으로 뒤집을 수 없다" in MATCHUP
    assert "오늘 나온 9명이 기준이다" in MATCHUP
    assert "{{HOME_FORM_JSON}}" in MATCHUP
    assert "{{STARTERS_RECENT_JSON}}" in MATCHUP


def test_fill_replaces_placeholders_not_json_braces():
    """출력 JSON 예시의 중괄호를 format 필드로 오인하면 KeyError가 난다."""
    out = fill(TEAM_FORM, TEAM_NAME="한화", GAMES_JSON="[]", NEWS_HEADLINES="[]")
    assert "{{TEAM_NAME}}" not in out
    assert '"team": "한화"' in out
    assert '"타선": {"평가": "상|중|하"' in out
    out2 = fill(
        MATCHUP,
        HOME_FORM_JSON="{}",
        AWAY_FORM_JSON="{}",
        LINEUPS_JSON="{}",
        STARTERS_RECENT_JSON="{}",
        LINEUP_INTENT_JSON="{}",
    )
    assert '"p_home": 0.00' in out2
    assert "{{HOME_FORM_JSON}}" not in out2


def test_matchup_receives_lineup_intent_as_interpretation():
    """🔴 실측 2026-09-01: 라인업 의도가 카드에만 실리고 매치업 프롬프트에는
    없었다. 수집한 정보가 확률을 움직이지 않는 상태였다 — 파드리스전에서
    핵심 4명 이탈을 서술에 써놓고 승률은 그대로였던 것과 같은 모양이다.

    ⚠️ 넣되 **해석으로** 넣는다. lineup_intent 모듈 자신의 규율이
       "사실과 해석을 끝까지 분리한다 — 섞으면 3단이 추측을 사실로 읽는다"다.
    """
    assert "{{LINEUP_INTENT_JSON}}" in MATCHUP
    assert "사실이 아니라 해석이다" in MATCHUP
    assert '"해석:"으로 시작해 사실과 구분하라' in MATCHUP


def test_intent_is_capped_together_with_news_and_cannot_flip():
    """의도는 보조 신호다. 뉴스와 **합쳐서** ±3%p, 우세 방향 뒤집기 금지.

    새 임계값을 만들지 않았다 — 기존 뉴스 상한을 공유하도록 좁혔을 뿐이다.
    """
    assert "뉴스와 의도를 **합쳐서** ±3%p를" in MATCHUP
    assert "이 둘만으로 뒤집을 수 없다" in MATCHUP
    # 기존 뉴스 규칙은 그대로 살아 있다 (회귀)
    assert "확률을 최대 ±3%p까지만 조정" in MATCHUP


def test_intent_boryu_is_not_evidence():
    """'보류'는 "판단 못 함"이지 "중립"이 아니다 — 근거로 쓰면 안 된다."""
    assert "'보류'인 항목은 **근거로 쓰지 마라.**" in MATCHUP


def test_fill_replaces_intent_slot():
    out = fill(
        MATCHUP,
        HOME_FORM_JSON="{}", AWAY_FORM_JSON="{}", LINEUPS_JSON="{}",
        STARTERS_RECENT_JSON="{}", PREV_VERDICT_JSON="null",
        LINEUP_INTENT_JSON='{"home": {"요약": "주전 2명 휴식"}}',
    )
    assert "{{LINEUP_INTENT_JSON}}" not in out
    assert "주전 2명 휴식" in out


def test_interpreter_role_is_actually_usable():
    """🔴 기본값이 서로 모순이었다: interpreter_provider="groq" 인데 groq 은
    disabled_providers 기본값에 들어 있다. 그래서 의도 해석이 한 번도 돌지
    않았고, role_enabled 는 True 를 돌려줘 그 사실이 드러나지도 않았다.
    """
    from app.config import Settings
    from app.llm.provider import resolve_model, role_enabled

    s = Settings(_env_file=None)
    assert role_enabled("interpreter", s) is True
    assert s.is_disabled(s.interpreter_provider) is False, \
        "해석봇 프로바이더가 비활성 목록에 있다 — 영원히 안 돈다"


def test_interpreter_model_is_pinned_not_opus_fallback():
    """⚠️ 비우면 역할 폴백이 judge_model(=Opus)을 넣는다. 해석봇은 경기×양팀이라
    호출량이 가장 많은 역할이다 — 슬레이트당 20콜이 조용히 Opus가 된다."""
    from app.config import Settings
    from app.llm.provider import resolve_model

    s = Settings(_env_file=None)
    assert s.interpreter_model, "비어 있으면 Opus 폴백이다"
    assert resolve_model("interpreter", s) == s.interpreter_model
    assert resolve_model("interpreter", s) != s.judge_model
