"""[1][2] 승률 표기 일관성 — 같은 경기에 확률이 두 개 나오면 읽을 수 없다.

실사고(2026-08-25):
- "승률 조정: 기준 32% → 최종 23%"는 자이언츠 기준인데 마켓 보드는 레즈 77%로 표시
- 판단문은 "모델 레즈 63.2%", 마켓 보드는 "레즈 승 77%" — 같은 팀 확률이 2개
"""

import re

import pytest

from app.engine.markets import grade_candidate
from app.engine.performance import WinProbAdjuster, trace_for
from app.pipeline import (
    DETAIL_SEP,
    allowed_prob_pcts,
    render_game_easy,
    render_game_section,
    scrub_conflicting_probs,
)


def _jg(**over):
    jg = {
        "game_id": 415, "sport": "mlb", "status": "scheduled", "status_label": "",
        "home": "San Francisco Giants", "away": "Cincinnati Reds", "league": "MLB",
        "starts_at_kst": "08/25 10:45", "model_valid": True,
        "p_model": 0.368, "p_market": 0.396, "p_claude": 0.35,
        "market_probs": {"San Francisco Giants": 0.396, "Cincinnati Reds": 0.604},
        "best_odds": {"San Francisco Giants": 2.53, "Cincinnati Reds": 1.61},
        "judge_confidence": "high", "expert_picks": [],
        "stats": {"home_pitcher": "Carson Whisenhunt", "away_pitcher": "Chase Burns"},
        "research": {"home_recent_form": {"form": "LLWLL"},
                     "absences": ["San Francisco Giants의 Matt Chapman 결장"]},
        "verdict": "번스는 시즌 ERA 2.51, WHIP 1.11로 안정적이다.",
        "market_board": [
            {"market": "h2h", "side": "Cincinnati Reds", "line": None,
             "desc": "신시내티 레즈 승", "odds": 1.61, "p": 0.68, "ev": 0.095,
             "axes_kr": "실데이터+전문가", "approved": True, "reject_reason": None},
            {"market": "h2h", "side": "San Francisco Giants", "line": None,
             "desc": "샌프란시스코 자이언츠 승", "odds": 2.53, "p": 0.32, "ev": -0.19,
             "axes_kr": "없음", "approved": False, "reject_reason": "지지 축 없음"},
        ],
        "markets_unpriced": [],
        "prob_adjust": {
            "trace": ["San Francisco Giants 기준 40%", "선발 매치업 -8%p",
                      "최종 San Francisco Giants 32% / Cincinnati Reds 68%"],
            "applied": [{"label": "선발 매치업", "delta": -0.08}],
            "unused": [], "basis": "home", "home": "San Francisco Giants",
            "away": "Cincinnati Reds", "p_home": 0.32, "p_away": 0.68,
            "net_delta": -0.08, "capped": False,
        },
        "pick_summary": {"side": "Cincinnati Reds", "desc": "신시내티 레즈 승",
                         "market": "h2h", "odds": 1.61, "p_final": 0.68, "ev": 0.095,
                         "flags": [], "approved": True, "reject_reason": None,
                         "axes": "실데이터+전문가"},
    }
    jg.update(over)
    for c in jg["market_board"]:
        c["grade"], c["grade_note"] = grade_candidate(c)
    return jg


# ---------------------------------------------------------------- [1] 기준 통일

def test_trace_flips_to_target_team():
    """[1] 조정 과정을 대상팀 기준으로 다시 쓴다 — 상대 승률은 100-대상팀."""
    adj = _jg()["prob_adjust"]
    home_trace = trace_for(adj, "San Francisco Giants")
    away_trace = trace_for(adj, "Cincinnati Reds")
    assert home_trace[0].startswith("San Francisco Giants 기준")
    assert away_trace[0].startswith("Cincinnati Reds 기준 60%")   # 100 - 40
    assert "선발 매치업 +8%p" in away_trace                        # 부호가 뒤집힌다
    assert away_trace[-1].startswith("최종 Cincinnati Reds 68%")


def test_adjustment_trace_matches_board_basis():
    """[1] 회귀: 조정 과정과 마켓 보드가 서로 다른 팀 기준이면 안 된다."""
    out = render_game_section(_jg())
    trace = next(l for l in out.splitlines() if l.startswith("승률 조정:"))
    # 대표 마켓이 레즈이므로 조정 과정도 레즈 기준이어야 한다
    assert "Cincinnati Reds 기준" in trace
    assert "68%" in trace
    board = next(l for l in out.splitlines() if l.startswith("  신시내티 레즈 승"))
    assert "| 68% |" in board


# ---------------------------------------------------------------- [2] 확률 소스 단일화

_TEAM_PCT = re.compile(r"(레즈|자이언츠|Cincinnati Reds|San Francisco Giants)[^.\n]{0,20}?(\d{1,3})\s*%")


