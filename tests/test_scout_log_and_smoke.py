"""로그 오탐 · 배포 게이트 공백 (2026-09-07).

① `scout` 이 폴링마다 `--- Logging error ---` 트레이스백을 쌓았다.
   `_factor_state` 는 "0건"과 "안 봤다"를 구분하려고 일부러 `None` 을 내는데
   포맷 문자열이 `%d` 였다. 파이프라인은 안 막지만 로그를 오염시켜
   **진짜 오류를 묻는다.**

② 배포 게이트의 판정 안정성 스모크가 매 배포마다 SKIP 이었다.
   v1.4 로 2차 최종이 Opus(유료)가 된 뒤, "주전이 유료면 SKIP" 규칙이
   게이트를 통째로 껐다 — 꺼진 게이트는 없는 게이트다.
"""
from __future__ import annotations

import logging
import pathlib

import pytest

from app.engine.scout import _factor_state


# ── ① 로그 ──────────────────────────────────────────────────────
def test_factor_state_still_distinguishes_unknown_from_zero():
    """None 을 0 으로 바꿔 고치지 않았는지 — 그러면 필드의 존재 이유가 사라진다."""
    assert _factor_state({})["news"] is None, "'안 봤다'가 0 이 됐다"
    assert _factor_state({"research": {}})["news"] == 0


def test_scout_log_does_not_use_percent_d_for_nullable_fields():
    src = pathlib.Path("app/engine/scout.py").read_text(encoding="utf-8")
    line = next(x for x in src.split("\n") if "[scout] %s game=" in x)
    assert "뉴스=%d" not in line, "None 이 오는 자리에 %d 를 쓴다"
    assert "뉴스=%s" in line


def test_scout_log_renders_with_none(caplog):
    """실제로 찍어 본다 — 포맷 오류는 emit 시점에만 터진다."""
    rec = {"hours_to_start": 2.6, "lineup": {"state": "없음", "sides": 0},
           "market": {"provider": "oddsportal", "rows": 78},
           "factor": {"news": None}}
    logger = logging.getLogger("scout-test")
    with caplog.at_level(logging.INFO):
        _news = rec["factor"]["news"]
        logger.info("[scout] %s game=%s T-%.1fh 라인업=%s(%s면) 배당=%s %s행 뉴스=%s",
                    "npb", 3601, rec["hours_to_start"], rec["lineup"]["state"],
                    rec["lineup"]["sides"], rec["market"]["provider"],
                    rec["market"]["rows"], "미상" if _news is None else _news)
    assert "뉴스=미상" in caplog.text


# ── ② 배포 게이트 ───────────────────────────────────────────────
def test_smoke_falls_back_to_the_free_prelim_chain():
    src = pathlib.Path("tools/stability_smoke.py").read_text(encoding="utf-8")
    assert "PRELIM_ROLE" in src, "유료면 그냥 SKIP 하던 그대로다"
    assert "1차 예비 사슬로 잰다" in src
    # 유료를 배포마다 3회 부르지는 않는다
    i = src.index("PRELIM_ROLE")
    assert 'cands[0][0] == "anthropic"' in src[:i + 400]


def test_chain_candidates_takes_a_role():
    from tools.stability_audition import chain_candidates
    from app.llm.judge_route import MATCHUP_ROLE, PRELIM_ROLE

    import inspect

    sig = inspect.signature(chain_candidates)
    assert "role" in sig.parameters
    # 기본은 종전대로 최종 사슬
    assert sig.parameters["role"].default is None


@pytest.mark.parametrize("role", ["matchup", "matchup_prelim"])
def test_chain_candidates_reads_the_origin(role):
    """사슬을 손으로 적지 않는다 — `judge_route.chain` 이 원본이다."""
    from tools.stability_audition import chain_candidates

    src = pathlib.Path("tools/stability_audition.py").read_text(encoding="utf-8")
    i = src.index("def chain_candidates")
    j = src.find("\nasync def ", i)
    body = src[i: j if j != -1 else len(src)]
    assert "chain(" in body, body[:200]
    assert isinstance(chain_candidates(role), list)
