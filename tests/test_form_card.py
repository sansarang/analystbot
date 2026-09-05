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


def test_npb_verified_uses_same_rec_gate():
    s = Settings(_env_file=None)
    assert s.npb_last3_verified is True
    jg = _jg(sport="npb", league="NPB")
    assert rec_label(jg, s) == "추천"
    assert "추천" in render_form_card(jg)
    s.npb_last3_verified = False
    assert rec_label(jg, s) == "NPB: 참고용"


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


# ── [2026-09-05] 카드 게이트와 파이프라인 게이트가 갈려 있었다 ──────────
# 실사고: 선발 표본 하한(2026-09-01 신설)은 `pipeline.qualifies()` 에만 있었고
# 카드를 만드는 `rec_label()` 에는 없었다. 사용자가 받는 카드는 느슨한 쪽이라
# NC 카드가 근거3에 "이재학 704일 만 복귀(표본 0)" 이라고 적어놓고
# `우세 NC 66.0% · 🟢 · 추천` 으로 나갔다. 같은 슬레이트 일일 요약은
# "선발 표본 부족 3경기 — 추천 자격 없음" 이라고 정확히 셌다.
def test_low_starter_sample_is_board_only_on_the_card():
    """표본 부족이면 확률이 아무리 높아도 카드는 보드만이다."""
    jg = _jg(p_claude=0.66, starter_low_sample=["away"])
    assert rec_label(jg) == "보드만"
    assert "추천" not in render_form_card(jg).splitlines()


def test_low_starter_sample_veto_beats_a_green_light():
    """신호등은 표시 전용 — 🟢 여도 추천이 되지 않는다."""
    jg = _jg(p_claude=0.66, starter_low_sample=["home"])
    assert traffic_light(0.66) == "🟢"
    assert rec_label(jg) == "보드만"


def test_normal_sample_still_recommends():
    """반대 위험 — 표본이 정상이면 종전대로 추천이 나간다."""
    assert rec_label(_jg(p_claude=0.66, starter_low_sample=[])) == "추천"
    assert rec_label(_jg(p_claude=0.66)) == "추천"


def test_card_gate_and_pipeline_gate_read_the_same_field():
    """두 게이트가 다시 갈리면 여기서 걸린다."""
    import inspect

    from app.engine import form_card
    from app import pipeline

    assert "starter_low_sample" in inspect.getsource(form_card.rec_label)
    assert "starter_low_sample" in inspect.getsource(pipeline.qualifies)
