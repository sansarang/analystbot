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


def test_npb_rec_label_follows_gate_when_verified():
    s = Settings(_env_file=None)
    assert s.npb_last3_verified is True
    jg = {"sport": "npb", "p_claude": 0.64, "pick_state": "final",
          "matchup": {"p_home": 0.64, "우세": "home"}}
    assert rec_label(jg, s) == "추천"
    assert qualifies({"p": 0.64, "sport": "npb", "pick_state": "final"}, s)
    s.npb_last3_verified = False
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


def test_compare_merge_flags_favored_flip():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tools" / "compare_form_slate.py"
    spec = importlib.util.spec_from_file_location("compare_form_slate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    new = [{
        "game_id": "g1", "status": "scheduled",
        "away": "A", "home": "H", "sport": "kbo", "pick_state": "final",
        "matchup": {"p_home": 0.40, "우세": "away", "근거": ["원정 3경기 흐름"]},
        "p_claude": 0.40,
    }]
    old = [{
        "game_id": "g1", "old_p_home": 0.61, "old_favored": "home",
        "old_rec_label": "추천", "old_qualifies": True,
        "old_verdict": "홈 ERA 우위", "old_근거": ["홈 ERA 우위"],
    }]
    rows = mod.merge_rows(new, old)
    assert rows[0]["favored_flip"] is True
    assert rows[0]["new_favored"] == "away"
    assert rows[0]["old_favored"] == "home"
    assert rows[0]["new_근거"] == ["원정 3경기 흐름"]
    assert "홈 ERA" in str(rows[0]["old_근거"])


def test_compare_loads_frozen_kbo_baseline_without_old_flag():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tools" / "compare_form_slate.py"
    spec = importlib.util.spec_from_file_location("compare_form_slate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    rows = mod.load_frozen_old_kbo("2026-08-29")
    assert len(rows) == 5
    by = {r["game_id"]: r for r in rows}
    assert by[1445]["old_p_home"] == 0.6
    assert by[1447]["old_favored"] == "away"
    assert by[1449]["old_p_home"] == 0.35
    assert mod.load_frozen_old_kbo("2026-08-28") == []
    new = [{
        "game_id": 1445, "status": "scheduled",
        "away": "Kiwoom Heroes", "home": "Doosan Bears", "sport": "kbo",
        "matchup": {"p_home": 0.55, "우세": "home"},
        "p_claude": 0.55,
    }]
    merged = mod.merge_rows(new, rows)
    assert merged[0]["old_p_home"] == 0.6
    assert merged[0]["favored_flip"] is False


def test_pipeline_npb_refresh_passes_standings():
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index("await refresh_npb_form")
    block = src[i:i + 180]
    assert "standings=npb_standings" in block
    assert "lacks_opponent_context" in src
    assert "_parse_npb_standings" in src
