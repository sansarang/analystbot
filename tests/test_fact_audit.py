"""[감시 L1] 사실 감시 — 추출·분류·격리.

🔴 이 층의 최대 리스크는 **오탐**이다. 테스트도 거기에 집중한다:
   "원문에 없다"(not_found)와 "값이 다르다"(mismatch)를 섞지 않는다.
"""
from __future__ import annotations

import asyncio

import pytest

from app.engine import fact_audit
from app.engine.fact_audit import audit, classify, extract_claims

#: 2026-09-02 실카드 SSG@키움 근거 전문 (사용자 수신분)
REAL_VERDICT = {
    "근거": [
        "자료1: 홈팀 최근 3경기 LLL, 득점 1.0/경기 실점 8.67/경기(3득점-26실점) "
        "vs 원정팀 최근 3경기 WLW, 득점 6.0/경기 실점 2.67/경기(18득점-8실점)",
        "자료4: 오늘 선발 최근 5등판 비교 - 하영민 평균 5.13이닝 4.2실점, "
        "김건우 평균 4.93이닝 3.4실점으로 두 선발 모두 최근 불안정",
        "자료9: 양팀 불펜 ERA 5.39 vs 5.38로 사실상 동일해 변별력 없음",
    ],
    "변수": ["표본 3경기 한계 - 홈팀은 상대가 두산(5위,0.535)x2로 실점 부풀려졌을 가능성"],
}
#: 그 판정에 실제로 실린 자료(발췌)
REAL_PROMPT = """
9. 양팀 불펜: {"home": {"era": 5.39}, "away": {"era": 5.38}}
1. 박스스코어: {"home": {"runs_l3": 3, "runs_allowed_l3": 26},
                "away": {"runs_l3": 18, "runs_allowed_l3": 8}}
4. 선발등판: [{"innings": 5.0, "r": 4}, {"innings": 5.13, "r": 4.2},
             {"innings": 4.93, "r": 3.4}]
"""


def test_extracts_only_numbers_with_units():
    """맨숫자·날짜·배수는 뽑지 않는다 — 원문에 없어도 정상이기 때문이다."""
    claims = extract_claims(REAL_VERDICT)
    units = {c["unit"] for c in claims}
    assert "era" in units and "ip" in units
    # "5위" · "0.535" · "x2" 는 단위가 없어 추출 대상이 아니다
    assert not any(c["value"] == 0.535 for c in claims)
    assert not any(c["unit"] == "" for c in claims)


def test_real_card_numbers_verify_against_its_source():
    """실카드 근거의 수치가 원문에서 확인된다."""
    res = audit(REAL_VERDICT, REAL_PROMPT)
    assert res["mismatch_n"] == 0, res["mismatch_detail"]
    assert res["verified_n"] + res["derived_n"] > 0


def test_tampered_value_is_a_mismatch():
    """같은 단위 값이 원문에 있는데 다르면 **불일치**다."""
    bad = {**REAL_VERDICT,
           "근거": [REAL_VERDICT["근거"][2].replace("5.39", "9.99")]}
    res = audit(bad, REAL_PROMPT)
    assert res["mismatch_n"] == 1
    d = res["mismatch_detail"][0]
    assert d["unit"] == "era" and d["claimed"] == 9.99


def test_absent_unit_is_not_found_not_mismatch():
    """🔴 **원문에 아예 없음 ≠ 값이 다름.** 환각 후보이지 확정이 아니다."""
    v = {"근거": ["WHIP 1.42 로 제구가 불안하다"]}
    res = audit(v, REAL_PROMPT)          # 원문에 WHIP 이 없다
    assert res["not_found_n"] == 1 and res["mismatch_n"] == 0


def test_derived_average_is_recomputed_within_tolerance():
    """"평균 4.93이닝" 같은 계산값은 원본에서 재계산해 확인한다."""
    kind, _ = classify({"text": "평균 5.02이닝", "unit": "ip", "value": 5.02,
                        "derived": True},
                       '{"innings": 5.0}\n{"innings": 5.13}\n{"innings": 4.93}',
                       0.05)
    assert kind in ("verified", "derived")


def test_derived_mismatch_is_not_asserted_as_hallucination():
    """어느 부분집합의 평균인지 모른다 — 산수 검사가 이 층의 목적이 아니다."""
    kind, detail = classify({"text": "평균 7.7이닝", "unit": "ip", "value": 7.7,
                             "derived": True},
                            '{"innings": 5.0}\n{"innings": 4.0}', 0.05)
    assert kind == "not_found" and detail is None


