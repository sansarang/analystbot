"""ODF-1 계약 — ESPN 이 주는 **MLB 총점·핸디 가격**을 쓴다. 무료다.

🔴 사용자 지시 2026-09-17: "Odds API 아니더라도 무료가 잇다" — 맞았다.
실측(운영에서 ESPN Core API 직접 호출):
    DraftKings … overUnder 7.0 · overOdds 101.0 · underOdds -122.0
                 spread -1.5 · homeTeamOdds.current.spread.value 2.42
그런데 MLB 파서가 "ESPN 은 O/U 가격을 따로 안 준다"며 버렸다 — **틀린 판단**이고,
같은 파일의 축구 파서는 **이미 그 필드를 읽고 있었다.**
결과: 14일 실측 mlb totals **0건** · soccer totals 150건 → S9 구조픽 0/18.

⚠️ KBO·NPB 는 여전히 h2h 뿐이다 — ESPN 이 그 리그를 커버하지 않는다.
"""
import inspect

import pytest

from app.collectors import espn_odds as E

HOME, AWAY = "Cleveland Guardians", "Chicago White Sox"
ITEM = {"provider": {"name": "DraftKings"},
        "homeTeamOdds": {"current": {"moneyLine": {"decimal": 1.60},
                                     "spread": {"value": 2.42}}},
        "awayTeamOdds": {"current": {"moneyLine": {"decimal": 2.40},
                                     "spread": {"value": 1.62}}},
        "overUnder": 7.0, "overOdds": 101.0, "underOdds": -122.0,
        "spread": -1.5}


def _rows(item=None):
    return E.parse_odds(item or ITEM, HOME, AWAY)


def _of(market, rows=None):
    return [r for r in (rows or _rows()) if r["market"] == market]


def test_총점_양쪽이_나온다():
    t = _of("totals")
    assert {r["side"] for r in t} == {"Over", "Under"}
    assert all(r["line"] == 7.0 for r in t)


def test_미국식_환산이_맞다():
    """🔴 항등식이라 추측이 아니다: +101 → 2.01 · −122 → 1.82."""
    t = {r["side"]: r["odds"] for r in _of("totals")}
    assert t["Over"] == pytest.approx(2.01, abs=0.005)
    assert t["Under"] == pytest.approx(1.82, abs=0.005)


def test_핸디_양쪽이_나온다():
    s = {r["side"]: r for r in _of("spreads")}
    assert set(s) == {HOME, AWAY}
    assert s[HOME]["line"] == -1.5 and s[AWAY]["line"] == 1.5


def test_핸디_가격은_소수_그대로다():
    """🔴 야구 핸디는 `current.spread.value` 가 **소수**다 — 환산하지 않는다."""
    s = {r["side"]: r["odds"] for r in _of("spreads")}
    assert s[HOME] == pytest.approx(2.42) and s[AWAY] == pytest.approx(1.62)


# ── 🔴 반대 위험

def test_h2h가_그대로_나온다():
    """🔴 승부 배당이 본선이다."""
    h = {r["side"]: r["odds"] for r in _of("h2h")}
    assert h[HOME] == pytest.approx(1.6) and h[AWAY] == pytest.approx(2.4)


def test_가격이_없으면_안_넣는다():
    """🔴 종전 판단의 **원칙은 옳다** — 없는 값을 −110 으로 지어내지 않는다."""
    item = {k: v for k, v in ITEM.items() if k not in ("overOdds", "underOdds")}
    assert _of("totals", _rows(item)) == []


def test_라인이_없으면_안_넣는다():
    item = {k: v for k, v in ITEM.items() if k != "overUnder"}
    assert _of("totals", _rows(item)) == []
    item2 = {k: v for k, v in ITEM.items() if k != "spread"}
    assert _of("spreads", _rows(item2)) == []


def test_핸디_가격이_1_이하면_안_넣는다():
    item = dict(ITEM, homeTeamOdds={"current": {"moneyLine": {"decimal": 1.6},
                                                "spread": {"value": 0.9}}})
    assert [r["side"] for r in _of("spreads", _rows(item))] == [AWAY]


def test_라이브_북은_버린다():
    item = dict(ITEM, provider={"name": "ESPN BET Live"})
    if E.is_live_book("espn bet live"):
        assert _rows(item) == []


def test_축구_파서를_안_건드렸다():
    """🔴 거긴 이미 읽고 있었다 — 두 벌이 되면 사본이다."""
    src = inspect.getsource(E.parse_soccer_odds)
    assert "overOdds" in src and "spreadOdds" in src


def test_틀린_주석을_지웠다():
    body = "\n".join(ln for ln in inspect.getsource(E.parse_odds).splitlines()
                     if ln.strip())
    assert "가격 없음 — 생략" not in body


def test_콜_수가_안_는다():
    """🔴 같은 응답에서 더 읽을 뿐이다."""
    src = inspect.getsource(E.parse_odds)
    for bad in ("await", "httpx", "client.get"):
        assert bad not in src, bad
