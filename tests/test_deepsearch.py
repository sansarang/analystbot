"""[v1.1 6단계] 트리거형 딥서치 — 발동 조건과 상한.

최고위험 단계다(비용·외부 의존). 그래서 **상한을 프롬프트가 아니라 코드가
강제하는지**가 가장 중요한 테스트다 — 모델이 규칙을 어겨도 값이 새어
나가지 않아야 한다.
"""

from pathlib import Path

import pytest

from app.config import Settings
from app.engine.deepsearch import (
    ADJUST_CAP_PP, SEARCH_LANG, T1_BOUNDARY, T2_MARKET, T3_ASKED, T4_STARTER,
    T5_LINEUP, apply_findings, clamp_adjustment, daily_cap, lineup_anomaly,
    triggers,
)

S = Settings(_env_file=None)


def _jg(**kw):
    base = {"sport": "kbo", "p_claude": 0.50, "home": "H", "away": "A",
            "matchup": {"p_home": 0.50, "우세": "home"}}
    m = kw.pop("matchup", None)
    base.update(kw)
    if m:
        base["matchup"] = {**base["matchup"], **m}
    return base


# ---------------------------------------------------------------- 트리거 5종

def test_t1_boundary_only_near_threshold():
    """게이트 임계 ±3%p 안이면 경계 경기다. 멀면 발동하지 않는다."""
    assert T1_BOUNDARY in triggers(_jg(p_claude=0.58), S)      # 임계 정확히
    assert T1_BOUNDARY in triggers(_jg(p_claude=0.60), S)      # +2%p
    assert T1_BOUNDARY not in triggers(_jg(p_claude=0.66), S)  # +8%p — 여유


def test_t1_uses_away_premium():
    """원정은 임계가 63%다 — 홈 기준으로 재면 엉뚱한 경기가 걸린다."""
    jg = _jg(p_claude=0.36, matchup={"우세": "away"})   # 원정 64%
    assert T1_BOUNDARY in triggers(jg, S)


def test_t2_fires_on_edge_or_divergence():
    assert T2_MARKET in triggers(_jg(edge_status="candidate"), S)
    assert T2_MARKET in triggers(_jg(market_divergence=True), S)
    assert T2_MARKET not in triggers(_jg(edge_status="none"), S)


def test_t3_fires_when_judgement_asked():
    assert T3_ASKED in triggers(_jg(matchup={"추가확인": ["선발 등판 간격"]}), S)
    assert T3_ASKED not in triggers(_jg(matchup={"추가확인": []}), S)
    assert T3_ASKED not in triggers(_jg(matchup={"추가확인": ["  "]}), S)


def test_t4_fires_on_starter_change():
    jg = _jg(matchup={"직전대비": {"변경입력": ["홈 선발 안우진으로 변경"]}})
    assert T4_STARTER in triggers(jg, S)
    jg2 = _jg(matchup={"직전대비": {"변경입력": ["타순 3번 교체"]}})
    assert T4_STARTER not in triggers(jg2, S)


def test_t5_fires_on_two_starter_swaps():
    """🔴 숫자가 경계에 안 걸려도 라인업 이상 자체가 조사 사유다."""
    prev = {"lineup_home": "가-나-다-라-마-바-사-아-자"}
    jg = _jg(p_claude=0.66, lineup_home="가-나-다-라-마-바-사-차-카")  # 2명 교체
    assert T5_LINEUP in triggers(jg, S, prev_lineup=prev)
    assert lineup_anomaly(jg, prev) is True


def test_t5_ignores_single_swap():
    prev = {"lineup_home": "가-나-다-라-마-바-사-아-자"}
    jg = _jg(lineup_home="가-나-다-라-마-바-사-아-차")   # 1명만
    assert lineup_anomaly(jg, prev) is False


def test_t5_fires_when_form_key_player_is_absent():
    """폼 평가서가 근거로 삼은 선수가 빠지면 그 판정의 토대가 무너진다."""
    jg = _jg(p_claude=0.66,
             lineup_home="김핵심-나-다-라-마-바-사-아-자",
             research={"home_form": {"종합": "김핵심이 타선을 이끌고 있다"}},
             home_lineup={"결장": ["김핵심"]})
    assert lineup_anomaly(jg) is True