def test_header_numbers_are_not_audited():
    """p·별점·필요배당은 모델 산출물이지 인용이 아니다."""
    v = {"p_home": 0.66, "확신도": "중", "근거": []}
    assert audit(v, REAL_PROMPT)["not_found_n"] == 0


def test_audit_failure_never_escapes():
    """P4 — 감시 실패가 판정·발송을 막으면 안 되고, 침묵해서도 안 된다."""
    from app.engine import fact_audit as fa

    async def boom(*a, **k):
        raise RuntimeError("감사 폭발")

    orig = fa.load_prompt
    fa.load_prompt = boom
    try:
        got = asyncio.run(fa.run(None, None, {"game_id": 1, "sport": "kbo",
                                              "matchup": {"근거": ["x"]}}))
    finally:
        fa.load_prompt = orig
    assert got is None          # 예외가 밖으로 나오지 않는다


def test_disabled_flag_short_circuits(monkeypatch):
    """비활성이면 즉시 반환 — 아무것도 읽지 않는다."""
    from app.config import Settings
    from app.engine import fact_audit as fa

    monkeypatch.setattr("app.config.get_settings",
                        lambda: Settings(_env_file=None, fact_audit_enabled=False))
    assert asyncio.run(fa.run(None, None, {"game_id": 1})) is None


def test_alert_reuses_the_existing_suppression(monkeypatch):
    """P5 — 새 억제 체계를 만들지 않는다. 워치독 헬퍼를 부른다."""
    from pathlib import Path

    src = Path("app/engine/fact_audit.py").read_text(encoding="utf-8")
    assert "from app.alerts import watchdog" in src
    assert "SUPPRESS" not in src and "_claim(" not in src


def test_no_hardcoded_thresholds():
    """P2 — 허용 오차·활성 여부는 config 에서 읽는다."""
    from pathlib import Path

    src = Path("app/engine/fact_audit.py").read_text(encoding="utf-8")
    assert "get_settings().fact_audit_tolerance" in src
    assert "fact_audit_enabled" in src


# ── [2026-09-05] 야구 이닝 표기법 오탐 ────────────────────────────────
# 실사고: 운영 경보 W-FACT-MISMATCH game=1711 "ip 주장 5.6 vs 원문 5.667".
# 원문 이닝은 `parse_innings` 가 만든 소수(5⅔ → 5.667)인데 판정은 같은 이닝을
# 야구 표기(5.2)나 1자리 절사(5.6)로 적는다. 숫자만 비교해 **정확한 인용이
# 환각으로 찍혔다.**
_IP_PROMPT = '{"home": {"starter_recent": [{"innings": 5.667}, {"innings": 6.333}]}}'


@pytest.mark.parametrize("line", [
    "홈 선발 5.2이닝",   # 야구 표기 5⅔ — 원문 5.667 과 같은 값
    "홈 선발 6.1이닝",   # 야구 표기 6⅓ — 원문 6.333 과 같은 값
    "홈 선발 5.6이닝",   # 1자리 절사 (5.667 → 5.6)
    "홈 선발 5.7이닝",   # 1자리 반올림
])
def test_innings_notation_is_not_a_hallucination(line):
    """같은 이닝을 다르게 적은 것은 불일치가 아니다."""
    res = fact_audit.audit({"근거": [line]}, _IP_PROMPT)
    assert res["mismatch_n"] == 0, res["mismatch_detail"]


@pytest.mark.parametrize("line,claimed", [
    ("홈 선발 9.0이닝", 9.0),
    ("홈 선발 2.1이닝", 2.1),
    ("홈 선발 5.9이닝", 5.9),
])
def test_real_mismatch_still_caught(line, claimed):
    """반대 위험 — 표기법을 봐준다고 진짜 불일치를 놓치면 안 된다."""
    res = fact_audit.audit({"근거": [line]}, _IP_PROMPT)
    assert res["mismatch_n"] == 1
    assert res["mismatch_detail"][0]["claimed"] == claimed


def test_written_at_does_not_swallow_whole_innings():
    """정수 인용이 큰 오차를 덮지 않는다 — 자릿수 해석 상한 0.1."""
    assert fact_audit.written_at(6.0, 6.049)
    assert not fact_audit.written_at(6.0, 6.9)


def test_notation_reading_only_for_innings():
    """`.1`/`.2` 해석은 이닝만이다. ERA 3.2 는 3⅔ 가 아니다."""
    assert fact_audit.readings(5.2, "ip") == [5.2, 5.667]
    assert fact_audit.readings(3.2, "era") == [3.2]
