"""ODN-1 계약 — KBO·NPB **총점·핸디·팀토탈**을 받는다. 예산 안에서.

🔴 실측 2026-09-17 (odds-api.net 실호출):
     /events 야구 6일 창 — KBO 2 · NPB 5 · 경기당 북 44
     /events/{id}/odds/snapshot → 1,405행
       total/over 7.5 33북 · handicap/home -1.5 39북 · team total 272행
   앞서 셋이 막혔다 — 배트맨(폐기) · oddsportal(JS 뒤) · betexplorer(과거 전적).
🔴 **월 1,000 크레딧(sandbox)** — 기존 30분 주기면 월 11,520콜이 필요하다.
⚠️ **기존 `odds_snapshot_30m` 은 안 건드린다**(무료·무제한 · CLV 가 거기서 난다).
"""
import inspect
import pathlib

import pytest

from app.collectors import oddsapinet as ON

# 🔴 **실측 모양 그대로다**(운영에서 직접 확인 2026-09-17):
#    total       side=None · line="over 7.5"        ← 방향이 line 안에 있다
#    team total  side=home/away · line="over 4.5"
#    handicap    side=home/away · line="-1.5"
#    처음에 내가 지어낸 `side="over"` 로 통과시켰다가 운영에서 totals 0행이
#    나왔다(ODN-1-b). 지어낸 모양을 재면 고친 코드가 아니라 상상을 잰다.
ITEMS = [
    {"bet_type": "total", "bookmaker": "pinnacle", "line": "over 7.5",
     "side": None, "odds": 1.91, "period": "full time", "is_available": True},
    {"bet_type": "total", "bookmaker": "pinnacle", "line": "under 7.5",
     "side": None, "odds": 1.95, "period": "full time", "is_available": True},
    {"bet_type": "handicap", "bookmaker": "bet365", "line": "-1.5",
     "side": "home", "odds": 2.05, "period": "full time", "is_available": True},
    {"bet_type": "handicap", "bookmaker": "bet365", "line": "+1.5",
     "side": "away", "odds": 1.80, "period": "full time", "is_available": True},
    {"bet_type": "team total", "bookmaker": "pinnacle", "line": "over 4.5",
     "side": "home", "odds": 1.85, "period": "full time", "is_available": True},
]
KW = {"home": "KIA", "away": "키움"}


def _rows(items=None):
    return ON.to_rows(items if items is not None else ITEMS, **KW)


def test_총점이_나온다():
    t = [r for r in _rows() if r["market"] == "totals"]
    assert {r["side"] for r in t} == {"Over", "Under"}
    assert all(r["line"] == 7.5 for r in t)


def test_핸디가_쪽마다_제_라인을_갖는다():
    """⚠️ API 가 쪽마다 라인을 따로 준다 — 부호를 우리가 뒤집지 않는다."""
    s = {r["side"]: r["line"] for r in _rows() if r["market"] == "spreads"}
    assert s == {"KIA": -1.5, "키움": 1.5}


def test_팀토탈은_팀과_방향을_둘_다_갖는다():
    """🔴 side 는 팀, line 은 방향+숫자 — 둘 다 있어야 한 줄이 된다."""
    t = [r for r in _rows() if r["market"] == "team_totals"]
    assert t and t[0]["side"] == "KIA Over" and t[0]["line"] == 4.5


def test_라인이_숫자다():
    assert all(isinstance(r["line"], float) for r in _rows())


# ── 🔴 버리는 규칙이 본체다

def test_정규이닝만_쓴다():
    """🔴 5이닝 −0.5 와 정규 −1.5 는 **다른 시장**이다. 섞으면 라인이 어긋난다."""
    five = [dict(ITEMS[0], period="5 innings")]
    assert _rows(five) == []


def test_닫힌_배당은_버린다():
    closed = [dict(ITEMS[0], is_available=False)]
    assert _rows(closed) == []


def test_승패는_안_싣는다():
    """🔴 oddsportal 이 이미 준다 — 두 소스가 같은 칸을 채우면 디빅이 흔들린다."""
    ml = [{"bet_type": "moneyline", "bookmaker": "x", "line": None,
           "side": "home", "odds": 1.49, "period": "full time",
           "is_available": True}]
    assert _rows(ml) == []


def test_라인이나_배당이_없으면_버린다():
    for bad in ({"line": None}, {"odds": None}, {"odds": 1.0}):
        assert _rows([dict(ITEMS[0], **bad)]) == []


def test_홀짝은_총점이_아니다():
    """🔴 `even`·`odd` 는 다른 시장이고 라인이 없다."""
    for v in ("even", "odd"):
        assert _rows([dict(ITEMS[0], line=v)]) == []


# ── 예산·키

def test_예산_문턱이_있다():
    assert 0 < ON.BUDGET_STOP_RATIO <= 0.9
    src = inspect.getsource(ON.budget_ok)
    assert "BUDGET_STOP_RATIO" in src


@pytest.mark.asyncio
async def test_예산을_읽고_판단한다(monkeypatch):
    """🔴 `/usage` 를 못 읽으면 **안전한 쪽**으로 멈춘다.

    ⚠️ **망을 타지 않는다.** 처음에 `budget_ok()` 를 그냥 불렀더니 실제
       HTTP 를 쳐서 스위트가 600초 넘게 멈췄다(샌드박스가 막는다).
    """
    async def _fake(result):
        async def _g(*a, **k):
            return result
        return _g

    monkeypatch.setattr(ON, "_get", await _fake(None))
    assert await ON.budget_ok() is False                      # 못 읽으면 멈춘다

    monkeypatch.setattr(ON, "_get", await _fake(
        {"api_credits_limit": 1000, "api_credits_used": 100}))
    assert await ON.budget_ok() is True                       # 10% — 간다

    monkeypatch.setattr(ON, "_get", await _fake(
        {"api_credits_limit": 1000, "api_credits_used": 900}))
    assert await ON.budget_ok() is False                      # 90% — 멈춘다


def test_키가_코드에_없다():
    """🔴 키는 `.env` 에만. 코드·커밋에 남기지 않는다."""
    src = pathlib.Path("app/collectors/oddsapinet.py").read_text(encoding="utf-8")
    assert "oa_" not in src
    assert "get_settings" in inspect.getsource(ON._key)


def test_KBO_NPB만_받는다():
    """🔴 MLB·축구는 ESPN 무료로 이미 된다 — 크레딧을 아낀다."""
    assert set(ON.LEAGUES) == {"kbo", "npb"}


def test_적재는_기존_통로를_쓴다():
    import app.scheduler as S

    src = inspect.getsource(S.oddsapinet_job)
    assert "store_rows" in src
    assert "INSERT INTO odds_snapshots" not in src


def test_기존_30분_잡이_그대로다():
    """🔴 반대 위험 — 무료·무제한이고 CLV 가 거기서 난다."""
    src = pathlib.Path("app/scheduler.py").read_text(encoding="utf-8")
    assert '("odds_snapshot_30m", odds_snapshot_job, IntervalTrigger(minutes=30))' in src
    assert '("oddsapinet_2x"' in src
