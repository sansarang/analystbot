"""[투명 리포트 G2 2026-09-04] 5절 리포트 생성기.

🔴 **템플릿 채우기다. LLM 을 부르지 않는다.** 리포트가 재서술하면 그것이
   제2의 환각 경로다 — 카드가 맞는지 보려고 읽는 문서가 스스로 새 주장을
   하면, 검증 도구가 아니라 검증 대상이 하나 더 느는 것이다.
🔴 **재계산하지 않는다.** 확률·괴리·적중은 원장에 있는 값을 옮긴다.
   여기서 다시 계산하면 카드와 다른 숫자가 나올 수 있고, 그때 어느 쪽이
   맞는지 아무도 모른다.
🔴 **없는 것은 "없음 + 사유"다.** 빈 칸을 그럴듯하게 메우면 목적이 사라진다.
"""
from pathlib import Path

import pytest

from app.engine import glass_report as gr

GOLDEN = Path("tests/golden/glass_kbo_1708.md")


def _jg():
    """2026-09-04 KBO game=1708 (Kia @ KT) — 실제 슬레이트 값 모양."""
    return {
        "sport": "kbo", "game_id": 1708, "home": "KT Wiz", "away": "Kia Tigers",
        "date": "2026-09-04", "p_claude": 0.58,
        "matchup": {"우세": "home", "확신도": "중",
                    "model": "nvidia/nemotron-3-ultra-550b-a55b",
                    "근거": ["3경기 팀 득점 11점으로 상위 (자료1)",
                            "불펜 최근3경기 실점 7 · 가용성 피로 (자료9)",
                            "홈 선발 올러 8/29 6이닝 1실점 (자료4)"],
                    "변수": ["선발 조기 강판 — 발생 시 원정 방향 약 6%p · "
                            "현재 p에 2%p 기반영 · 근거 자료10"]},
        "research": {
            "home_usage": {"games": [{"date": "2026-09-03", "runs": 4}]},
            "away_usage": {"games": [{"date": "2026-09-03", "runs": 3}]},
            "home_starter_recent": [{"innings": 6.0, "r": 1}],
            "away_starter_recent": [{"innings": 5.0, "r": 3}],
            "home_bullpen": {"최근3경기": {"실점": 7}},
            "away_bullpen": {"최근3경기": {"실점": 2}},
        },
        "material10_status": "Y", "material10": {"이닝분포": {"p50": 5.2}},
        "material11_status": "해당없음",
    }


def _trace():
    from datetime import UTC, datetime
    t = datetime(2026, 9, 4, 8, 0, tzinfo=UTC)
    from datetime import timedelta
    return [
        {"stage": "조립", "at": t,
         "summary": "[materials] game=1708 자료3=N(타순 0명) 자료9=Y 자료10=Y 자료11=해당없음",
         "ref": None},
        {"stage": "판정", "at": t + timedelta(minutes=2),
         "summary": "[matchup] game=1708 Kia Tigers vs KT Wiz p_home=0.580 "
                    "우세=home 확신도=중 model=nvidia/nemotron-3-ultra-550b-a55b",
         "ref": {"prompt_sha": "a1b2c3d4e5f6"}},
        {"stage": "딥서치", "at": t + timedelta(minutes=3),
         "summary": "[deepsearch] game=1708 발동=False 트리거=- source=- "
                    "status=- 검색=0 이동=0.0%p",
         "ref": {"triggered": False, "triggers": [], "status": None}},
        {"stage": "게이트", "at": t + timedelta(minutes=9),
         "summary": "[gate] kbo game=1708 결과=보드만 확신도=medium p=0.580 시장p=0.512",
         "ref": None},
        {"stage": "발송", "at": t + timedelta(minutes=9),
         "summary": "[pregame] kbo game=1708 revised", "ref": {"revision": True}},
    ]


def _sources():
    return {
        "trace": _trace(),
        "ledger": {"odds": 1.95, "market_prob": 0.512, "divergence_pp": 6.8,
                   "edge_status": "none", "gate_result": "보드만",
                   "final_score": "2-5", "winner": "away", "hit": False},
        "audit": {"verified_n": 41, "derived_n": 6, "not_found_n": 3,
                  "mismatch_n": 1,
                  "mismatch_detail": [{"claim": "ip 17.1", "found": "7.0"}]},
        "variables": [{"raw": "선발 조기 강판 — 발생 시 원정 방향 약 6%p · "
                              "현재 p에 2%p 기반영 · 근거 자료10",
                       "direction": "away", "claimed_n": 6, "claimed_m": 2,
                       "source_ref": "자료10", "realized": "true",
                       "actual": {"innings": 3.2}}],
        "market": {"p_market_send": 0.512, "captured_at": None},
    }


