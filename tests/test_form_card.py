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


# ── [2026-09-06] 카드가 결론을 말해야 한다 ──────────────────────────
# 🔴 실사고: 카드가 확률·근거·변수만 늘어놓고 마지막 줄이 `보드만` 이라
#    사용자가 "결론을 못 내고 있는 거냐"고 물었다. 판정 모델은 애초에
#    `결론` 을 요구받은 적이 없었다 — 출력 계약에 그 칸이 없었다.
#    판정의 답은 확률이 아니라 결론이고, 확률은 그 표현일 뿐이다.
def _with_conclusion(**kw):
    """⚠️ `p_claude` 만 바꾸면 안 된다 — 카드는 `matchup.p_home` 을 읽는다."""
    jg = _jg(**kw)
    if "p_claude" in kw:
        jg["matchup"]["p_home"] = kw["p_claude"]
    jg["matchup"]["결론"] = {
        "승자": "LG Twins",
        "판단": "선발 격차가 이 경기를 가른다. 다만 원정 타선이 뜨겁다."}
    return jg


def test_prompt_asks_the_model_to_conclude():
    """모델에게 결론을 요구하지 않으면 결론이 나올 리 없다."""
    from app.engine.prompts import MATCHUP

    assert '"결론"' in MATCHUP
    assert "승자" in MATCHUP and "판단" in MATCHUP
    assert "이것이 이 판정의 답이다" in MATCHUP
    assert "전부 한 상에 놓고" in MATCHUP


def test_card_leads_with_the_conclusion():
    out = render_form_card(_with_conclusion())
    assert "🎯 결론 — LG 트윈스 승" in out
    assert "선발 격차가 이 경기를 가른다" in out
    # 결론이 근거보다 먼저 나온다.
    assert out.index("🎯 결론") < out.index("근거1")


def test_board_only_says_why_it_is_board_only():
    """🔴 `보드만` 은 "승자를 모른다"가 아니라 "걸 자격이 없다"는 뜻이다.

    이유를 안 적으면 카드의 마지막 말이 결론처럼 읽힌다.
    """
    out = render_form_card(_with_conclusion(p_claude=0.54))
    assert "보드만 — 추천 하한" in out
    assert "54%" in out


def test_board_only_reason_names_confidence_veto():
    jg = _with_conclusion(p_claude=0.66, judge_confidence="low")
    assert "보드만 — 확신도 하" in render_form_card(jg)


def test_board_only_reason_names_low_starter_sample():
    jg = _with_conclusion(p_claude=0.66, starter_low_sample=["away"])
    assert "보드만 — 선발 표본 부족" in render_form_card(jg)


def test_recommended_card_is_unchanged():
    """반대 위험 — 추천일 때는 종전대로 '추천' 한 단어다."""
    out = render_form_card(_with_conclusion(p_claude=0.66))
    assert "\n추천" in out and "보드만" not in out


def test_missing_conclusion_does_not_break_the_card():
    """모델이 칸을 안 채워도 카드는 나가야 한다."""
    out = render_form_card(_jg())
    assert "우세" in out and "🎯 결론" not in out


# ═══════════════ [CARD-1 2026-09-08] 갈림길이 만들어지는데 카드엔 안 나갔다
#
# 🔴 사용자 보고: "분기점도 안 나오고, 변수를 DB에서 찾아 측정하는 것도 안 나온다."
#    조사 결과 **판정은 분기점을 내고 있었고, 자료14 도 답을 내고 있었다.**
#    운영 2026-09-08 KBO game=1721(stage=final) 실판정:
#      전개.분기점 = "최원태가 5이닝을 넘기며 2실점 이하로 막아내는가"
#      그 리스크의 발생 확률 15% · 원정 쪽 4%p  ← 자료14 가 답을 준 변수
#    `card.verdict_block` 은 이것을 "⚠️ 갈림길 —" 로 조립한다. 그런데 그 함수를
#    쓰는 곳은 `pipeline.render_star_board`(슬레이트 보드) **하나뿐**이고,
#    실제 발송 카드는 `pregame_push.compose_card → form_card.render_form_card`
#    를 타는데 거기엔 전개·분기점이 **한 글자도 없었다.**
#    `card.py:668` 이 "⑥ 전개·분기점·예상점수·발생확률이 카드에 하나도 없었다"
#    고 적고 고친 2026-09-07 개편이 **발송 경로에는 배선되지 않았다.**
#    PGP-2("새로 만든 쪽이 죽고 옛 경로가 살아 있었다")와 같은 형태다.
#
# ⚠️ 문구를 두 곳에 적지 않는다 — `card.branch_lines` 를 **부른다**.

_BRANCH_M = {
    "p_home": 0.52, "우세": "home",
    "근거": ["자료4 최근 등판", "자료1 타선", "자료12 레이팅"],
    "변수": ["최원태의 이전 맞대결 부진 재발 — 발생 시 원정 방향 약 4%p · "
             "발생 확률 15% · 현재 p에 1%p 기반영 · 근거 자료4"],
    "뉴스반영": {"적용": False, "조정폭": "0", "사유": ""},
    "확신도": "중",
    "전개": {"홈승리경로": "…", "원정승리경로": "…",
             "분기점": "최원태가 5이닝을 넘기며 2실점 이하로 막아내는가",
             "예상점수": {"홈": 5, "원정": 4}},
    "결론": {"승자": "삼성", "판단": "박빙이다."},
}


def test_카드가_갈림길을_싣는다():
    """🔴 판정이 낸 분기점이 발송 카드에 나가야 한다."""
    text = render_form_card(_jg(matchup=_BRANCH_M))
    assert "갈림길" in text, f"갈림길이 카드에 없다:\n{text}"
    assert "최원태가 5이닝을 넘기며 2실점 이하로 막아내는가" in text


def test_카드가_발생확률과_영향을_함께_싣는다():
    """자료14 가 답을 준 변수만 발생 확률을 갖는다 — 그 수가 카드에 보여야 한다."""
    text = render_form_card(_jg(matchup=_BRANCH_M))
    assert "15%" in text and "4%p" in text, f"발생 확률·영향이 없다:\n{text}"


def test_분기점이_없으면_그_줄도_없다():
    """⚠️ 반대 위험 — 없는 것을 지어내거나 빈 제목만 남기지 않는다."""
    m = {k: v for k, v in _BRANCH_M.items() if k != "전개"}
    assert "갈림길" not in render_form_card(_jg(matchup=m))


def test_발송_카드가_같은_조립기를_쓴다():
    """⚠️ 사본 금지 — 보드와 카드가 같은 함수를 부른다."""
    from app.engine.card import branch_lines

    lines = branch_lines(_BRANCH_M)
    assert lines and "갈림길" in lines[0]
    text = compose_card(_jg(matchup=_BRANCH_M), "", "kbo")
    for ln in lines:
        assert ln.strip() in text, f"조립기 출력이 카드에 그대로 안 들어갔다: {ln!r}"
