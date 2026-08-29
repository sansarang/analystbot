"""야구 카드는 매치업 JSON만. 언더오버·런라인·F5 없음."""
from app.config import Settings
from app.engine.form_card import rec_label, render_form_card, traffic_light
from app.engine.pregame_push import compose_card


def _jg(**kw):
    m = {
        "p_home": 0.61,
        "우세": "home",
        "근거": ["홈 3경기 흐름", "원정 선발 최근 등판", "오늘 타순"],
        "변수": ["불펜 연투"],
        "뉴스반영": {"적용": False, "조정폭": "0", "사유": ""},
        "확신도": "중",
    }
    jg = {
        "sport": "kbo", "league": "KBO", "home": "LG Twins", "away": "NC Dinos",
        "starts_at_kst": "08/28 18:30", "stadium": "잠실",
        "p_claude": 0.61, "judge_confidence": "medium",
        "pick_state": "final", "lineup_status": "confirmed",
        "matchup": m,
        "research": {},
    }
    jg.update(kw)
    if "matchup" in kw:
        jg["matchup"] = kw["matchup"]
    return jg


def test_card_maps_matchup_fields_only():
    text = render_form_card(_jg())
    assert "KBO" in text and "잠실" in text
    assert "우세" in text and "61.0%" in text
    assert "근거1" in text and "근거3" in text
    assert "변수 불펜 연투" in text
    assert "언더" not in text and "오버" not in text
    assert "런라인" not in text and "5이닝" not in text
    assert "보드만" in text or "추천" in text


def test_board_only_still_has_reasons():
    jg = _jg(pick_state="preview", lineup_status="predicted")
    text = render_form_card(jg)
    assert "근거1" in text
    assert rec_label(jg) == "보드만"
    assert "보드만" in text


def test_npb_unverified_is_reference_only():
    s = Settings(_env_file=None)
    assert s.npb_last3_verified is False
    jg = _jg(sport="npb", league="NPB")
    assert rec_label(jg, s) == "NPB: 참고용"
    assert "NPB: 참고용" in render_form_card(jg)


def test_news_line_only_when_applied():
    jg = _jg()
    assert "뉴스반영" not in render_form_card(jg)
    jg["matchup"]["뉴스반영"] = {"적용": True, "조정폭": "+1.5%p", "사유": "주축복귀"}
    text = render_form_card(jg)
    assert "뉴스반영 +1.5%p 주축복귀" in text


def test_revision_tag_and_green_light():
    jg = _jg()
    jg["matchup"]["p_home"] = 0.64
    jg["p_claude"] = 0.64
    text = compose_card(jg, "", "kbo", revision=True)
    assert "라인업 변경 재판정" in text
    assert "🟢" in text
    assert traffic_light(0.64) == "🟢"
    assert traffic_light(0.60) == "🟡"