def _probs_by_team(text: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    alias = {"레즈": "REDS", "Cincinnati Reds": "REDS",
             "자이언츠": "SFG", "San Francisco Giants": "SFG"}
    for m in _TEAM_PCT.finditer(text):
        out.setdefault(alias[m.group(1)], set()).add(int(m.group(2)))
    return out


def _conclusion_lines(text: str) -> str:
    """결론 확률만 남긴다 — '승률 조정' 줄은 과정 표시라 기준값·중간값이 들어간다.

    [1-2]가 조정 과정 노출을 요구하므로 그 줄은 예외이며, 대신 그 줄의 **최종값**이
    결론과 같은지를 따로 검사한다(test_trace_final_matches_conclusion).
    """
    return "\n".join(l for l in text.splitlines() if not l.startswith("승률 조정:"))


def test_no_team_has_two_different_probabilities():
    """[2] 회귀: 같은 경기·같은 팀의 결론 확률이 출력 안에 2개 이상 등장하면 실패."""
    for renderer in (render_game_easy, render_game_section):
        out = _conclusion_lines(renderer(_jg()))
        for team, values in _probs_by_team(out).items():
            assert len(values) <= 1, (
                f"{renderer.__name__}: {team} 확률이 {sorted(values)}로 여러 개 등장한다")


def test_trace_final_matches_conclusion():
    """[1][2] 조정 과정의 최종값은 마켓 보드·대표 마켓의 확률과 같아야 한다."""
    out = render_game_section(_jg())
    trace = next(l for l in out.splitlines() if l.startswith("승률 조정:"))
    final = re.search(r"최종 Cincinnati Reds (\d{1,3})%", trace)
    assert final and final.group(1) == "68"
    assert "| 68% |" in out                       # 마켓 보드
    assert "승률 68%" in out                       # 대표 마켓 줄


def test_verdict_probabilities_conflicting_with_p_final_are_scrubbed():
    """[2] 판정문이 자기 확률을 다시 쓰면 보드와 충돌한다 — 그 문장을 버린다."""
    jg = _jg(verdict=("모델 레즈 63.2%로 우위. 번스는 ERA 2.51, WHIP 1.11로 안정적이다. "
                      "레즈 승리 확률 68%."))
    out = render_game_section(jg)
    assert "63.2%" not in out and "63%" not in out
    assert "ERA 2.51" in out               # 근거 수치는 남는다
    assert "68%" in out                    # p_final과 일치하는 값은 남는다


def test_scrubber_keeps_non_probability_numbers():
    allowed = {68, 67, 69}
    kept = scrub_conflicting_probs(
        "메식은 ERA 2.54, WHIP 1.03이다. 승률 68%로 우위다.", allowed)
    assert "ERA 2.54" in kept and "68%" in kept
    dropped = scrub_conflicting_probs("모델 홈 45.5%로 계산됐다.", allowed)
    assert dropped == ""


def test_allowed_pcts_come_from_p_final_only():
    """[2] 허용 목록은 마켓 보드 p_final과 조정 결과만 — 시장·모델 확률은 제외."""
    allowed = allowed_prob_pcts(_jg())
    assert 68 in allowed and 32 in allowed
    assert 40 not in allowed        # 시장 39.6% 반올림값은 허용되지 않는다
    assert 37 not in allowed        # 모델 36.8%도 마찬가지


def test_model_and_market_probs_not_printed():
    """[2] 모델·Claude·시장 확률은 p_final의 입력값이지 별도 결론이 아니다."""
    out = render_game_section(_jg())
    assert "시장(참고" not in out and "Claude:" not in out
    assert "모델: 36.8%" not in out


# ---------------------------------------------------------------- [3] 승률 상한

def test_probability_cap_applied_and_labelled():
    """[1] MLB 단일 경기 77%는 비현실적 — 65%로 절사하고 원값을 표기한다."""
    from app.config import Settings

    s = Settings(_env_file=None)
    a = WinProbAdjuster(s)
    jg = {"home": "H", "away": "A"}
    out = a.adjust(0.77, jg, {}, "mlb")
    assert out["p"] == s.prob_cap_mlb == 0.65
    assert out["capped"] is True
    assert any("추정 상한 적용" in x for x in out["trace"])

    # 반대편도 절사된다 (0.23 → 0.35)
    low = a.adjust(0.23, jg, {}, "mlb")
    assert low["p"] == round(1 - s.prob_cap_mlb, 4)

    # 축구는 상한이 더 높다
    soccer = a.adjust(0.80, jg, {}, "soccer")
    assert soccer["p"] == s.prob_cap_soccer == 0.70


def test_no_cap_when_within_range():
    from app.config import Settings

    out = WinProbAdjuster(Settings(_env_file=None)).adjust(0.62, {"home": "H", "away": "A"}, {}, "mlb")
    assert out["capped"] is False and out["p"] == 0.62
    assert not any("상한" in x for x in out["trace"])
