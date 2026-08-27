"""[§9 2단] 해석봇 — 정보 차단벽이 이 설계의 전부다.

한 번에 시키면 LLM은 **먼저 결론을 세우고 칸을 거기 맞춘다.** 프롬프트로는
못 막는다. 2단이 상대를 모르게 만드는 것이 유일한 방어다.
"""

import asyncio

import pytest

from app.config import Settings
from app.engine import interpreter as I
from app.engine.card import build_card

JG = {"game_id": 1, "home": "Kia Tigers", "away": "Lotte Giants"}

RESEARCH = {
    "home_usage": {"last_game_date": "2026-08-26", "pitchers_used_last": 9,
                   "relief_ip_last": 6.33, "relief_batters_last": 37,
                   "relief_ip_l3": 13.33, "relief_batters_l3": 69, "window_games": 3,
                   "back_to_back": ["김범수", "성영탁", "정해영"], "back_to_back_count": 3,
                   "score_games": 3, "results_l3": "WWL", "runs_l3": 31,
                   "runs_allowed_l3": 24, "runs_per_game_l3": 10.33},
    "home_pitcher": {"name": "양현종", "throws": "L", "era_season": 4.19,
                     "whip": 1.44, "ip_avg_recent": 4.81},
    "home_offense": {"ops": 0.792},
    "home_standing": {"rank": 4, "w": 62, "l": 50, "d": 2, "games_behind": 5.5,
                      "games_behind_cut": -2.0, "remaining": 30},
    "away_usage": {"last_game_date": "2026-08-26", "pitchers_used_last": 6,
                   "relief_ip_last": 4.33, "relief_batters_last": 25,
                   "relief_ip_l3": 9.33, "relief_batters_l3": 47, "window_games": 3,
                   "back_to_back": [], "back_to_back_count": 0,
                   "score_games": 3, "results_l3": "LLL", "runs_l3": 17,
                   "runs_allowed_l3": 27, "runs_per_game_l3": 5.67},
    "away_pitcher": {"name": "나균안", "throws": "R", "era_season": 4.00,
                     "whip": 1.43, "ip_avg_recent": 5.73},
    "away_offense": {"ops": 0.727},
    "away_standing": {"rank": 6, "w": 50, "l": 60, "d": 2, "games_behind": 16.5,
                      "games_behind_cut": 9.0, "remaining": 32},
}


# ---------------------------------------------------------------- 🔴 차단벽

def test_payload_contains_nothing_about_the_opponent():
    """🔴 이 설계의 전부 — 2단은 상대가 누군지 모른다.

    하나라도 새면 LLM이 결론을 세우고 칸을 거기 맞춘다.
    """
    card = build_card(JG, RESEARCH)
    payload = I.build_payload(card["home"], "KIA")
    dump = str(payload)

    # 상대 팀 이름·선수·수치가 한 조각도 없어야 한다
    for leaked in ("Lotte", "롯데", "나균안", "5.73", "0.727", "LLL", "16.5"):
        assert leaked not in dump, f"상대 정보가 샜다: {leaked}"
    # 자기 팀 사실은 있어야 한다
    assert "KIA" in dump and "양현종" in dump and "37" in dump


def test_payload_carries_no_outcome_signals():
    """🔴 승패·확률·배당을 보면 2단이 결론부터 세운다."""
    card = build_card(JG, RESEARCH)
    dump = str(I.build_payload(card["home"], "KIA"))
    for banned in ("p_final", "p_model", "p_claude", "odds", "배당", "승률",
                   "확률", "distribution", "lam", "ev", "recommended"):
        assert banned not in dump, f"승패 관련 데이터가 샜다: {banned}"


def test_payload_shape_is_facts_only():
    """입력은 사실 문자열 목록뿐 — 사실을 수정할 경로가 구조적으로 없다."""
    card = build_card(JG, RESEARCH)
    p = I.build_payload(card["home"], "KIA")
    assert set(p) == {"team", "cells"}
    for c in p["cells"]:
        assert set(c) == {"key", "label", "facts"}
        assert all(isinstance(f, str) for f in c["facts"])


