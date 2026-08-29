"""파트 D 체크리스트 — 코드 레벨 확인. 라이브 슬레이트는 tools/compare_form_slate.py."""
from app.config import Settings
from app.engine.form_card import rec_label
from app.engine.matchup import clip_p_home
from app.engine.pregame_push import (
    NPB_FINISH_MIN,
    SEND_OPEN_MIN,
    analysis_open,
    in_send_window,
)
from app.pipeline import qualifies


def test_p_home_clip_bounds():
    s = Settings(_env_file=None)
    assert clip_p_home(0.90, s) == 0.68
    assert clip_p_home(0.10, s) == 0.32


def test_away_pick_needs_plus_five():
    s = Settings(_env_file=None)
    home = {"p": 0.58, "sport": "kbo", "pick_state": "final"}
    assert qualifies(home, s)
    away = {"p": 0.62, "sport": "kbo", "pick_state": "final",
            "required_prob": s.min_win_prob + s.away_prob_penalty}
    assert not qualifies(away, s)
    away["p"] = 0.63
    assert qualifies(away, s)


def test_npb_rec_label_stays_reference_while_unverified():
    s = Settings(_env_file=None)
    assert s.npb_last3_verified is False
    jg = {"sport": "npb", "p_claude": 0.64, "pick_state": "final",
          "matchup": {"p_home": 0.64, "우세": "home"}}
    assert rec_label(jg, s) == "NPB: 참고용"
    assert not qualifies({"p": 0.64, "sport": "npb", "pick_state": "final"}, s)


def test_send_windows_and_npb_cut():
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)  # KST 17:45
    npb = now + timedelta(minutes=15)  # 18:00
    kbo = now + timedelta(minutes=45)  # 18:30
    assert SEND_OPEN_MIN["kbo"] == 70
    assert SEND_OPEN_MIN["npb"] == 40
    assert SEND_OPEN_MIN["mlb"] == 180
    assert NPB_FINISH_MIN == 15
    assert analysis_open("npb", npb, now) is False
    assert in_send_window("npb", npb, now) is True
    assert analysis_open("kbo", kbo, now) is True
