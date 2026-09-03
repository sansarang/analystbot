"""[L1 보강 2026-09-03] 파생값 재계산 — **리허설이 잡은 실제 오탐**으로 잠근다.

🔴 리허설 실측(NPB game=2541): 판정이 "최근 4경기 27이닝 7자책"이라 적었고
   L1 이 이걸 **환각(mismatch)** 으로 찍었다. 27 은 4경기 **합계**인데
   원문에는 경기별 이닝(≈6~8)만 있어 "가장 가까운 값 8.0"과 19이닝 차이가
   났기 때문이다. **판정은 옳았고 감시가 틀렸다.**

   같은 실행에서 `derived` 가 7경기 내내 **0건**이었다. "평균 6.4이닝"을
   재계산할 때 양 팀 모든 경기를 한 덩어리로 평균 내니 맞을 리가 없었다.
   그래서 `not_found` 34% 는 환각률이 아니라 **재계산 실패율**이었다.
"""
import pytest

from app.engine.fact_audit import audit, classify, claim_subject, sample_n

#: 리허설 프롬프트를 재현한 최소 구조 — 진영이 둘이라는 점이 핵심이다.
PROMPT = """
자료4 선발등판: {"home": {"name": "金丸夢斗",
                 "games": [{"innings": 6.667, "er": 2}, {"innings": 7.0, "er": 1},
                           {"innings": 6.333, "er": 3}, {"innings": 7.0, "er": 1}]},
                "away": {"name": "栗林良吏",
                 "games": [{"innings": 6.0, "er": 4}, {"innings": 6.0, "er": 4},
                           {"innings": 6.667, "er": 6}]}}
자료9 불펜: {"home": {"era": 3.25}, "away": {"era": 3.40}}
"""


def test_sum_expression_is_recognised_as_derived():
    """① 합계 인용이 **환각이 아니다.** (리허설 실제 문장)"""
    text = ("자료4: 홈 선발 金丸夢斗 최근 4경기 27이닝 7자책(약 2.33), "
            "BB 6/K 25로 제구·구위 모두 안정적")
    assert claim_subject(text) == "home"
    assert sample_n(text) == 4
    kind, detail = classify(
        {"text": text, "unit": "ip", "value": 27.0, "derived": True,
         "subject": "home", "n": 4}, PROMPT, 0.05)
    assert kind == "derived", f"합계 27 을 {kind} 로 봤다 (상세={detail})"


def test_second_real_case_away_sum():
    """① 원정 쪽 실제 문장 — 3경기 18.667이닝."""
    kind, _ = classify(
        {"text": "원정 선발 栗林良吏 최근 3경기 18.667이닝 14자책",
         "unit": "ip", "value": 18.667, "derived": True,
         "subject": "away", "n": 3}, PROMPT, 0.05)
    assert kind == "derived"


def test_average_uses_that_pitchers_array_only():
    """② "평균 6.75이닝" 은 **그 선수의** 배열로만 재계산한다.

    종전에는 양 팀 7경기를 한 덩어리로 평균 내 6.52 가 나왔고, 6.75 와
    어긋나 not_found 로 떨어졌다. 진영을 갈라야 맞는다.
    """
    kind, _ = classify(
        {"text": "홈 선발 평균 6.75이닝", "unit": "ip", "value": 6.75,
         "derived": True, "subject": "home", "n": 4}, PROMPT, 0.05)
    assert kind == "derived"


def test_wrong_sum_is_not_found_not_mismatch():
    """③ 합이 안 맞아도 **환각으로 단정하지 않는다** — 검증 못 한 것뿐이다."""
    kind, detail = classify(
        {"text": "홈 선발 최근 4경기 99이닝", "unit": "ip", "value": 99.0,
         "derived": True, "subject": "home", "n": 4}, PROMPT, 0.05)
    assert kind == "not_found" and detail is None


def test_same_subject_same_sample_difference_is_still_mismatch():
    """④ 진짜 불일치는 그대로 잡는다 — 완화가 아니라 정밀화다."""
    kind, detail = classify(
        {"text": "홈 불펜 ERA 9.99", "unit": "era", "value": 9.99,
         "derived": False, "subject": "home", "n": None}, PROMPT, 0.05)
    assert kind == "mismatch"
    assert detail["subject"] == "home" and detail["claimed"] == 9.99


def test_unknown_subject_blocks_recompute_but_not_direct_quote():
    """주체 불명: **재계산은 포기**, 직접 인용은 전체 풀로 대조."""
    # 재계산 — 어느 진영인지 모르면 하지 않는다
    kind, _ = classify(
        {"text": "최근 4경기 평균 6.75이닝", "unit": "ip", "value": 6.75,
         "derived": True, "subject": None, "n": 4}, PROMPT, 0.05)
    assert kind == "not_found"
    # 직접 인용 — 값 하나를 그대로 적은 것이라 모호성이 없다
    kind, _ = classify(
        {"text": "불펜 ERA 3.25", "unit": "era", "value": 3.25,
         "derived": False, "subject": None, "n": None}, PROMPT, 0.05)
    assert kind == "verified"


def test_mismatch_docstring_pins_the_definition():
    """🔴 정의를 코드에 박는다 — 다음 사람이 넓히지 않도록."""
    assert "동일 주체·동일 단위·동일 표본" in classify.__doc__
    assert "환각률이 아니라 검증 불가율" in classify.__doc__


def test_audit_end_to_end_on_the_real_verdict():
    """리허설 판정 원문 그대로 — mismatch 0 이어야 한다."""
    verdict = {"근거": [
        "자료4: 홈 선발 金丸夢斗 최근 4경기 27이닝 7자책(약 2.33), BB 6/K 25",
        "자료4: 원정 선발 栗林良吏 최근 3경기 18.667이닝 14자책(약 6.75)",
        "자료9: 불펜 ERA 홈 3.25 대 원정 3.40으로 홈이 근소하게 우위",
    ]}
    res = audit(verdict, PROMPT)
    assert res["mismatch_n"] == 0, res["mismatch_detail"]
    assert res["derived_n"] >= 2, res


def test_material3_is_measured_by_slots_not_emptiness():
    """[2d] 자료3 거짓 Y — `lineups_payload` 는 선발투수 키를 항상 넣는다.

    리허설 실측: `자료8=N slots=0` 인데 자료3 은 Y 로 찍혔다. 타순이 하나도
    없는데 "타순 있음"으로 읽히면, 공시 전후를 로그로 구분할 수 없다.
    """
    from pathlib import Path

    src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    i = src.index("[materials] game=")
    seg = src[max(0, i - 900):i + 400]
    assert "_slots >= 9" in seg, "자료3 이 여전히 dict 비어있음 기준이다"
    assert "자료3=%s" in seg