def test_system_prompt_forbids_outcome_judgement():
    for must in ("상대가 누구인지 모른다", "이긴다/진다", "인용", "="):
        assert must in I.SYSTEM, f"시스템 프롬프트에 '{must}' 규율이 없다"


# ---------------------------------------------------------------- 인용 강제

def test_citation_requires_a_specific_token():
    facts = ["직전 경기(2026-08-26) 투수 9명 투입 · 구원 6.33이닝 37타자 상대"]
    assert I.cites_facts("직전 경기에 투수 9명·37타자를 썼다 — 뒷문이 얇다", facts)
    assert I.cites_facts("구원 6.33이닝은 과한 소모다", facts)
    # 🔴 근거 없는 인상평은 통과하면 안 된다
    assert not I.cites_facts("컨디션이 좋아 보인다", facts)
    assert not I.cites_facts("최근 경기 흐름이 나쁘다", facts), "흔한 말만으로 통과했다"


def test_citation_needs_facts():
    assert not I.cites_facts("뭐라도 썼다", [])
    assert not I.cites_facts("", ["직전 9명"])


# ---------------------------------------------------------------- 배칭·폐기

class _Fake:
    """provider 대신 — 한 콜에 다섯 칸이 오는지, 폐기가 되는지 본다."""

    def __init__(self, cells):
        self.cells, self.calls, self.seen = cells, 0, []

    async def __call__(self, role, messages, **kw):
        self.calls += 1
        self.seen.append(messages[0]["content"])

        class R:
            data = {"cells": self.cells}
            label = "mock/none"
        return R()


def _run(monkeypatch, cells, side="home", team="KIA"):
    fake = _Fake(cells)
    monkeypatch.setattr(I, "complete", fake)
    monkeypatch.setattr(I, "role_enabled", lambda *a, **k: True)
    card = build_card(JG, RESEARCH)
    out = asyncio.run(I.interpret_side(card[side], team))
    return out, fake


def test_all_cells_go_in_one_call(monkeypatch):
    """🔴 배칭 — 칸마다 부르면 비용이 5배다(150콜 → 30콜)."""
    cells = [{"key": k, "symbol": "=", "reason": "양현종 ERA 4.19 기준 평이"}
             for k, _ in __import__("app.engine.card", fromlist=["CELLS"]).CELLS]
    out, fake = _run(monkeypatch, cells)
    assert fake.calls == 1, f"{fake.calls}콜 — 팀당 1콜이어야 한다"


def test_uncited_cells_are_dropped(monkeypatch):
    """🔴 근거 없는 부호는 3단에서 사실처럼 읽힌다 — 여기서 버려야 한다."""
    cells = [
        {"key": "bullpen", "symbol": "▼", "reason": "직전 9명·37타자로 소모가 크다"},
        {"key": "starter", "symbol": "▲", "reason": "컨디션이 좋아 보인다"},
    ]
    out, _ = _run(monkeypatch, cells)
    assert "bullpen" in out and out["bullpen"]["symbol"] == "▼"
    assert "starter" not in out, "인용 없는 칸이 살아남았다"


def test_unknown_key_and_symbol_are_ignored(monkeypatch):
    cells = [{"key": "존재하지않는칸", "symbol": "▲", "reason": "37타자"},
             {"key": "bullpen", "symbol": "↑", "reason": "37타자"}]
    out, _ = _run(monkeypatch, cells)
    assert out == {}


def test_disabled_role_returns_empty_not_mock(monkeypatch):
    """🔴 목 판정이 실판정으로 오인되면 안 된다."""
    monkeypatch.setattr(I, "role_enabled", lambda *a, **k: False)
    card = build_card(JG, RESEARCH)
    assert asyncio.run(I.interpret_side(card["home"], "KIA")) == {}


# ---------------------------------------------------------------- 무게 칸 규칙

def _st(gb, gc):
    return {"games_behind": gb, "games_behind_cut": gc}


