"""ACL-1 — ACL 엘리트 배선. 경기는 FotMob, 배당은 오즈포털 평균.

🔴 실측 2026-09-15 이 이 파일의 이유다:
     The Odds API 종목 178개 전수 → AFC 계열 키 **0개**
     FotMob matches?date=20260915 → AFC Champions League Elite East 에 4경기
     오즈포털 /asia/afc-champions-league/ → 경기행 15 · 1X2 배당 16
     같은 페이지 positionsWithProviders → **0경기**(북별 불가)
     Transfermarkt AFCL·ACL·AFC1 → 부상 **0행**(컵 대회 표가 없다)
"""
from __future__ import annotations

import pytest

from app.collectors import oddsportal as OP
from app.leagues import LEAGUES


def test_acl이_리그로_있다():
    cfg = LEAGUES["acl"]
    assert cfg["label"] == "ACL엘리트"
    assert cfg["odds_key"] is None, "The Odds API 에 AFC 키가 없다(실측 178종목)"
    assert cfg["elo"] is None
    assert cfg["tm_code"] is None
    assert cfg["fotmob_contains"] == "AFC Champions League Elite"


def test_SOCCER_URL_키가_LEAGUES_와_같다():
    """기존 계약 유지 — 리그가 늘면 배당 URL 도 같이 는다."""
    # 🔴 [LGA-1 2026-09-20] 이 계약이 뜻한 것은 **전 기능이 준비된 리그**다.
    #    결과만 쌓는 리그는 `features` 로 갈린다(계약 약화가 아니라 뜻의 명시).
    from app.leagues import leagues_with

    assert set(OP.SOCCER_URL) == set(leagues_with("odds"))
    assert "afc-champions-league" in OP.SOCCER_URL["acl"]


# ── 🔴 반대 위험 ①: odds_key=None 이 기존 경로를 깨면 안 된다

def test_odds_key_없는_리그가_기존_경로를_깨지_않는다():
    from app.collectors.odds import SOCCER_LEAGUE_LABELS, SPORT_KEYS

    assert None not in SPORT_KEYS["soccer"], "None 키로 API 를 때린다"
    assert all(SPORT_KEYS["soccer"]), SPORT_KEYS["soccer"]
    assert len(SPORT_KEYS["soccer"]) == 7, "기존 7리그가 줄었다"
    assert None not in SOCCER_LEAGUE_LABELS
    assert "ACL엘리트" not in SOCCER_LEAGUE_LABELS.values()


def test_odds_key_를_읽는_곳이_전부_막혀_있다():
    """🔴 리그가 늘 때마다 반복될 자리다. `odds_key` 를 **무조건** 읽는 줄이
    남아 있으면 None 리그가 들어올 때 거기서 터진다."""
    import pathlib
    import re

    #: `cfg["odds_key"]` 처럼 **조건 없이** 첨자로 읽는 형태만 잡는다.
    raw = re.compile(r"""\[["']odds_key["']\]""")
    bad = []
    for f in pathlib.Path("app").rglob("*.py"):
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, ln in enumerate(lines):
            s = ln.strip()
            if s.startswith("#") or not raw.search(ln):
                continue
            window = " ".join(lines[max(0, i - 1):i + 2])
            if 'get("odds_key")' in window or "_ok" in window:
                continue          # 같은 줄이나 바로 옆에서 걸러진다
            bad.append(f"{f}:{i + 1} {s[:90]}")
    assert bad == [], "odds_key 를 거르지 않고 읽는다:\n  " + "\n  ".join(bad)


# ── 🔴 반대 위험 ②: 국가 접미사 제거가 다른 팀을 합치면 안 된다

@pytest.mark.parametrize("raw,want", [
    ("Gamba Osaka (Jpn) ", "Gamba Osaka"),
    ("Daejeon (Kor) ", "Daejeon"),
    ("Cong An Ha Noi (Vie) ", "Cong An Ha Noi"),
    ("Newcastle Jets (Aus)", "Newcastle Jets"),
    # 괄호가 없거나 3글자가 아니면 **건드리지 않는다**
    ("Hull City AFC", "Hull City AFC"),
    ("Manchester Utd", "Manchester Utd"),
    ("Brighton (Reserve)", "Brighton (Reserve)"),
    ("1. FC Köln", "1. FC Köln"),
])
def test_국가접미사만_떼고_다른_이름은_그대로다(raw, want):
    assert OP.strip_country(raw) == want


def test_기존_팀키가_바뀌지_않았다():
    """🔴 회귀 방지 — 접미사 제거가 기존 122팀 대조를 흔들면 안 된다."""
    for raw, want in (("Leeds", "leeds united"),
                      ("Manchester Utd", "manchester united"),
                      ("Brighton", "brighton hove albion")):
        assert OP.team_key(raw) == want, (raw, OP.team_key(raw))


def test_ACL_팀키가_FotMob_표기와_붙는다():
    """오즈포털 짧은 표기 ↔ FotMob 긴 표기. 양쪽 키가 같아야 경기에 붙는다."""
    from app.collectors.fotmob import canonical

    for op_raw, fm_name in (
            ("Kashima Antlers (Jpn) ", "Kashima Antlers"),
            ("Newcastle Jets (Aus) ", "Newcastle Jets"),
            ("Gamba Osaka (Jpn) ", "Gamba Osaka"),
            ("Cong An Ha Noi (Vie) ", "Công An Hà Nội"),
            ("Daejeon (Kor) ", "Daejeon Hana Citizen"),   # FotMob 긴 표기
            ("Kyoto (Jpn) ", "Kyoto Sanga FC"),
            ("Beijing Guoan (Chn) ", "Beijing Guoan"),
            ("Pohang (Kor) ", "Pohang Steelers")):
        assert OP.team_key(op_raw) == OP.norm(canonical(fm_name)), \
            f"{op_raw!r} → {OP.team_key(op_raw)!r} ≠ {OP.norm(canonical(fm_name))!r}"


# ── FotMob 적재

@pytest.mark.asyncio
async def test_fotmob_적재는_매핑_실패를_조용히_넘기지_않는다(monkeypatch, caplog):
    import logging

    from app.collectors import fotmob as FM

    async def fake_slate(_d):
        return [
            {"id": 1, "league": "AFC Champions League Elite East", "ccode": "INT",
             "home": "Kashima Antlers", "away": "Newcastle Jets",
             "utc": "2026-09-15T10:00:00.000Z"},
            {"id": 2, "league": "AFC Champions League Elite East", "ccode": "INT",
             "home": "", "away": "X", "utc": "2026-09-15T10:00:00.000Z"},
            {"id": 3, "league": "Premier League", "ccode": "ENG",
             "home": "H", "away": "A", "utc": "2026-09-15T10:00:00.000Z"},
        ]

    monkeypatch.setattr(FM, "slate", fake_slate)

    calls = []

    class _Pool:
        async def execute(self, sql, *a):
            calls.append(a)

    with caplog.at_level(logging.WARNING):
        out = await FM.upsert_slate(_Pool(), "20260915", league_key="acl")

    assert out["fetched"] == 3 and out["matched"] == 2 and out["saved"] == 1
    assert out["skipped"] and "적재 제외" in caplog.text, "조용히 버렸다"
    assert calls[0][1] == "fotmob:1", "키가 fotmob_id 가 아니다"
    assert calls[0][0] == "ACL엘리트"
    from datetime import datetime
    assert isinstance(calls[0][2], datetime), "킥오프가 문자열이다(ODP-2·LH-2 재발)"
