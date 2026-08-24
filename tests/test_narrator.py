"""[B] 서술 단계 — 필드 나열이 아니라 분석 글이 나오는지 검증.

실사고: 판정 JSON을 그대로 문장화해 "시장: 홈 55%. 모델: 53.5%. 전문가: [PickDawgz]…"
같은 필드 나열이 기본층에 나갔다. 서술은 맥락·인과·승부처를 담아야 한다.
"""

from app.engine.narrator import (
    BAD_EXAMPLE,
    NARRATIVE_TOOL,
    GOOD_EXAMPLE,
    SYSTEM,
    Narrator,
    _normalize,
    _payload_game,
    clean_line,
)


# ---------------------------------------------------------------- 프롬프트 계약

def test_prompt_carries_both_examples():
    """[B-4] 좋은 예시와 나쁜 예시를 함께 넣어 대조시킨다."""
    assert GOOD_EXAMPLE in SYSTEM and BAD_EXAMPLE in SYSTEM
    assert "스쿠발" in GOOD_EXAMPLE and "승부처" in GOOD_EXAMPLE
    for rule in ("각주", "복붙 금지", "그래서 무슨 일이 벌어지는가", "승부처"):
        assert rule in SYSTEM


# ---------------------------------------------------------------- 출력 가드

def test_footnote_markers_are_stripped():
    """[B-3] 각주 마커 제거."""
    assert clean_line("스쿠발은 WHIP 0.96이다[1][3][6].") == "스쿠발은 WHIP 0.96이다."


def test_field_enumeration_is_rejected():
    """[B-3] 필드 나열식 문장은 기본층에 쓰지 않는다."""
    assert clean_line("시장: 55%. 모델: 53.5%.") == ""
    assert clean_line("p_final 62%로 계산됐다") == ""


def test_generic_template_lines_are_rejected():
    """[B-3] 그 경기 고유 정보가 없는 범용 문구는 줄째로 버린다."""
    assert clean_line("부상·라인업 변수는 킥오프 직전에 바뀔 수 있습니다.") == ""
    assert clean_line("변수가 많은 경기다.") == ""
    # 고유 수치가 있는 문장은 통과
    assert clean_line("존스가 ERA 4.78로 기복이 있어 초반이 관건이다.")


def test_normalize_keeps_three_elements():
    out = _normalize({"games": [{
        "game_id": "409", "context": "4연승 중이다[2].", "causal": "ERA 5.06에 이닝을 못 먹는다.",
        "decider": "존스가 초반을 버티느냐가 승부처다.", "expert_note": "3명 중 2명 언더.",
        "missing": "",
    }]})
    assert set(out) == {409}
    assert out[409]["context"] == "4연승 중이다."
    assert out[409]["decider"].endswith("승부처다.")


# ---------------------------------------------------------------- 입력 페이로드

def test_payload_includes_board_and_research_not_raw_probs():
    """[B-1] 서술 입력은 판정 결론 + 마켓 보드 + 리서치 재료."""
    jg = {
        "game_id": 1, "home": "H", "away": "A", "league": "MLB",
        "verdict": "결론", "judge_confidence": "high",
        "market_board": [{"desc": "언더 8.5", "odds": 1.87, "ev": 0.07,
                          "grade": "🟢", "grade_note": "이득 +7.0%"}],
        "expert_picks": [{"expert": "E", "site": "S", "pick": "Under 8.5",
                          "reasoning": "긴 원문", "record": "10-5"}],
        "stats": {"home_pitcher": "P"},
    }
    pay = _payload_game(jg, {"home_recent_form": {"form": "WWLWL"}})
    assert pay["market_board"][0]["grade"] == "🟢"
    assert pay["research"]["home_recent_form"]["form"] == "WWLWL"
    assert "p_claude" not in pay and "p_model" not in pay


# ---------------------------------------------------------------- 폴백

async def test_mock_mode_returns_no_narrative():
    """[규칙 3] 키가 없으면 서술 없이 결정적 렌더로 폴백한다 (크래시 금지)."""
    assert await Narrator(mock=True).narrate([{"game_id": 1, "status": "scheduled"}], "mlb") == {}


async def test_failure_falls_back_without_raising(monkeypatch):
    """[B] 서술 호출이 실패해도 분석을 막지 않는다."""
    n = Narrator(mock=False)

    async def boom(payload):
        raise RuntimeError("narrator did not return a narrative tool call")

    monkeypatch.setattr(n, "_call", boom)
    assert await n.narrate([{"game_id": 1, "status": "scheduled", "home": "H", "away": "A"}],
                           "mlb") == {}


# ---------------------------------------------------------------- 렌더 통합

