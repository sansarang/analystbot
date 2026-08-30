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


def test_slate_teams_counts_teams_not_games():
    """분모 규칙: 폼 대상은 경기 수가 아니라 **팀 수**다."""
    from app.pipeline import _slate_teams

    games = [{"home": "A", "away": "B"}, {"home": "C", "away": "D"},
             {"home": "E", "away": "F"}]
    assert _slate_teams(games) == 6          # 경기 3 → 팀 6
    # 더블헤더: 같은 팀이 두 경기에 나와도 폼은 한 번만 받는다
    assert _slate_teams(games + [{"home": "A", "away": "B"}]) == 6
    assert _slate_teams([]) == 0
    assert _slate_teams([{"home": "A", "away": None}]) == 1


async def test_form_quota_path_reports_team_denominator(monkeypatch):
    """🔴 크레딧 소진 알림의 분모가 경기 수면 실패 규모가 절반으로 보인다.

    실측 2026-08-29 14:16 KST에 실제로 이 경로가 탔다. 그때 "5팀 중 0팀"으로
    나갔지만 대상은 10팀이었다. 재발을 막는다.
    """
    from app.collectors.base import ApiQuotaError
    from app.engine import team_form
    from app.pipeline import _run_baseball_forms

    async def boom(*a, **kw):
        raise ApiQuotaError("anthropic(form)", "credit balance is too low")

    monkeypatch.setattr(team_form, "analyze_games", boom)

    calls = []

    async def record(name, ok, total, **kw):
        calls.append({"name": name, "ok": ok, "total": total, **kw})

    games = [{"home": f"H{i}", "away": f"A{i}"} for i in range(5)]   # 5경기 = 10팀
    try:
        await _run_baseball_forms(None, "kbo", "2026-08-30", games, record)
    except ApiQuotaError:
        pass
    else:
        raise AssertionError("크레딧 소진이 삼켜졌다 — 슬레이트가 계속 돈다")

    # _run_baseball_forms 는 기록하지 않고 그대로 올린다. 기록은 호출부의 몫이다.
    assert calls == [], f"예외 경로에서 이중 기록: {calls}"

    # 호출부(build_analysis)의 분모가 팀 수인지 — 경기 수(len(upcoming))면 절반이다.
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("팀 폼", 0,')
    assert "_slate_teams(upcoming)" in src[i:i + 120], \
        "크레딧 소진 경로의 팀 폼 분모가 팀 수가 아니다"


def test_compare_tool_drops_started_games():
    """검증 도구가 실운영과 다른 규칙으로 돌면 결과가 오염된다.

    실측 2026-08-30: DB status 가 아직 'scheduled' 인 진행 중 경기(1회초)가
    드라이런에서 '추천' 라벨을 받았다. 실운영 발송은 still_upcoming 으로
    막는다(pregame_push:87, :259) — 도구도 같은 문을 통과해야 한다.
    """
    from tools.compare_form_slate import live_games, merge_rows

    games = [
        {"game_id": 1, "status": "scheduled", "home": "H", "away": "A",
         "starts_at": "2099-01-01T00:00:00+00:00"},        # 예정
        {"game_id": 2, "status": "scheduled", "home": "H", "away": "A",
         "starts_at": "2020-01-01T00:00:00+00:00"},        # 진행 중 (status 미갱신)
        {"game_id": 3, "status": "final", "home": "H", "away": "A",
         "starts_at": "2099-01-01T00:00:00+00:00"},        # 종료
    ]
    assert [g["game_id"] for g in live_games({"games": games})] == [1]
    assert [r["game_id"] for r in merge_rows(games, [])] == [1]
