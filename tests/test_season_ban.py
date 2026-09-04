"""[C2 2026-09-04] 대원칙 계약 — 시즌 누적은 판정 입력이 아니다.

🔴 사용자 지시(2026-09-04): "판정에 들어가는 모든 데이터는 최근 3~5경기
   (불펜은 최근 3일)만. 시즌 누적·통산·상대전적 판정 입력 금지. 예외 없음."

   C1 이 자료9(불펜)를 최근 폼으로 교체했고, C2 가 자료7(선발 시즌 라인)·
   자료8(타선 시즌 타격)을 **폐지**한다. 이 테스트가 없으면 다음에 누군가
   "표본 보정용이니까 괜찮다"며 되살릴 때 알려줄 사람이 없다 — 실제로 자료7·8
   이 그 논리로 두 번 들어왔다(2026-09-01·09-02).

⚠️ 대체는 하지 않았다. 최근 5경기 타격은 MLB(statsapi lastXGames)만 되고
   KBO(기록실에 최근 N경기 스플릿 없음)·NPB(시즌표뿐)는 경로가 없다 —
   MLB 만 바꾸면 3리그 표본이 갈린다. 경로가 생기면 3리그 동시에 넣는다.
"""
from pathlib import Path

import pytest

from app.engine.prompts import MATCHUP


def test_matchup_prompt_has_no_season_placeholders():
    """폐지된 두 자료의 자리표시자가 프롬프트에 남아 있지 않다."""
    assert "{{STARTER_SEASON_JSON}}" not in MATCHUP
    assert "{{LINEUP_SEASON_JSON}}" not in MATCHUP


def test_matchup_prompt_states_the_ban():
    """빈 칸이 아니라 **폐지**임을 판정 모델에게 말한다.

    없는 자료를 상상해 채우지 못하게 하는 것이 목적이다.
    """
    assert "폐지됨 (2026-09-04)" in MATCHUP
    assert "시즌 누적·통산·상대전적은 판정 입력이 아니다" in MATCHUP


def test_matchup_prompt_keeps_thin_sample_rule_without_season():
    """표본이 얇을 때의 처방이 '시즌으로 메운다' 에서 '0.50 으로 당긴다' 로 남았다."""
    assert "2경기 이하" in MATCHUP
    assert "0.50 쪽으로 당겨라" in MATCHUP


def test_render_does_not_pass_season_payloads():
    """렌더 함수가 시즌 payload 를 만들지도, 넘기지도 않는다."""
    src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    assert "STARTER_SEASON_JSON" not in src
    assert "LINEUP_SEASON_JSON" not in src
    assert "lineup_season_payload" not in src
    assert "starters_season_payload" not in src


def test_pipeline_no_longer_attaches_season_lines():
    """재료를 안 쓰면서 크롤만 남는 상태를 만들지 않는다."""
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    assert "starter_season import attach" not in src
    assert "lineup_season import attach" not in src


def test_rendered_prompt_carries_no_season_numbers():
    """실제 렌더 결과에 시즌 라인 값이 섞여 들어가지 않는다.

    research 에 옛 키가 남아 있어도(캐시 잔여) 프롬프트로는 새지 않아야 한다.
    """
    from app.engine.matchup import render_matchup_prompt

    jg = {
        "sport": "kbo",
        "research": {
            # 옛 캐시가 그대로 남아 있는 상황을 흉내낸다.
            "home_starter_season": {"era": "2.85", "whip": "1.05", "이닝": 160},
            "away_starter_season": {"era": "5.40", "whip": "1.62", "이닝": 88},
            "home_lineup_season": {"타자": [{"이름": "가", "OPS": ".912"}],
                                   "팀": {"가중OPS": ".794"}},
            "away_lineup_season": {"타자": [{"이름": "나", "OPS": ".650"}],
                                   "팀": {"가중OPS": ".701"}},
        },
    }
    out = render_matchup_prompt(jg, boxes={}, news={}, prev=None)
    for leaked in ("2.85", "5.40", "1.62", ".912", ".794", "가중OPS"):
        assert leaked not in out, f"시즌 값 누출: {leaked}"
    assert "{{" not in out, "자리표시자 잔여"


@pytest.mark.parametrize("field", ["mat_total", "mat_injected", "regress"])
def test_m2_counter_moved_to_lineup_not_deleted(field):
    """자료8 이 사라졌다고 M-2 감시까지 사라지지 않았다."""
    from app.engine.monitor_metrics import summary  # noqa: F401
    import inspect

    from app.engine import monitor_metrics as mm

    src = inspect.getsource(mm)
    assert "mat_with8" not in src, "옛 필드명이 남아 있다"
    assert field in src
