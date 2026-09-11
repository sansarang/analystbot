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


# ── [2026-09-05] L1 오탐 3종 — 운영 judgement_audit 원문으로 특정했다 ────
# 실판정 20건(MLB 16 · NPB 4)에 걸어 측정: 불일치 3→1 · 검증됨 184→194 ·
# 검증불가 23→9 · 악화 0.
_P = '''1. 박스스코어: {"home": {"runs_per_game_l3": 5.0}}
4. 선발 최근 등판: {"home": {"선발등판": [{"innings": 6.0, "r": 1}]}}
9. 불펜: {"home": {"최근3경기": {"실점": 6, "이닝": 8.0}, "era": 3.10}}
10. 대장: {"이닝분포": {"p50": 2.0, "최장": 3.0}}
'''


def test_a_era_computed_from_innings_and_runs_is_not_a_hallucination():
    """(a) 8.0이닝 6실점 → ERA 6.75. 6×9÷8=6.75 로 판정이 맞다."""
    v = {"근거": ["홈 불펜 최근3경기 8.0이닝 6실점 ERA 6.75 — 자료9"]}
    res = fact_audit.audit(v, _P)
    assert res["mismatch_n"] == 0, res["mismatch_detail"]
    assert res["derived_n"] >= 1, "ERA 를 재계산으로 인정해야 한다"


def test_a_wrong_era_is_still_caught():
    """반대 위험 — 계산이 틀린 ERA 는 잡아야 한다.

    ⚠️ 원문에 ERA 가 **있을 때만** "불일치"라고 말할 수 있다. 없으면
       `not_found`(검증 못 했다)가 옳다 — 그것이 이 층의 설계다.
    """
    v = {"근거": ["홈 불펜 최근3경기 8.0이닝 6실점 ERA 19.9 — 자료9"]}
    assert fact_audit.audit(v, _P)["mismatch_n"] >= 1


def test_b_bullpen_numbers_are_not_compared_against_starter_numbers():
    """(b) 불펜 이닝을 자료4 선발 이닝과 대조하지 않는다."""
    v = {"근거": ["홈 불펜 최근3경기 8.0이닝 6실점 — 자료9"]}
    res = fact_audit.audit(v, _P)
    assert res["mismatch_n"] == 0, res["mismatch_detail"]


def test_b_relief_is_not_a_bullpen_cue():
    """`구원` 은 자료4(구원등판)·자료10 얘기다 — 자료9 로 좁히면 오탐이 난다."""
    assert fact_audit.claim_scope("구원 3경기 p50 2.0이닝", 14) != "bullpen"
    assert fact_audit.claim_scope("홈 불펜 최근3경기 8.0이닝", 12) == "bullpen"


def test_b_scope_is_decided_per_number_not_per_line():
    """한 줄에 선발과 불펜이 섞여 있다 — 숫자마다 가장 가까운 단서로 가른다."""
    line = "홈 선발 6.0이닝 소화 · 원정 불펜 8.0이닝 부담"
    claims = {c["value"]: c["scope"] for c in fact_audit.extract_claims({"근거": [line]})}
    assert claims[6.0] == "starter"
    assert claims[8.0] == "bullpen"


def test_c_rate_denominator_is_not_an_innings_claim():
    """(c) "9이닝 4.4볼넷" 의 9 는 BB/9 의 분모다."""
    line = "홈 선발 최근 5경기 5.0이닝 2.4실점·9이닝 4.4볼넷 — 자료4"
    vals = [c["value"] for c in fact_audit.extract_claims({"근거": [line]})
            if c["unit"] == "ip"]
    assert 9.0 not in vals
    assert 5.0 in vals


def test_c_projection_is_not_a_citation():
    """전망은 인용이 아니다 — "6이닝↑ 소화 부담" 은 원문에 없어야 정상이다."""
    v = {"근거": ["홈 불펜 6이닝↑ 소화 부담(자료9)"]}
    assert fact_audit.audit(v, _P)["mismatch_n"] == 0


def test_sample_size_reads_starts_too():
    """"최근 3선발 21이닝" 은 3등판 합계다 — 표본수를 읽어야 재계산이 된다."""
    assert fact_audit.sample_n("원정 선발 최근 3선발 21이닝 3실점") == 3


# ── [2026-09-06] 자료 번호를 값으로 읽었다 ──────────────────────────
def test_material_reference_number_is_not_a_value():
    """🔴 `자료10 이닝분포` 의 `10` 이 "10이닝"으로 읽혔다.

    자료10 의 이름이 하필 "이닝분포"라서 `(\\d+)\\s*이닝` 에 걸린다.
    **자료10 을 인용하는 변수는 전부 이 오탐이 난다** — 같은 경보가 반복됐다.
    실측 game=1716: `ip 주장 10.0 vs 원문 12.0`.
    """
    line = ("후라도가 이닝분포 하단(p25 6.0)에 그치고 피로한 원정 불펜이 조기 "
            "투입될 리스크 — 발생 시 홈 방향 약 2%p · 현재 p에 1%p 기반영 · "
            "근거 자료10 이닝분포 p25(n=2)")
    vals = [c["value"] for c in fact_audit.extract_claims({"변수": [line]})
            if c["unit"] == "ip"]
    assert 10.0 not in vals, f"자료 번호를 이닝으로 읽었다: {vals}"


