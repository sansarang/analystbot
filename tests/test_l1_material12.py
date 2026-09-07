"""L1 이 자료12(실력 레이팅)도 대조한다 — v1.4 2026-09-07.

🔴 실측 2026-09-06 리허설: 맞는 인용과 **틀린 인용**(홈 1590/원정 1410)이
   둘 다 `verified 0 · mismatch 0` 으로 나왔다. 단위가 없는 숫자는
   `extract_claims` 가 애초에 후보로 뽑지 않았기 때문이다.
   자료12 는 판정의 **기본 축**인데 감시가 붙지 않은 유일한 자료였다.

⚠️ 감시층의 최대 리스크는 오탐이다. 실판정 15건으로 전후를 쟀고
   검증 185 · 불일치 5 가 **한 건도 변하지 않았다**(새 불일치 0건).
"""
from __future__ import annotations

import pytest

from app.engine import fact_audit as FA
from app.engine.matchup import elo_payload, render_matchup_prompt

ELO = {"home": {"레이팅": 1514.4, "리그평균대비": 14.4, "경기수": 23},
       "away": {"레이팅": 1480.0, "리그평균대비": -20.0, "경기수": 25}}


@pytest.fixture
def prompt():
    jg = {"sport": "mlb", "home": "H", "away": "A", "research": {}, "elo": ELO}
    return render_matchup_prompt(
        jg, {"home": [{"runs": 3}], "away": [{"runs": 1}]}, {}, None)


def _audit(line, prompt):
    return FA.audit({"근거": [line], "변수": []}, prompt)


# ── 뽑히는가 ────────────────────────────────────────────────────
def test_rating_and_gap_are_extracted_as_claims():
    claims = FA.extract_claims(
        {"근거": ["자료12: 실력 레이팅 홈 1514.4 vs 원정 1480.0, 격차 34.4점"],
         "변수": []})
    units = sorted({c["unit"] for c in claims})
    assert "elo" in units and "elo_gap" in units
    vals = sorted(c["value"] for c in claims if c["unit"] == "elo")
    assert vals == [1480.0, 1514.4]


def test_correct_citation_verifies(prompt):
    r = _audit("자료12: 실력 레이팅 홈 1514.4 vs 원정 1480.0, 격차 34.4점", prompt)
    assert r["verified_n"] == 3
    assert r["mismatch_n"] == 0


def test_wrong_rating_is_caught(prompt):
    """🔴 어제 못 잡던 바로 그 케이스."""
    r = _audit("자료12: 실력 레이팅 홈 1590.0 vs 원정 1410.0, 격차 34.4점", prompt)
    assert r["mismatch_n"] == 2, r
    d = r["mismatch_detail"][0]
    assert d["unit"] == "elo" and d["claimed"] == 1590.0


def test_wrong_gap_is_caught(prompt):
    r = _audit("자료12: 실력 레이팅 홈 1514.4 vs 원정 1480.0, 격차 180.0점", prompt)
    assert r["mismatch_n"] == 1
    assert r["mismatch_detail"][0]["unit"] == "elo_gap"


# ── 오탐이 안 나는가 ────────────────────────────────────────────
def test_small_numbers_are_not_read_as_ratings():
    """이닝·실점은 한 자리~두 자리다. 레이팅 패턴이 삼켜선 안 된다."""
    claims = FA.extract_claims(
        {"근거": ["자료4: 최근 4등판 26이닝 9실점, 자료1: 3경기 11득점"], "변수": []})
    assert not [c for c in claims if c["unit"].startswith("elo")]


def test_rating_pattern_only_matches_the_elo_range():
    """1000~1999 만 잡는다 — 2026 같은 연도나 900 대 숫자를 삼키지 않는다."""
    claims = FA.extract_claims(
        {"근거": ["2026 시즌 900구 던진 투수, 2500만원"], "변수": []})
    assert not [c for c in claims if c["unit"] == "elo"]


def test_material12_is_in_the_prompt_so_the_pool_is_not_empty(prompt):
    """대조할 원문이 실려 있어야 감시가 성립한다."""
    pay = elo_payload({"elo": ELO})
    assert str(pay["홈"]["레이팅"]) in prompt
    assert str(pay["격차"]) in prompt
