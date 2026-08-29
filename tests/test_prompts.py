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
    )
    assert '"p_home": 0.00' in out2
    assert "{{HOME_FORM_JSON}}" not in out2