# ─────────────────── 원칙 ───────────────────

def test_generator_never_calls_an_llm():
    """🔴 재서술은 제2의 환각 경로다."""
    src = Path("app/engine/glass_report.py").read_text(encoding="utf-8")
    for banned in ("complete(", "anthropic", "openai_compat", "judge_route",
                   "generate(", "gemini"):
        assert banned not in src, banned


def test_generator_never_recomputes_probability():
    """확률·괴리·적중은 **원장에서 읽는다** — 여기서 다시 계산하지 않는다."""
    src = Path("app/engine/glass_report.py").read_text(encoding="utf-8")
    for banned in ("clip_p_home", "devig", "value(", "classify(", "p_market("):
        assert banned not in src, banned


# ─────────────────── ① 재료 ───────────────────

def test_missing_material_says_none_with_a_reason():
    jg = _jg()
    jg["research"].pop("home_bullpen")
    jg["research"].pop("away_bullpen")
    md = gr.section_materials(jg, _trace())
    assert "없음" in md and "수집 실패 또는 미공시" in md


def test_retired_materials_stay_listed_with_the_reason():
    """🔴 빠지면 '왜 없지?'를 매번 다시 묻는다."""
    md = gr.section_materials(_jg(), _trace())
    assert "폐지 2026-09-04" in md
    assert md.count("폐지 2026-09-04") == 2, "자료7·8 둘 다 남아야 한다"


# ─────────────────── ② 딥서치 ───────────────────

def test_no_deepsearch_row_is_different_from_not_triggered():
    """🔴 '조사 안 했다'와 '조사했는데 아무것도 없었다'는 다르다."""
    none_md = gr.section_deepsearch([t for t in _trace()
                                     if t["stage"] != "딥서치"])
    assert "호출 자체가 없었다" in none_md
    off_md = gr.section_deepsearch(_trace())
    assert "미발동" in off_md and "트리거 판별값" in off_md


# ─────────────────── ③ 역참조 ───────────────────

@pytest.mark.parametrize("text,expected", [
    ("3경기 팀 득점 11점 (자료1)", [1]),
    ("자료1 과 자료 9 를 함께 본다", [1, 9]),
    ("선발이 좋다", []),
])
def test_reference_extraction(text, expected):
    assert gr.refs_in(text) == expected


def test_unreferenced_evidence_is_counted_as_a_hallucination_candidate():
    """🔴 근거가 재료를 못 가리키면 환각 후보다 — G3 가 이 숫자로 경보한다."""
    jg = _jg()
    jg["matchup"]["근거"] = ["선발이 좋다", "타선이 강하다 (자료1)"]
    md, n = gr.section_verdict(jg, None, [])
    assert n == 1
    assert "역참조 실패" in md
    assert "[→ ①의 자료1]" in md


# ─────────────────── ⑤ 원인 분류 ───────────────────

@pytest.mark.parametrize("ledger,audit,missing,expected", [
    ({"hit": True}, None, False, "적중 — 분류 없음"),
    ({"hit": None}, None, False, "미채점"),
    ({"hit": False}, None, True, "(a) 재료 부족"),
    ({"hit": False}, {"mismatch_n": 2}, False, "(b) 사실 오류 — L1 불일치"),
    ({"hit": False}, {"mismatch_n": 0}, False, "(c) 판단 오류"),
    (None, None, False, "미채점"),
])
def test_cause_classification_is_rule_based_not_narrative(
        ledger, audit, missing, expected):
    """사후 서사를 만들지 않는다 — 규칙으로 라벨만 붙인다."""
    assert gr.cause_class(ledger, audit, missing) == expected


# ─────────────────── 골든 파일 ───────────────────

def test_golden_snapshot():
    """실경기 1건 스냅샷. 문서가 조용히 바뀌면 이 테스트가 잡는다."""
    md, met = gr.build(_jg(), **_sources())
    if not GOLDEN.exists():                      # 최초 1회 생성
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(md, encoding="utf-8")
    assert md == GOLDEN.read_text(encoding="utf-8"), (
        "리포트 형식이 바뀌었다 — 의도한 변경이면 골든 파일을 갱신하라")
    assert met == {"unresolved": 0, "mismatch": 1}


def test_all_five_sections_present():
    md, _ = gr.build(_jg(), **_sources())
    for sec in ("① 무엇을 수집했나", "② 무엇을 조사했나", "③ 어떻게 결론냈나",
                "④ 시장과 어떻게 달랐나", "⑤ 결과와 복기"):
        assert sec in md, sec
    assert "부록 · 원장" in md, "원문 출처가 보여야 한다"


def test_filename_is_safe():
    assert gr.filename(_jg()) == "KBO_KiaTigers_KTWiz.md"
