"""[C2] 변수 정량 형식 — 파싱·예산·표기.

🔴 §3 은 **변수 출력 명세만** 여는 동결 예외다. 프롬프트의 다른 문장은
   한 줄도 바뀌지 않았음을 이 파일이 함께 잠근다.
"""
import pytest

from app.engine.prompts import MATCHUP
from app.engine.variable_parse import check_budget, parse_all, parse_variable

GOOD = ("원정 선발 이로운 3이닝 미만 조기 강판 — 발생 시 홈 방향 약 8%p · "
        "현재 p에 3%p 기반영 · 근거 자료10")


def test_parses_the_specified_format():
    p = parse_variable(GOOD)
    assert p == {"risk": "원정 선발 이로운 3이닝 미만 조기 강판", "side": "home",
                 "n": 8.0, "m": 3.0, "source": "자료10"}


def test_away_direction_and_decimals():
    p = parse_variable("타선 침체 지속 — 발생 시 원정 방향 약 4.5%p · "
                       "현재 p에 1.5%p 기반영 · 근거 자료1,자료10")
    assert p["side"] == "away" and p["n"] == 4.5 and p["m"] == 1.5
    assert p["source"] == "자료1,자료10"


def test_no_reference_variant_still_parses():
    """"근거 없음 — 보수 반영" 도 형식 안에 있어야 파싱된다."""
    p = parse_variable("불펜 과부하 — 발생 시 원정 방향 약 5%p · "
                       "현재 p에 2%p 기반영 · 근거 없음 — 보수 반영")
    assert p is not None and p["m"] == 2.0
    assert "없음" in p["source"]


def test_narrative_variable_fails_to_parse_and_is_logged(caplog):
    """🔴 종전 서술형은 **정량 실패로 남는다** — 조용히 통과시키지 않는다."""
    old = "원정 선발 이로운은 선발등판 기록이 0건이라 이닝 소화력 예측 불가"
    assert parse_variable(old) is None
    with caplog.at_level("INFO"):
        rows = parse_all({"변수": [old]})
    assert rows[0]["parsed"] is None and rows[0]["raw"] == old
    assert any("형식 위반" in r.getMessage() for r in caplog.records)


def test_budget_rule_two():
    """② M 합 ≤ |p−0.50|."""
    v = {"p_home": 0.60, "변수": [GOOD]}
    r = check_budget(v)
    assert r["budget"] == 10.0 and r["sum_m"] == 3.0 and r["ok"] is True


def test_budget_violation_warns_but_does_not_reject(caplog):
    """🔴 **판정을 막지 않는다.** 감시가 발송을 멈추면 안 된다."""
    big = ("리스크 — 발생 시 홈 방향 약 20%p · 현재 p에 15%p 기반영 · 근거 자료10")
    with caplog.at_level("WARNING"):
        r = check_budget({"p_home": 0.55, "변수": [big]})
    assert r["ok"] is False and r["sum_m"] == 15.0 and r["budget"] == 5.0
    assert any("규칙② 위반" in x.getMessage() for x in caplog.records)
    # 반환만 할 뿐 예외를 던지지 않는다
    assert isinstance(r, dict)


def test_budget_without_p_home_is_not_judged():
    r = check_budget({"변수": [GOOD]})
    assert r["budget"] is None and r["ok"] is True


# ═════════ 프롬프트 — §3 블록만 열렸는가 ═════════

def test_prompt_has_the_variable_spec():
    assert "[변수 형식]" in MATCHUP
    assert "발생 시 <홈|원정> 방향 약 N%p" in MATCHUP
    assert "현재 p에 M%p 기반영" in MATCHUP
    assert "근거 <자료 번호>" in MATCHUP


def test_prompt_has_the_three_rules():
    assert "근거 없음 — 보수 반영" in MATCHUP          # ①
    assert "M 의 합은 |p_home − 0.50| 이내" in MATCHUP  # ②
    assert "변수로 우세를 뒤집지 않는다" in MATCHUP      # ③


def test_frozen_sentences_are_untouched():
    """§3 밖 문장은 그대로다 — diff 가 이 블록을 넘으면 반려다."""
    for kept in ("p_home은 0.32~0.68 범위를 벗어나지 않는다",
                 "근거는 위 자료 안에서만 찾는다",
                 "{{BOXSCORE_JSON}}", "{{BULLPEN_JSON}}"):
        assert kept in MATCHUP, kept
    # [C2 2026-09-04] 자료7·8 은 대원칙에 따라 폐지됐다 — 동결 목록에서 뺀다.
    for gone in ("{{LINEUP_SEASON_JSON}}", "{{STARTER_SEASON_JSON}}"):
        assert gone not in MATCHUP, gone


def test_card_emits_the_variable_verbatim():
    """렌더는 **발명하지 않는다** — 문자열을 그대로 낸다."""
    from pathlib import Path

    src = Path("app/engine/form_card.py").read_text(encoding="utf-8")
    assert 'lines.append(f"변수 {v}")' in src


# ═════════ §5 표본 재시작 ═════════

def test_sample_restarts_for_all_three_leagues():
    """자료10·변수 명세는 **판정 입력 변경**이다 — 표본을 섞지 않는다."""
    from app.engine.daily_summary import (
        FREEZE_RESTART_IS_FINAL, FREEZE_RESTART_REASON, freeze_start,
    )

    assert freeze_start("kbo") == freeze_start("npb") == freeze_start("mlb")
    assert freeze_start("kbo") == "2026-09-04"
    assert "변수 정량화" in FREEZE_RESTART_REASON
    # 🔴 이 재시작이 마지막이다 — 재료를 바꿀 때마다 버리면 50건에 영영 못 간다
    assert FREEZE_RESTART_IS_FINAL is True


@pytest.mark.asyncio
async def test_summary_states_the_restart_reason():
    """숫자가 왜 0 부터인지 **묻기 전에** 답한다."""
    from app.engine.daily_summary import freeze_progress_lines

    class Pool:
        async def fetch(self, sql, *a):
            return [{"sport": "kbo", "n": 2}]

    lines = await freeze_progress_lines(Pool(), ("kbo",))
    assert any("표본 재시작" in x and "변수 정량화" in x for x in lines), lines