def test_no_trigger_means_no_investigation():
    """편안한 확률·이상 없음 → 발동하지 않는다. 상시 검색 금지."""
    assert triggers(_jg(p_claude=0.66), S) == []


# ---------------------------------------------------------------- 상한

def test_daily_cap_is_share_of_slate():
    assert daily_cap(15, S) == 4          # 30%
    assert daily_cap(0, S) == 0


def test_daily_cap_allows_at_least_one():
    """3경기 슬레이트에서 0.9 → 0이면 경계 경기가 있어도 손을 놓게 된다."""
    assert daily_cap(3, S) == 1
    assert daily_cap(1, S) == 1


def test_adjustment_is_capped_at_4pp():
    """🔴 프롬프트가 아니라 코드가 강제한다."""
    p, note = clamp_adjustment(0.60, 0.75, "home")
    assert p == pytest.approx(0.64)
    assert f"±{ADJUST_CAP_PP:g}%p" in note
    p2, _ = clamp_adjustment(0.60, 0.40, "home")
    assert p2 == pytest.approx(0.56)


def test_adjustment_within_cap_passes_through():
    p, note = clamp_adjustment(0.60, 0.62, "home")
    assert p == pytest.approx(0.62) and note is None


def test_direction_cannot_be_flipped_by_search_alone():
    p, note = clamp_adjustment(0.52, 0.48, "home")
    assert p == 0.5 and "뒤집기 금지" in note
    p2, note2 = clamp_adjustment(0.48, 0.52, "away")
    assert p2 == 0.5 and "뒤집기 금지" in note2


def test_single_article_halves_the_adjustment():
    """소스 규칙 ②를 코드로도 집행한다 — 프롬프트만으로는 지켜졌는지 모른다."""
    jg = _jg(p_claude=0.60)
    out = apply_findings(jg, {"조정": {"p_home": 0.64, "단일기사여부": True},
                              "요약": "s"})
    assert jg["p_claude"] == pytest.approx(0.62), "단일 기사인데 전액 반영됐다"
    assert out["moved"] == pytest.approx(2.0)


def test_no_adjustment_leaves_probability_alone():
    jg = _jg(p_claude=0.60)
    apply_findings(jg, {"조정": {}, "요약": "새 사실 없음"})
    assert jg["p_claude"] == 0.60


def test_card_line_is_added():
    jg = _jg(p_claude=0.60)
    apply_findings(jg, {"조정": {"p_home": 0.61}, "요약": "선발 복귀 확인"})
    assert any("🔍 추가 조사 반영" in c for c in jg["breaking_changes"])


# ---------------------------------------------------------------- 언어·규칙

def test_search_language_per_sport():
    """영어로만 찾으면 KBO 구단 공지·NPB 스포츠지가 통째로 빠진다."""
    assert SEARCH_LANG["kbo"] == "한국어"
    assert SEARCH_LANG["npb"] == "일본어"
    assert SEARCH_LANG["mlb"] == SEARCH_LANG["soccer"] == "영어"


def test_prompt_carries_source_rules_and_status():
    from app.engine.deepsearch import PROMPT

    assert "뉴스만으로 조사를 끝내지 않는다" in PROMPT
    assert "단일 기사 하나뿐이면 조정 폭을 절반으로" in PROMPT
    assert "루머·익명 소스·커뮤니티발" in PROMPT
    assert "크롤 정형 데이터보다 낮은 신뢰 등급" in PROMPT
    assert "±4%p" in PROMPT


def test_search_count_is_capped_by_api_not_just_prompt():
    """max_uses 로 API가 강제한다 — 모델의 자제에 기대지 않는다."""
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert '"max_uses": int(s.deepsearch_max_searches)' in src
    assert "web_search_20260318" in src


def test_credit_guard_applies_to_this_path():
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert "abort_if_credit_gone" in src and "trip_credit" in src


def test_prompt_output_asks_for_additional_checks():
    from app.engine.prompts import MATCHUP

    assert '"추가확인"' in MATCHUP
    assert "외부에서 확인 가능한 정보라면" in MATCHUP