def test_out_of_contention_needs_both_gaps():
    """🔴 선두 게임차만 보면 안 된다.

    실측(2026-08-27): 한화는 선두와 16.5G지만 5위와 9.0G — 잔여 33경기에
    수학적으로 살아 있다. 여기서 경쟁권 밖이라 하면 없는 사실을 만드는 것이다.
    """
    s = Settings(anthropic_api_key="k")
    assert I.out_of_contention(_st(20.0, 12.5), s) is True     # SSG
    assert I.out_of_contention(_st(16.5, 9.0), s) is False     # 한화 — 컷과 9G
    assert I.out_of_contention(_st(16.5, -2.0), s) is False    # 선두와 멀어도 컷 위
    assert I.out_of_contention({}, s) is False, "모르면 단정하지 않는다"


def test_both_out_of_contention_forces_equal():
    """🔴 순위가 높은 쪽에 ▲를 주면 **없는 동기 차이를 만드는 것**이다."""
    home = {"weight": {"symbol": "▲", "reason": "9위"}}
    away = {"weight": {"symbol": "▼", "reason": "10위"}}
    research = {"home_standing": _st(20.0, 12.5), "away_standing": _st(27.0, 19.5)}
    note = I.apply_weight_rule(home, away, research)
    assert note and "경쟁권 밖" in note
    assert home["weight"]["symbol"] == "=" and away["weight"]["symbol"] == "="
    assert home["weight"]["rule"] == "양쪽 무의미"


def test_one_side_contending_keeps_the_symbols():
    home = {"weight": {"symbol": "▲", "reason": "4위"}}
    away = {"weight": {"symbol": "▼", "reason": "9위"}}
    research = {"home_standing": _st(5.5, -2.0), "away_standing": _st(20.0, 12.5)}
    assert I.apply_weight_rule(home, away, research) is None
    assert home["weight"]["symbol"] == "▲"


def test_threshold_is_config_driven_not_hardcoded():
    """문턱은 아직 실측되지 않았다 — 채점 데이터로 교체할 수 있어야 한다."""
    loose = Settings(anthropic_api_key="k", contention_gb=8.0)
    assert I.out_of_contention(_st(16.5, 9.0), loose) is True, \
        "config로 문턱을 낮췄는데 반영되지 않았다"


# ---------------------------------------------------------------- 🔴 방향 오독

# 실사고(2026-08-27): KIA 불펜 사실은 "직전 9명 투입 · 구원 37타자 · 연투 3명"
# (= 명백한 과소모)인데 모델이 "사용량이 적어 유리" ▲로 읽었다.
# **숫자는 인용했으므로 인용 강제를 통과했다.**
KIA_BULLPEN = {"relief_batters_l3": 69.0, "back_to_back_count": 3.0,
               "pitchers_used_last": 9.0}
def _band(q1, med, q3):
    return {"q1": q1, "median": med, "q3": q3}


# ⚠️ 기준선은 중앙값 하나가 아니라 **사분위 구간**이다.
#    사분위 안(=평소)은 표를 던지지 않는다 — OPS 0.760 vs 0.756 같은
#    오차 범위가 "방향 오독"으로 폐기된 실사고(2026-08-27) 때문이다.
LEAGUE = {"relief_batters_l3": _band(38.0, 43.0, 48.0),
          "back_to_back_count": _band(0.0, 0.0, 1.0),
          "pitchers_used_last": _band(4.0, 5.0, 6.0),
          "era_season": _band(3.9, 4.4, 4.9),
          "whip": _band(1.30, 1.44, 1.58),
          "ip_avg_recent": _band(4.3, 4.8, 5.3),
          "ops": _band(0.720, 0.752, 0.784),
          "run_diff_l3": _band(-3.0, 0.0, 3.0),
          "runs_per_game_l3": _band(3.7, 4.5, 5.3),
          "games_behind_cut": _band(0.0, 0.0, 3.0)}


def test_kia_bullpen_misread_is_caught():
    """🔴 회귀 핵심 — 인용 강제로는 못 막는 유형이다.

    인용 강제는 *지어내기*를 막지, 그 숫자를 *어떻게 읽는지*는 못 막는다.
    """
    why = I.direction_check("bullpen", KIA_BULLPEN, LEAGUE, "▲")
    assert why and "불리를 가리킨다" in why
    assert "relief_batters_l3 69" in why, "근거 수치가 사유에 없다"
    # 같은 사실에 ▼는 정상이다
    assert I.direction_check("bullpen", KIA_BULLPEN, LEAGUE, "▼") is None


