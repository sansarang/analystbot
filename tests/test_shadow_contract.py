"""[감시 3층] 계약 — **감시는 판정·카드를 한 바이트도 바꾸지 않는다.**

P1 이 이 파일의 전부다. 감시층이 활성이든 비활성이든 사용자가 받는 카드는
같아야 한다. 다르면 그건 감시가 아니라 입력이다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SPORT_CARD_JG = {
    "sport": "kbo", "game_id": 1, "home": "두산 베어스", "away": "LG 트윈스",
    "starts_at_kst": "09/03 18:30", "lineup_status": "confirmed",
    "p_claude": 0.57, "judge_confidence": "medium",
    "matchup": {"p_home": 0.57, "우세": "away", "확신도": "중",
                "근거": ["자료4: 홈 선발 최근 5경기 평균 4.6이닝·평균 3.2실점",
                        "자료8: 타선 시즌 가중OPS 원정 0.794 vs 홈 0.77",
                        "자료9: 불펜 ERA 홈 3.64 vs 원정 4.88"],
                "변수": ["표본 한계"]},
    "pick_summary": {"side": "LG 트윈스", "desc": "LG", "odds": None,
                     "p_final": 0.57},
    "research": {}, "best_odds": {},
}


def _card(monkeypatch, *, audit_on: bool) -> str:
    from app.config import Settings
    from app.engine.form_card import render_form_card

    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(_env_file=None, fact_audit_enabled=audit_on))
    return render_form_card(dict(SPORT_CARD_JG), "kbo")


def test_card_is_byte_identical_with_audit_on_and_off(monkeypatch):
    """🔴 **핵심 계약.** 감시 활성/비활성에서 카드 텍스트가 같아야 한다."""
    on = _card(monkeypatch, audit_on=True)
    off = _card(monkeypatch, audit_on=False)
    assert on.encode("utf-8") == off.encode("utf-8"), (
        "감시가 카드를 바꿨다 — 그건 감시가 아니라 입력이다")


def test_audit_result_never_reaches_the_card():
    """감시 결과 표기는 v1.4 승격 때다 — 지금 카드에 들어가면 안 된다."""
    for path in ("app/engine/form_card.py", "app/engine/pregame_push.py",
                 "app/engine/value_gate.py"):
        src = Path(path).read_text(encoding="utf-8")
        for banned in ("fact_audit", "shadow_panel", "judge_review",
                       "judgement_audit", "mismatch"):
            assert banned not in src, f"{path} 가 감시 결과를 읽는다: {banned}"


def test_judgement_path_does_not_import_monitors():
    """P1 — 판정 경로가 감시 모듈을 import 하면 되먹임이 생긴다."""
    for path in ("app/engine/matchup.py", "app/engine/prompts.py",
                 "app/engine/team_form.py"):
        src = Path(path).read_text(encoding="utf-8")
        assert "shadow_panel" not in src, path
    # matchup 은 프롬프트 **보관**만 한다 — 감사 로직을 부르지 않는다
    m = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    assert "PROMPT_KEY" in m and "fact_audit.run" not in m
    assert "from app.engine.fact_audit import run" not in m


def test_audit_runs_only_after_the_verdict_is_saved():
    """훅은 저장 **뒤**에만 있다. 앞이면 판정을 지연시킨다."""
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    seg = src[src.index("async def rejudge_after_lineup"):]
    seg = seg[:seg.index("def _spawn_fact_audit")] if "def _spawn_fact_audit" in seg \
        else seg[:seg.index("async def ensure_game_fresh")]
    save = seg.index("_save_caches(redis, analysis, card)")
    hook = seg.index("_spawn_fact_audit(jg)")
    assert save < hook, "감사가 캐시 저장보다 먼저 돈다"


def test_audit_is_spawned_not_awaited():
    """`await` 하면 판정·발송이 감사만큼 늦어진다 — 태스크로 띄운다."""
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    assert "create_task(_go())" in src
    assert "await _spawn_fact_audit" not in src


def test_design_freeze_tests_still_pass():
    """기존 동결 계약이 살아 있는지 — 감시 작업이 그걸 건드리지 않았다."""
    from app.engine.matchup import clip_p_home
    from app.engine.prompts import MATCHUP

    assert "p_home은 0.32~0.68 범위를 벗어나지 않는다" in MATCHUP
    # [C2 2026-09-04] 자료8 폐지 — 나머지 동결 계약은 그대로다.
    assert "{{BOXSCORE_JSON}}" in MATCHUP
    assert "{{LINEUP_SEASON_JSON}}" not in MATCHUP
    assert clip_p_home(0.99) == pytest.approx(0.68)


def test_monitor_alerts_are_registered():
    """감시 경보도 기존 코드 목록에 있어야 사람이 읽을 수 있다."""
    from app.alerts import WATCHDOG_CODES

    for code in ("W-FACT-MISMATCH", "W-PANEL-DIVERGE", "W-MONITOR-DOWN"):
        assert code in WATCHDOG_CODES


def test_shadow_panel_covers_all_three_leagues():
    """🔴 감시가 리그마다 달라지면 안 된다.

    실측 2026-09-03: `_run_shadow_panel` 호출부가 **아시아 사이클에만**
    있었다. MLB 판정은 발송까지 정상이었는데 L2·L3 를 한 번도 받지 못했다
    — "어느 것은 되고 어느 것은 안 되는" 상태였고, 로그만 봐서는 그냥
    조용했다. 대칭을 테스트로 잠근다.
    """
    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    calls = src.count("await _run_shadow_panel(")
    assert calls >= 2, f"그림자 패널 호출부가 {calls}곳뿐 — MLB 누락 의심"
    assert 'await _run_shadow_panel(redis, ("mlb",), date)' in src, \
        "MLB 폴러에 그림자 패널이 없다"
