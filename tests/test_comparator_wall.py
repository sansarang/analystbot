"""[§9 3단] **정보 차단벽** — 대조봇은 카드 두 장 외에는 아무것도 못 본다.

이 파일이 3단 구현의 **첫 단계**다. 프롬프트로는 차단벽을 세울 수 없다 —
`build_payload`가 무엇을 넘기는지가 차단벽의 실체이고, 여기서 그것을 직접 검사한다.

🔴 3단이 원본 사실에 닿으면 1·2단의 규율이 전부 무의미해진다. 카드를 무시하고
   원본에서 결론을 세운 뒤 카드를 거기 맞추기 때문이다. λ가 한쪽으로 기울자
   모든 서술이 그쪽으로 정렬됐던 실패가 정확히 그 형태였다.
"""
import json
import pathlib

import pytest

from app.engine import comparator as C
from app.engine.card import CELLS

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "comparator_payload.json"


def _jg(**over):
    jg = {
        "game_id": 7, "home": "Kia Tigers", "away": "Lotte Giants",
        "home_kr": "KIA", "away_kr": "롯데", "sport": "kbo",
        # 아래는 전부 **3단이 봐서는 안 되는 것들**이다.
        "research": {"home_pitcher": {"era_season": 3.2}, "absences": ["A 선수 결장"]},
        "card": {"home": {k: {"facts": [f"{k} 원본사실"], "metrics": {"x": 1}}
                          for k, _ in CELLS},
                 "away": {k: {"facts": [f"{k} 원본사실"], "metrics": {"x": 2}}
                          for k, _ in CELLS}},
        "p_claude": 0.63, "p_model": 0.58, "p_market": 0.55, "p_final": 0.61,
        "best_odds": {"Kia Tigers": 1.72}, "market_board": [{"desc": "승", "p": 0.63}],
        "alt_markets": [{"key": "totals"}], "lambda_trace": ["4.5 → 4.8"],
        "verdict": {"p_claude": 0.63}, "news": "속보: 에이스 결장",
        "cells": {
            "home": {"bullpen": {"symbol": "▼", "reason": "직전 경기 투수 5명 투입"},
                     "starter": {"symbol": "▲", "reason": "시즌 ERA 3.2·평균 6.1이닝"}},
            "away": {"bullpen": {"symbol": "▲", "reason": "연투 투수 없음"},
                     "recent3": {"symbol": "▼", "reason": "최근 3경기 4득점 18실점"}}},
    }
    jg.update(over)
    return jg


# ------------------------------------------------------------------ 차단벽

def test_payload_carries_only_cards():
    """🔴 이 테스트가 차단벽이다. 필드를 추가하려면 여기를 먼저 보라."""
    p = C.build_payload(_jg())
    assert set(p) == {"home_team", "away_team", "cards", "uncollected"}


def test_no_forbidden_key_anywhere_in_the_payload():
    """원본 사실·확률·배당은 **한 조각도** 들어가지 않는다 — 중첩까지 훑는다."""
    blob = json.dumps(C.build_payload(_jg()), ensure_ascii=False)
    for banned in C.FORBIDDEN_KEYS:
        assert f'"{banned}"' not in blob, f"차단벽이 뚫렸다: {banned}"


def test_no_raw_facts_leak_through_the_cards():
    """카드에는 ▲▼와 사유만 있다 — 1단이 모은 원본 사실 문자열은 없다."""
    blob = json.dumps(C.build_payload(_jg()), ensure_ascii=False)
    assert "원본사실" not in blob
    assert "metrics" not in blob and "facts" not in blob


def test_no_probability_or_odds_values_leak():
    """숫자 자체가 새는지도 본다 — 키 이름만 지우고 값을 넣는 실수를 막는다."""
    blob = json.dumps(C.build_payload(_jg()), ensure_ascii=False)
    for v in ("0.63", "0.58", "0.55", "1.72", "4.5"):
        assert v not in blob, f"확률·배당 값이 샜다: {v}"


def test_uncollected_gives_labels_only_not_the_missing_facts():
    """빈칸의 내용을 알려주면 3단이 그것을 상상으로 메운다."""
    p = C.build_payload(_jg())
    assert p["uncollected"] == ["타선", "무게"]
    assert all(isinstance(x, str) for x in p["uncollected"])


def test_dumped_payload_matches_the_real_pipeline_shape():
    """실데이터에서 뜬 덤프와 구조가 같아야 한다 — 합성 입력만으로는
    파이프라인이 실제로 넘기는 모양이 바뀐 것을 못 잡는다."""
    saved = json.loads(FIXTURE.read_text(encoding="utf-8"))
    live = C.build_payload(_jg())
    assert set(saved) == set(live)
    assert set(saved["cards"]) == set(live["cards"]) == {"home", "away"}
    for side in ("home", "away"):
        for row in saved["cards"][side]:
            assert set(row) == {"cell", "label", "symbol", "reason"}
    blob = json.dumps(saved, ensure_ascii=False)
    for banned in C.FORBIDDEN_KEYS:
        assert f'"{banned}"' not in blob, f"덤프에 금지 키: {banned}"


# ------------------------------------------------------------------ 재료 규율

def test_no_material_means_no_call():
    """🔴 재료 없이 결론을 만들지 않는다 — 양쪽 판정이 비면 부르지 않는다."""
    assert not C.has_material(C.build_payload(_jg(cells={"home": {}, "away": {}})))
    assert C.has_material(C.build_payload(_jg()))