def test_real_innings_next_to_a_material_ref_still_counts():
    """반대 위험 — 자료10 을 **인용한 값**은 그대로 검증한다."""
    line = "원정 선발 3이닝 미만 조기 강판 — 근거 자료10 (p50 1.2이닝, 최장 3.0이닝)"
    vals = sorted({c["value"] for c in fact_audit.extract_claims({"변수": [line]})
                   if c["unit"] == "ip"})
    assert vals == [1.2, 3.0], vals


@pytest.mark.parametrize("line,expect", [
    ("근거 자료4 선발등판", None),
    ("자료 10 이닝분포", None),
    ("홈 선발 6.0이닝 2실점 — 자료4", 6.0),
])
def test_material_ref_detection(line, expect):
    got = [c["value"] for c in fact_audit.extract_claims({"근거": [line]})
           if c["unit"] == "ip"]
    assert (got[0] if got else None) == expect, (line, got)


# ── [FA-1 2026-09-11] 감시가 한국어 조사에 소수점을 잘랐다 ────────────────
#   🔴 운영 경보 실측 2026-09-11 — `W-FACT-MISMATCH` 8건을 전수 확인했더니
#      **8건 모두 판정이 옳고 감시가 틀렸다.**
#
#      elo 5건: `\b(1\d{3}(?:\.\d+)?)\b` 의 **뒤 `\b`** 가 문제다. 숫자 뒤에
#        한국어 조사(`로`·`으로`)가 붙으면 둘 다 단어문자라 경계가 성립하지
#        않아, 정규식이 **정수까지만** 잡는다.
#          "볼티모어 1489.9로"  → 1489   (경보: 주장 1489.0 vs 원문 1489.9)
#          "홈팀이 1503.3으로"  → 1503
#          "원정이 1501.2로"    → 1501
#        쉼표·괄호가 뒤에 오면(`1509.5,` `1497.4)`) 멀쩡히 잡힌다.
#        경보의 "주장" 값이 **전부 `.0` 으로 끝나는 것**이 증거였다.
#
#   ⚠️ `app/engine/CLAUDE.md`: "이 층의 최대 리스크는 **오탐**이다. 놓치는
#      쪽이 틀리는 쪽보다 낫다." 지금은 오탐이 쏟아져 **진짜 환각이 묻힌다.**

import pytest


@pytest.mark.parametrize("text,want", [
    ("자료12: 실력 레이팅 토론토 1509.5, 볼티모어 1489.9로 토론토가 우세",
     ["1509.5", "1489.9"]),
    ("실력 레이팅에서 홈팀이 1503.3으로 원정팀(1497.4)에 미세 우위",
     ["1503.3", "1497.4"]),
    ("실력 레이팅에서 원정이 1501.2로 홈(1482.2) 대비 우위", ["1501.2", "1482.2"]),
    ("자료12: 실력 레이팅 홈 1480.3 vs 원정 1485.5로 격차 -5.2점", ["1480.3", "1485.5"]),
])
def test_elo_survives_korean_particle(text, want):
    import re

    from app.engine.fact_audit import UNIT_PATTERNS

    pat = next(p for p, unit, _ in UNIT_PATTERNS if unit == "elo")
    assert re.findall(pat, text) == want, f"조사 뒤에서 소수점이 잘렸다: {text!r}"


def test_elo_still_rejects_longer_numbers():
    """⚠️ 반대 위험 — 앵커를 풀었다고 더 긴 숫자의 앞부분을 물면 안 된다."""
    import re

    from app.engine.fact_audit import UNIT_PATTERNS

    pat = next(p for p, unit, _ in UNIT_PATTERNS if unit == "elo")
    assert re.findall(pat, "관중 15095명") == [], "5자리 숫자의 앞 4자리를 물었다"
    assert re.findall(pat, "코드 21489 참조") == [], "숫자 중간을 물었다"


def test_elo_range_unchanged():
    """1000~1999 만 잡는다는 기존 계약은 그대로다."""
    import re

    from app.engine.fact_audit import UNIT_PATTERNS

    pat = next(p for p, unit, _ in UNIT_PATTERNS if unit == "elo")
    assert re.findall(pat, "레이팅 1489.9") == ["1489.9"]
    assert re.findall(pat, "레이팅 2489.9") == []
