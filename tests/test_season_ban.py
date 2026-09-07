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
import json
from pathlib import Path

import pytest

from app.engine.prompts import MATCHUP


def test_matchup_prompt_has_no_season_placeholders():
    """폐지된 두 자료의 자리표시자가 프롬프트에 남아 있지 않다."""
    assert "{{STARTER_SEASON_JSON}}" not in MATCHUP
    assert "{{LINEUP_SEASON_JSON}}" not in MATCHUP


# ── [v1.4 2026-09-07] 자료12 예외 — 삭제가 아니라 **갱신**이다 ───────────
#   대원칙 개정: "시즌 누적 통계(집계표)는 금지 — 유지. 단, 경기 단위로
#   갱신되는 실력 레이팅(ELO, 최근 가중)은 누적 통계가 아니라 '오늘 시점
#   실력 상태값'이므로 자료12로 허용한다." (사용자 결정, 620행 분석 근거)
#   아래 기존 집계표 차단 단언은 **하나도 빼지 않았다.**

def test_material12_elo_is_allowed():
    """자료12 는 프롬프트에 실린다 — 이것이 개정된 계약이다."""
    from app.engine.prompts import MATCHUP

    assert "{{ELO_JSON}}" in MATCHUP
    assert "실력 레이팅" in MATCHUP
    assert "기본 축" in MATCHUP and "조정 축" in MATCHUP


def test_material12_is_a_state_value_not_a_table():
    """팀당 **숫자 하나**여야 한다. 집계표를 얹으면 대원칙 위반이다."""
    from app.engine.matchup import elo_payload

    jg = {"elo": {"home": {"레이팅": 1530.0, "리그평균대비": 30.0, "경기수": 41},
                  "away": {"레이팅": 1470.0, "리그평균대비": -30.0, "경기수": 38}}}
    out = elo_payload(jg)
    assert out["격차"] == 60.0
    assert set(out["홈"]) == {"레이팅", "리그평균대비", "경기수"}
    blob = json.dumps(out, ensure_ascii=False)
    for banned in ("타율", "ERA", "승패", "스플릿", "통산", "상대전적", "OPS", "WHIP"):
        assert banned not in blob, f"집계표가 자료12 에 섞였다: {banned}"


def test_material12_needs_both_teams():
    """한 팀만 있으면 격차를 못 낸다 — 반쪽을 실력차로 읽게 하지 않는다."""
    from app.engine.matchup import elo_payload

    assert elo_payload({"elo": {"home": {"레이팅": 1530}, "away": None}}) == {}
    assert elo_payload({}) == {}


def test_ban_now_targets_tables_not_all_season_data():
    """금지선이 '시즌 데이터 전부'에서 '집계표'로 좁아졌다."""
    from app.engine.prompts import MATCHUP

    assert "시즌 **집계표**" in MATCHUP
    assert "자료12 실력 레이팅은 예외다" in MATCHUP
    # 종전 문구는 사라져야 한다 — 두 규칙이 공존하면 판정이 헷갈린다.
    assert "배당, 팀 명성, 시즌 승률, 사전 지식은 쓰지 않는다" not in MATCHUP


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
