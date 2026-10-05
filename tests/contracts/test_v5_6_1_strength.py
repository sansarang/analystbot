"""🔴🔴 **v5 §6-1·§6-7 — 무게는 변수 합·거짓 1.0.**

§9-3 이 *"`tests/contracts/` 에 **하나씩 파일로**"* 를 요구한다 —
처음에 남은 조항을 `test_v5_rest.py` 한 파일에 몰아 넣었고 그 계약이
🔴 *"조항 번호가 이름에 없는 계약 파일"* 로 빨개졌다. **맞았다**:
번호가 파일 이름에 없으면 그 조항을 찾을 수 없다.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]




def test_v5_6_1_무게는_늘_변수_합이다_M20():
    """🔴🔴 *"strength = 변수 weight 합 … 포아송 격자는 … strength 에 닿지 않는다."*

    ⚠️ 실측 2026-10-04: 격자가 strength 를 대신하고 있었고 **변수가 장식**이었다
       (§10-4 M20). 🔴 그래서 생존율이 변수를 따라 움직이지 않았다.
    """
    from app import survive
    drafts = [_draft("A", 2.0), _draft("B", 1.0)]
    w, mode = survive.weights(drafts)
    assert "strength" in mode, mode
    assert w["A"] > w["B"], w
    # 🔴 **격자 확률이 있어도** 무게는 strength 다
    for d in drafts:
        d.probability = 0.5
    w2, mode2 = survive.weights(drafts)
    assert "strength" in mode2, mode2
    assert w2["A"] > w2["B"], w2


def test_v5_6_7_거짓_1_0_의_다섯_조건이_있다_M9():
    """🔴 *"변수 5개 미만, 대량득점형 부재, 양 팀 연속 득점 폼인데 난타전 부재,
    시나리오 4개 미만"* 중 하나면 1.0 을 내지 않는다.

    ⚠️ 코드가 그 조건들을 **각각** 들고 있어야 한다(한 가드가 넷을 대신하면
       무엇이 걸렸는지 모른다).
    """
    import inspect

    from app import survive
    src = inspect.getsource(survive)
    for fn in ("_thin_set_guard", "_scoring_streak_guard"):
        assert fn in src, f"🔴 §6-7 가드 `{fn}` 가 없다"
    from app import scenarios
    assert scenarios.MIN_SCENARIOS == 4
    # 🔴 변수 개수 문턱이 **yaml** 에 있다(코드에 박지 않는다)
    assert survive._thin_set_vars() >= 1


# ══════════════════════════════════════════════════════════════════
# §8-7 · §9-5
# ══════════════════════════════════════════════════════════════════


# ── 대역 ──────────────────────────────────────────────────────────


def _inp():
    from datetime import datetime, timedelta, timezone

    from app import agentloop
    return agentloop.AgentInput(
        match_key="statsapi:849825", home="team:000338", away="team:000325",
        home_names=("Milwaukee Brewers",), away_names=("San Diego Padres",),
        competition="MLB", sport="baseball",
        kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2),
        venue="", langs=("en",))


def _draft(sid: str, strength: float):
    from app import scenarios
    return scenarios.Draft(id=sid, scores=["2-1"], strength=strength,
                           template_id="t", why="w", variables=["V1"],
                           added_by="template")


def _naive_var(when):
    from app import agentschema
    return agentschema.AgentVar(
        id="A1", type="pitcher_state", team="team:000338",
        direction_hint="home", claim="c", quote="Henderson will start",
        url="https://www.mlb.com/x", published_at=when, lang="en")


def _naive_ctx():
    from datetime import datetime, timedelta, timezone

    from app import verifylayer
    return verifylayer.Context(
        home="team:000338", away="team:000325",
        home_names=["Milwaukee Brewers"], away_names=["San Diego Padres"],
        competition="MLB", roster=["Logan Henderson"],
        kickoff=datetime.now(timezone.utc) + timedelta(hours=2),
        bodies={"https://www.mlb.com/x": "Henderson will start on Saturday"})
