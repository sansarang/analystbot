"""[v1.1 2단계] 재판정 델타 — "무엇이 바뀌어 어디로 움직였나".

재판정이 "처음부터 다시"가 되면, 판정이 왜 움직였는지 아무도 모른다.
(실측 사례: 안우진 등판 확인 → 두산 0.62→0.59 철회 / G1 완봉 → NYY 0.60→0.53)
"""

from pathlib import Path

import pytest

from app.engine.matchup import PREV_FIELDS, prev_verdict
from app.pipeline import delta_note


# ---------------------------------------------------------------- 직전 판정 입력

def test_first_judgement_has_no_previous():
    assert prev_verdict({}) is None
    assert prev_verdict({"matchup": {}}) is None
    assert prev_verdict({"matchup": {"우세": "home"}}) is None, \
        "p_home 없는 껍데기를 직전 판정으로 넘기면 안 된다"


def test_previous_verdict_carries_only_the_skeleton():
    """전체를 넘기면 프롬프트가 커지고 모델이 옛 서술을 베낀다 — 뼈대만."""
    jg = {"matchup": {"p_home": 0.62, "우세": "home", "근거": ["a", "b", "c"],
                      "변수": ["v"], "확신도": "중",
                      "직전대비": {"이동": "0"}, "model": "x", "raw": "…"}}
    prev = prev_verdict(jg)
    assert set(prev) <= set(PREV_FIELDS)
    assert "model" not in prev and "raw" not in prev and "직전대비" not in prev
    assert prev["p_home"] == 0.62


def test_prompt_has_previous_verdict_input_and_rule():
    from app.engine.prompts import MATCHUP

    assert "PREV_VERDICT_JSON" in MATCHUP
    assert "직전 판정이 있으면" in MATCHUP
    assert "바뀐 입력이 없으면 직전 판정을 유지한다" in MATCHUP
    assert '"직전대비"' in MATCHUP


def test_matchup_passes_previous_verdict():
    src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    assert "PREV_VERDICT_JSON=json.dumps(prev" in src


# ---------------------------------------------------------------- 카드 표기

def test_no_delta_no_note():
    """최초 판정이나 이동 0이면 아무것도 붙이지 않는다 — 빈말 금지."""
    assert delta_note({}) == ""
    assert delta_note({"matchup": {"직전대비": {"변경입력": [], "이동": "0"}}}) == ""


def test_delta_note_shows_change_and_move():
    note = delta_note({"matchup": {"직전대비": {
        "변경입력": ["홈 선발 안우진으로 변경", "타순 3번 교체"],
        "무효화된근거": ["원정 선발 우위"], "이동": "-3.0%p"}}})
    assert "변경 홈 선발 안우진으로 변경, 타순 3번 교체" in note
    assert "무효 원정 선발 우위" in note
    assert "이동 -3.0%p" in note


def test_delta_note_is_truncated():
    """카드가 길어지면 정작 확률·근거가 안 보인다 — 변경 2개·무효 1개까지."""
    note = delta_note({"matchup": {"직전대비": {
        "변경입력": ["A", "B", "C", "D"],
        "무효화된근거": ["X", "Y", "Z"], "이동": "+1.0%p"}}})
    assert "C" not in note and "D" not in note
    assert "Y" not in note and "Z" not in note


def test_delta_note_survives_malformed_model_output():
    """모델이 스키마를 어겨도 카드가 죽지 않는다."""
    assert delta_note({"matchup": {"직전대비": "문자열"}}) == ""
    assert delta_note({"matchup": {"직전대비": {"변경입력": "리스트아님"}}}) is not None


# ---------------------------------------------------------------- 축구 공통

def test_soccer_shares_the_same_delta_structure():
    """2단계는 종목 공통이다 — 축구 확정판도 같은 필드를 쓴다."""
    src = Path("app/engine/soccer_trial.py").read_text(encoding="utf-8")
    assert "직전 판정" in src and '"직전대비"' in src
    assert "prev_verdict" in src
    assert "PREV_KEY" in src, "재판정 입력을 보관하지 않으면 델타가 늘 비어 있다"