# ------------------------------------------------------------------ 출력 규율

def test_invented_probability_is_rejected():
    """🔴 3단이 지어낸 숫자는 사용자에게 근거처럼 읽힌다."""
    assert C.invents_probability("KIA가 63% 우세하다")
    assert C.invents_probability("승률 60 퍼센트")
    assert not C.invents_probability("불펜 5명 투입으로 KIA가 앞선다")


def test_reason_must_cite_the_cards():
    p = C.build_payload(_jg())
    assert C.cites_cards("롯데는 연투 투수 없음이 크다", p)
    assert not C.cites_cards("전반적으로 흐름이 좋아 보인다", p)


def test_basis_cells_cannot_name_unjudged_cells():
    """보지 않은 칸을 근거로 들면 그 칸이 판정된 것처럼 보인다."""
    p = C.build_payload(_jg())
    assert C.basis_is_real(["bullpen", "batting", "recent3"], p) == ["bullpen", "recent3"]


def test_thin_card_caps_confidence_at_low():
    """미수집이 절반을 넘으면 남은 칸으로 다섯 칸짜리 판단을 하는 셈이다."""
    thin = _jg(cells={"home": {"bullpen": {"symbol": "▲", "reason": "x"}}, "away": {}})
    assert C.thin_card_caps_confidence(C.build_payload(thin), "높음") == "낮음"
    assert C.thin_card_caps_confidence(C.build_payload(_jg()), "높음") == "높음"


def test_unknown_confidence_falls_back_not_crashes():
    assert C.thin_card_caps_confidence(C.build_payload(_jg()), "매우높음") == "보통"


@pytest.mark.asyncio
async def test_disabled_role_returns_empty_not_a_fake_verdict():
    """🔴 빈 판정을 'none 우세'로 채우면 판정한 것처럼 보인다."""
    from app.config import Settings

    s = Settings(force_mock=True, judge_a_provider="")
    assert await C.compare_game(_jg(), settings=s) == {}


# ------------------------------------------------------------------ 배선

def _calls_in_app(name: str) -> list[str]:
    import ast as _ast

    root = pathlib.Path(__file__).resolve().parents[1]
    hits = []
    for path in (root / "app").rglob("*.py"):
        for node in _ast.walk(_ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, _ast.Call):
                continue
            f = node.func
            called = (f.id if isinstance(f, _ast.Name)
                      else f.attr if isinstance(f, _ast.Attribute) else None)
            if called == name:
                hits.append(str(path.relative_to(root)))
    return sorted(set(hits))


@pytest.mark.parametrize("name", ["compare_game", "_attach_card_compare",
                                  "compare_line"])
def test_stage3_has_a_real_caller_in_app(name):
    """🔴 app/ 안에 호출처가 없으면 사용자에게 도달하지 않는다.

    2단이 구현만 되고 호출처가 0이었던 사고(2026-08-27)를 3단에서 반복하지 않는다.
    """
    callers = [c for c in _calls_in_app(name)
               if c != "app/engine/comparator.py"]
    assert callers, f"{name}() 호출처가 app/ 안에 없다 — 배선되지 않았다"


def test_stage3_runs_after_stage2():
    """3단은 2단 **뒤**여야 한다 — 카드가 없으면 대조할 것이 없다."""
    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "app/pipeline.py").read_text(encoding="utf-8")
    assert (src.index("await _attach_cell_verdicts(")
            < src.index("await _attach_card_compare(")), "3단이 2단보다 앞에 있다"


def test_compare_line_never_prints_a_probability():
    """🔴 3단은 확률을 주지 않는다 — 렌더가 숫자를 붙이면 없는 말을 만드는 것이다."""
    from app.engine.card import compare_line

    line = compare_line({"home_kr": "KIA", "away_kr": "롯데",
                         "compare": {"favored": "home", "confidence": "높음",
                                     "reason": "불펜 5명 투입"}})
    assert "KIA" in line and "%" not in line


def test_compare_line_is_silent_without_a_verdict():
    """빈말을 만들지 않는다."""
    from app.engine.card import compare_line

    assert compare_line({"compare": {}}) is None
    assert compare_line({}) is None


def test_undecidable_is_said_plainly():
    from app.engine.card import compare_line

    line = compare_line({"compare": {"favored": "none", "confidence": "낮음",
                                     "reason": "양쪽 다 얇다"}})
    assert "우열을 가리기 어렵다" in line


def test_slate_hint_matches_the_sport():
    """🔴 KBO 질문에 '/soccer'를 안내하고 있었다 — 종목이 셋 이상인데 이분법이었다."""
    from app.bot.main import _format_team_reply

    g = _jg(status="scheduled", starts_at_kst="18:30", league="KBO",
            market_board=[], research={}, expert_picks=[])
    for sport, expect, banned in (("kbo", "KBO", "/soccer"),
                                  ("npb", "NPB", "/soccer"),
                                  ("mlb", "/mlb", "/soccer"),
                                  ("soccer", "/soccer", "/mlb")):
        out = _format_team_reply(g, "", sport)
        tail = out.rsplit("전체 슬레이트는", 1)[-1]
        assert expect in tail, f"{sport}: {tail!r}"
        assert banned not in tail, f"{sport}에 {banned}를 안내한다"