def _jg_with_narrative(**over):
    from app.engine.markets import grade_candidate

    jg = {
        "game_id": 9, "sport": "mlb", "home": "Los Angeles Dodgers",
        "away": "Pittsburgh Pirates", "league": "MLB", "status": "scheduled",
        "status_label": "", "starts_at_kst": "08/25 10:38", "model_valid": True,
        "p_model": 0.60, "p_market": 0.58, "p_claude": 0.61,
        "market_probs": {"Los Angeles Dodgers": 0.58, "Pittsburgh Pirates": 0.42},
        "best_odds": {"Los Angeles Dodgers": 1.72, "Pittsburgh Pirates": 2.30},
        "judge_confidence": "high", "verdict": "다저스 우위", "expert_picks": [],
        "stats": {"home_pitcher": "Tarik Skubal", "away_pitcher": "Jared Jones"},
        "research": {"home_recent_form": {"form": "WWWWL"},
                     "absences": ["Pittsburgh Pirates의 Oneil Cruz 결장"]},
        "market_board": [
            {"market": "h2h", "side": "Los Angeles Dodgers", "line": None,
             "desc": "LA 다저스 승", "odds": 1.72, "p": 0.63, "ev": 0.084,
             "axes_kr": "실데이터+전문가", "approved": True, "reject_reason": None},
        ],
        "markets_unpriced": [],
        "narrative": {
            "context": "트레이드 마감일에 디트로이트에서 이적한 스쿠발의 홈 등판이다.",
            "causal": "스쿠발은 113.2이닝 135탈삼진에 볼넷이 20개뿐이라 주자를 거의 안 내보낸다.",
            "decider": "존스가 초반 다저스 상위 타선을 버텨내느냐가 갈림길이다.",
            "expert_note": "3명 중 2명이 다저스 승, 전적 61-42.",
            "missing": "",
        },
    }
    jg.update(over)
    for c in jg["market_board"]:
        c["grade"], c["grade_note"] = grade_candidate(c)
    return jg


def test_easy_layer_carries_context_causal_decider():
    """[B-2] 기본층에 맥락·인과·승부처 3요소가 모두 들어간다."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    easy = render_game_easy(_jg_with_narrative()).split(DETAIL_SEP)[0]
    assert "스쿠발의 홈 등판" in easy                      # ① 맥락
    assert "볼넷이 20개뿐" in easy                          # ② 인과
    assert easy.count("승부처:") == 1 and "존스가 초반" in easy   # ③ 승부처
    assert 6 <= len(easy.splitlines()) <= 9                 # [B-5] 분량


def test_easy_layer_drops_generic_narrative_lines():
    """[B-3] 고유 정보 없는 서술 줄은 기본층에 넣지 않는다."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    jg = _jg_with_narrative(narrative={
        "context": "중요한 경기다.", "causal": "변수가 많다.",
        "decider": "지켜봐야 한다.", "expert_note": "", "missing": "",
    })
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    assert "중요한 경기다" not in easy and "변수가 많다" not in easy
    assert "승부처:" not in easy


def test_detail_uses_compressed_expert_note():
    """[B-3] 상세의 전문가 줄은 원문 복붙이 아니라 압축 요약을 먼저 쓴다."""
    from app.pipeline import render_game_section

    out = render_game_section(_jg_with_narrative())
    assert "전문가 요약: 3명 중 2명이 다저스 승" in out


# ---------------------------------------------------------------- [4] 추천 마켓 근거

def test_prompt_requires_top_market_rationale_and_order():
    """[4] 최고 등급 마켓의 근거를 서술에 녹이고, 맥락→인과→승부처→추천 마켓 순."""
    assert "최고 등급 마켓의 근거를 서술에 반드시 녹여라" in SYSTEM
    assert "맥락 → 인과 → 승부처 → 추천 마켓" in SYSTEM
    assert "4~6줄" in SYSTEM
    props = NARRATIVE_TOOL["input_schema"]["properties"]["games"]["items"]
    assert "market_case" in props["properties"]
    assert "market_case" in props["required"]


def test_easy_layer_includes_market_case_after_decider():
    """[4] 기본층 순서: 맥락 → 인과 → 걸 만한가 → 승부처 → 추천 마켓 근거."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    jg = _jg_with_narrative()
    jg["narrative"]["market_case"] = (
        "두 선발 모두 QS 기대치가 낮아 난타전 가능성이 크고, 이 때문에 오버 9.0에 무게가 실린다.")
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    ls = easy.splitlines()
    i_decider = next(i for i, l in enumerate(ls) if l.startswith("승부처:"))
    i_case = next(i for i, l in enumerate(ls) if "오버 9.0에 무게" in l)
    i_value = next(i for i, l in enumerate(ls) if l.startswith("걸 만한가?"))
    assert i_value < i_decider < i_case
    assert 6 <= len(ls) <= 9
