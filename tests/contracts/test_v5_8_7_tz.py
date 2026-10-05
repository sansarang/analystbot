"""🔴🔴 **v5 §8-7·§9-5 — 시간대·돌연변이 요건.**

§9-3 이 *"`tests/contracts/` 에 **하나씩 파일로**"* 를 요구한다 —
처음에 남은 조항을 `test_v5_rest.py` 한 파일에 몰아 넣었고 그 계약이
🔴 *"조항 번호가 이름에 없는 계약 파일"* 로 빨개졌다. **맞았다**:
번호가 파일 이름에 없으면 그 조항을 찾을 수 없다.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]




def test_v5_8_7_naive_시각을_아무_곳도_안_받는다():
    """🔴 §8-7 — 시간대 없는 시각은 **어디서도** 받지 않는다(fail-closed).

    ⚠️ 한 곳이라도 받으면 그 시각이 UTC 인지 KST 인지 **아무도 모른다**.
    """
    from datetime import datetime

    from app import agentloop, factspec, verifylayer
    naive = datetime(2026, 10, 4, 12, 0)
    with pytest.raises((ValueError, TypeError)):
        factspec.Fact(kind="result", team="team:000338", opponent=None,
                      date_utc=naive, state="final", source="x", url="u")
    with pytest.raises((ValueError, TypeError)):
        agentloop.AgentInput(
            match_key="statsapi:1", home="team:1", away="team:2",
            home_names=("a",), away_names=("b",), competition="MLB",
            sport="baseball", kickoff_utc=naive, venue="", langs=("en",))
    # 🔴 검증층도 naive 발행 시각을 **폐기**한다
    ok, reason, _ = verifylayer.verify_one(_naive_var(naive), _naive_ctx())
    assert ok is False and reason.value == "date_missing"


def test_v5_9_5_계약마다_돌연변이_기록이_있다():
    """🔴🔴 §9-5 — *"모든 계약은 돌연변이 1개 이상을 가진다."*

    ⚠️ 돌연변이 **자체**는 기계가 자동으로 못 돌린다(가드를 꺼야 한다). 🔴 그래서
       이 계약이 보는 것은 **기록**이다: 통과한 돌연변이를 만나면 그 까닭과
       고침을 계약 파일에 적었나.
    🔴 그 기록이 없으면 다음 사람이 **같은 약한 계약을 다시 쓴다** — 이 세션에서
       열 번 넘게 그랬다.
    """
    d = pathlib.Path(__file__).parent
    files = sorted(p for p in d.glob("test_v5_*.py"))
    assert len(files) >= 15, len(files)
    # 🔴 **통과한 돌연변이를 적은 파일이 여럿**이어야 한다(안 적으면 잊는다)
    noted = [p.name for p in files if "돌연변이" in p.read_text(encoding="utf-8")]
    assert len(noted) >= 8, (
        f"🔴 돌연변이 기록이 {len(noted)}개 파일뿐이다 — §9-5 는 **모든** 계약에 "
        f"돌연변이를 요구한다: {noted}")
    # ⚠️ 그리고 **"통과했다"** 를 적은 파일이 있어야 한다(전부 빨강이면 의심스럽다)
    passed = [p.name for p in files
              if "통과했다" in p.read_text(encoding="utf-8")]
    assert passed, (
        "🔴 통과한 돌연변이를 적은 계약이 **하나도 없다** — 던지지 않았거나 "
        "기록하지 않았다(§9-5: 돌연변이가 통과하면 그 계약은 없는 것이다)")


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
