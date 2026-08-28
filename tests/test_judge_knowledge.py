"""판정은 입력에 없는 경기 결과를 기억으로 쓰지 않는다."""


def test_live_judge_system_forbids_recalling_results():
    """라이브도 같은 SYSTEM을 쓴다. 여기 없으면 문서만 있고 판정은 그대로다."""
    from app.engine.judge import SYSTEM

    assert "[지식 누수" in SYSTEM
    assert "아직 시작하지 않은 것" in SYSTEM
    assert "최종 점수" in SYSTEM
    assert "기억을 여는 열쇠" in SYSTEM
    assert "lineup_record" in SYSTEM
    assert "pitcher_matchup" in SYSTEM
    assert "시즌 상대팀" in SYSTEM