def test_equal_is_never_a_misread():
    """`=`는 판단 보류이지 반대가 아니다 — 오독으로 세면 정상 판정을 버린다."""
    assert I.direction_check("bullpen", KIA_BULLPEN, LEAGUE, "=") is None


def test_no_baseline_means_no_verdict():
    """🔴 못 재는 것을 틀렸다고 하면 정상 판정을 버린다(반대 방향 위험)."""
    assert I.direction_check("bullpen", KIA_BULLPEN, {}, "▲") is None
    assert I.direction_check("bullpen", {}, LEAGUE, "▲") is None


def test_mixed_metrics_are_left_alone():
    """지표가 갈리면 사람도 애매한 칸이다 — 기계가 단정하지 않는다."""
    mixed = {"era_season": 3.0, "whip": 1.44, "ip_avg_recent": 3.0}  # ERA 좋고 이닝 짧다
    assert I.direction_check("starter", mixed, LEAGUE, "▲") is None
    assert I.direction_check("starter", mixed, LEAGUE, "▼") is None


def test_direction_rules_are_in_the_prompt():
    """프롬프트만으로는 재발하지만, 없으면 더 자주 난다."""
    for must in ("많을수록 ▼", "낮을수록 ▲", "높을수록 ▲", "방향을 반대로 읽는"):
        assert must in I.SYSTEM, f"방향 규칙 '{must}'이 프롬프트에 없다"


def test_misread_cell_is_dropped_with_its_own_reason(monkeypatch):
    """폐기 사유를 구분한다 — 지어내기와 오독은 대응이 다르다."""
    cells = [{"key": "bullpen", "symbol": "▲",
              "reason": "구원 69타자·연투 3명이라 여유롭다"}]
    fake = _Fake(cells)
    monkeypatch.setattr(I, "complete", fake)
    monkeypatch.setattr(I, "role_enabled", lambda *a, **k: True)
    card = build_card(JG, RESEARCH)
    out = asyncio.run(I.interpret_side(card["home"], "KIA", baselines=LEAGUE))
    assert "bullpen" not in out, "방향 오독이 살아남았다"


def test_league_baseline_uses_median_not_mean():
    """🔴 한 팀의 이상치가 기준선을 밀면 나머지 팀 판정이 전부 틀어진다.

    실제로 한화 선발 ERA 13.5 같은 값이 있다.
    """
    from app.engine.card import league_baselines

    sides = [({"home_pitcher": {"era_season": e}}, "home")
             for e in (3.5, 4.0, 4.2, 4.5, 13.5)]
    base = league_baselines(sides)
    assert base["era_season"]["median"] == 4.2, f"중앙값이 아니다: {base['era_season']}"
    # 이상치 13.5는 상위 사분위 **밖**으로 밀려나야 한다 — 구간을 넓히면 안 된다
    assert base["era_season"]["q3"] < 13.5


def test_inside_the_quartile_band_is_not_a_misread():
    """🔴 오차 범위를 오독으로 잡으면 가드가 정상 판정을 버린다.

    실사고 2026-08-27: OPS 0.760 vs 기준 0.756(0.004 차이)이 "방향 오독"으로
    폐기됐다. 한 방향만 고치면 반대편에서 새 오류가 난다.
    """
    near = {"ops": 0.760}          # 사분위 0.720~0.784 한복판
    assert I.direction_check("batting", near, LEAGUE, "▼") is None
    assert I.direction_check("batting", near, LEAGUE, "▲") is None


def test_outside_the_band_still_gets_caught():
    """다만 구간 **밖**이면 여전히 잡아야 한다 — 완화가 아니라 정밀화다."""
    clear = {"ops": 0.850}          # 상위 사분위 0.784 밖
    assert I.direction_check("batting", clear, LEAGUE, "▼")
    assert I.direction_check("batting", clear, LEAGUE, "▲") is None
