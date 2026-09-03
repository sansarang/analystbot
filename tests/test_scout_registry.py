"""[정찰 C0] 종목 정의는 **레지스트리 하나**다.

🔴 이번 주 오탐 4건이 전부 "손으로 적은 사실이 원본과 어긋남"이었다
   (`782a918`). 정찰은 종목이 늘어나는 층이라 같은 병에 가장 취약하다 —
   그래서 종목 문자열을 코드에 다시 적지 못하게 처음부터 잠근다.
"""
import re
from dataclasses import replace
from pathlib import Path

import pytest

from app import registry as R


def test_active_and_inactive_are_separated():
    assert [x.sport for x in R.scout_sports(active_only=True)] == \
        ["kbo", "npb", "mlb"]
    assert "soccer" in [x.sport for x in R.scout_sports()]


def test_soccer_is_off_with_a_written_reason():
    """🔴 이유 없는 비활성은 다음 사람이 그냥 켜 본다."""
    s = R.scout_sport("soccer")
    assert s.active is False
    assert s.reason and "미검증" in s.reason
    # 켜기 전에 무엇이 필요한지도 코드에 남아 있어야 한다
    src = Path("app/registry.py").read_text(encoding="utf-8")
    assert "켜기 전에 필요한 것" in src


def test_odds_provider_is_not_duplicated_in_scout_table():
    """배당 담당은 `ODDS_PROVIDERS` 가 원본 — 정찰 표에 다시 적지 않는다."""
    src = Path("app/registry.py").read_text(encoding="utf-8")
    i = src.index("class ScoutSport")
    seg = src[i:src.index("_SCOUT_BY_SPORT")]
    for banned in ("oddsportal", "espn", "sharp", "betman", "theodds"):
        assert banned not in seg, f"정찰 표가 provider 를 베꼈다: {banned}"
    assert R.odds_provider_for("kbo") == "oddsportal"
    assert R.odds_provider_for("mlb") == "espn"


def test_unknown_sport_is_not_a_scout_target():
    assert R.scout_sport("hockey") is None
    assert R.odds_provider_for("hockey") is None
    assert R.uses_source("hockey", "rss") is False


# ═════════ 🔴 핵심 — 표에 한 줄 더하면 대상이 는다 ═════════

def test_adding_a_sport_to_the_registry_is_enough(monkeypatch):
    """가짜 종목을 표에 넣으면 **코드 수정 없이** 정찰 대상이 되어야 한다.

    이 테스트가 깨지면 어딘가에 종목 문자열이 하드코딩된 것이다.
    """
    fake = R.ScoutSport("cricket", ("rss",), lineup_source="espncricinfo")
    monkeypatch.setattr(R, "SCOUT_SPORTS", (*R.SCOUT_SPORTS, fake))
    monkeypatch.setattr(R, "_SCOUT_BY_SPORT",
                        {**R._SCOUT_BY_SPORT, "cricket": fake})

    assert R.scout_sport("cricket") is fake
    assert "cricket" in [x.sport for x in R.scout_sports(active_only=True)]
    assert R.uses_source("cricket", "rss") is True
    assert R.uses_source("cricket", "xsearch") is False


def test_deactivating_a_sport_removes_it_from_active(monkeypatch):
    off = replace(R.scout_sport("kbo"), active=False, reason="테스트")
    monkeypatch.setattr(R, "_SCOUT_BY_SPORT",
                        {**R._SCOUT_BY_SPORT, "kbo": off})
    monkeypatch.setattr(R, "SCOUT_SPORTS",
                        tuple(off if x.sport == "kbo" else x
                              for x in R.SCOUT_SPORTS))
    assert "kbo" not in [x.sport for x in R.scout_sports(active_only=True)]


# ═════════ 정찰 창·보고 시각도 표가 원본 ═════════

def test_windows_come_from_the_table():
    for s in R.scout_sports():
        assert s.scout_open_h > 0
        assert s.report_at_min > 0
        # 보고는 정찰 창 **안**이어야 한다
        assert s.report_at_min < s.scout_open_h * 60


def test_no_sport_string_hardcoded_in_scout_helpers():
    """헬퍼 본문에 종목 이름이 박히면 표가 원본이 아니게 된다."""
    src = Path("app/registry.py").read_text(encoding="utf-8")
    i = src.index("def scout_sport(")
    seg = src[i:src.index("#: 워치독이 지연을 볼 잡")]
    for sp in ("kbo", "npb", "mlb", "soccer"):
        assert not re.search(rf'"{sp}"', seg), f"헬퍼에 {sp} 가 박혀 있다"
