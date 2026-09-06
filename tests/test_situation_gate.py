"""[소식통 2026-09-06] 상황이 승률을 뒷받침하는가 — 확신도 강등.

🔴 설계 전환: 상황 정보에 **%p 를 매기지 않는다.** 은퇴식이 몇 %p 인지
   우리는 모르고, 모르는 것에 숫자를 붙이면 지어낸 계수다.
   대신 이미 나온 승률을 **검증**한다 — 지지/불일치/무관.

🔴 소식통이 관건이다. 익명 계정의 카더라로 픽을 죽일 수 없다.
"""
from __future__ import annotations

import pytest

from app.engine import situation_gate as sg


def _jg(concl="무관", conf="medium", *, official=True, tags=True, 사유="원정 주축 2명 IL"):
    st = {}
    if tags:
        st = {"home": [{"확인": "공식" if official else "미확인",
                        "유형": "roster_move", "제목": "roster moves"}]}
    return {"game_id": 1, "judge_confidence": conf, "situation_tags": st,
            "matchup": {"상황판정": {"결론": concl, "사유": 사유,
                                     "출처": "@Athletics"}}}


def test_supports_does_not_touch_confidence():
    jg = _jg("지지")
    res = sg.apply(jg)
    assert jg["judge_confidence"] == "medium"
    assert res["강등"] is False
    assert "뒷받침" in sg.card_line(res)


def test_contradiction_with_official_source_demotes():
    """🔴 숫자와 현지 상황이 어긋나면 확신도를 내린다."""
    jg = _jg("불일치", "medium", official=True)
    res = sg.apply(jg)
    assert jg["judge_confidence"] == "low"
    assert res["강등"] is True
    assert jg["situation_demoted"] is True
    line = sg.card_line(res)
    assert "뒷받침하지 않음" in line and "medium→low" in line


def test_contradiction_without_official_source_does_not_demote():
    """🔴 익명 계정의 카더라로 픽을 죽일 수 없다 — 소식통이 관건이다."""
    jg = _jg("불일치", "medium", official=False)
    res = sg.apply(jg)
    assert jg["judge_confidence"] == "medium", "미확인만으로 강등했다"
    assert res["강등"] is False
    assert "미확인" in sg.card_line(res)


def test_no_situation_tags_is_neutral():
    jg = _jg("불일치", "medium", tags=False)
    sg.apply(jg)
    assert jg["judge_confidence"] == "medium"


def test_low_confidence_is_not_demoted_further():
    jg = _jg("불일치", "low", official=True)
    res = sg.apply(jg)
    assert jg["judge_confidence"] == "low"
    assert res["강등"] is False


def test_missing_verdict_field_reads_as_neutral():
    """판정이 칸을 안 채웠다고 지어내지 않는다."""
    jg = {"game_id": 1, "judge_confidence": "medium", "matchup": {}}
    res = sg.apply(jg)
    assert res["결론"] == sg.NEUTRAL
    assert jg["judge_confidence"] == "medium"
    assert sg.card_line(res) == ""


def test_probability_is_never_touched():
    """🔴 상황은 확률의 입력이 아니다 — 검증이다."""
    jg = _jg("불일치", "medium", official=True)
    jg["p_claude"] = 0.54
    sg.apply(jg)
    assert jg["p_claude"] == 0.54


def test_prompt_no_longer_quantifies_situation():
    """옛 ±1.0%p 규칙이 남아 있으면 모델이 또 숫자를 붙인다."""
    from app.engine.prompts import MATCHUP

    assert "±1.0%p" not in MATCHUP
    assert "%p 반영은 0" in MATCHUP
    assert "상황판정" in MATCHUP
    for word in ("지지", "불일치", "무관"):
        assert word in MATCHUP


@pytest.mark.parametrize("account,official", [
    ("@Athletics", True),          # 구단 공식 — 팀명에서 유도
    ("@Mariners", True),
    ("@SponichiYakyu", True),      # 언론
    ("@PacificleagueTV", True),    # 리그 공식
    ("@fa_jue44567", False),       # 익명
    ("@BrettsTailgate", False),
])
def test_x_account_decides_source_weight(account, official):
    """🔴 도메인으로 보면 구단 공식도 익명도 똑같이 x.com 이다."""
    from app.engine.situation import classify

    tags = classify([{"title": "Athletics roster moves announced",
                      "url": "https://x.com/a/1", "account": account}],
                    "mlb", teams=("Athletics", "Seattle Mariners"))
    assert tags, account
    assert (tags[0]["확인"] == "공식") is official, (account, tags[0])


def test_card_renders_situation_line():
    from app.engine.form_card import render_form_card

    jg = {"sport": "kbo", "league": "KBO", "home": "LG Twins",
          "away": "NC Dinos", "starts_at_kst": "09/06 18:30",
          "p_claude": 0.61, "judge_confidence": "medium",
          "pick_state": "final", "lineup_status": "confirmed",
          "matchup": {"p_home": 0.61, "우세": "home", "확신도": "중",
                      "근거": ["a"], "변수": [], "뉴스반영": {"적용": False}},
          "research": {},
          "situation_check": {"결론": "불일치", "사유": "홈 주축 IL 등재",
                              "강등": True, "이전": "medium", "이후": "low"}}
    out = render_form_card(jg)
    assert "뒷받침하지 않음" in out
