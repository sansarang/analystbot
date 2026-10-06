"""🔴🔴 **v6 §7 단위 — s1 확정 · s2 구조 사실.**

⚠️ 라이브 없이 세는 것만 여기 둔다 — 다섯 경기 녹화는 §8 2단계가 **사용자가 준
   경기**로 한다(사용자 지시 2026-10-06: *"지금 제공한 경기는 이미 끝난 경기다"*).
"""
from __future__ import annotations

import asyncio
import datetime as dt

from app.core import adapt
from app.core.schema import Ambiguous, MatchRef
from app.core.stages import s1_resolve as S1
from app.core.stages import s2_facts as S2
from app.core.state import RunState

UTC = dt.timezone.utc


class _Look:
    def __init__(self, ok, ref=None, steps=(), candidates=(), reason=None):
        self.ok, self.ref, self.steps = ok, ref, list(steps)
        self.candidates = list(candidates)
        self.reason = reason


class _OldRef:
    """🔴 기존 `matchref.MatchRef` 의 모양(부품 내부는 안 건드린다 · §2)."""

    def __init__(self, **kw):
        self.key = kw.get("key", "fotmob:1")
        self.home, self.away = kw.get("home", "Honduras"), kw.get("away", "Jamaica")
        self.home_id = kw.get("home_id", "team:000103")
        self.away_id = kw.get("away_id", "team:000119")
        self.competition = kw.get("competition", "CONCACAF Nations League A Grp. 2")
        self.sport = kw.get("sport", "soccer")
        self.venue = kw.get("venue", "")
        self.kickoff_utc = kw.get("kickoff_utc",
                                  dt.datetime(2026, 10, 7, 2, tzinfo=UTC))
        self.langs = kw.get("langs", ("en",))


def _q():
    from app.core.schema import Question
    return Question(raw="온두라스 vs 자메이카", team="온두라스",
                    opponent="자메이카",
                    asked_at=dt.datetime(2026, 10, 6, 1, tzinfo=UTC))


def test_s1_확정하면_MatchRef_를_낸다(monkeypatch):
    from app import resolve

    async def _fake(pool, **kw):
        return _Look(True, ref=_OldRef(), steps=["✅ 찾았다"])

    monkeypatch.setattr(resolve, "match_of", _fake)
    st = RunState()
    got = asyncio.run(S1.run(_q(), pool=None, state=st))
    assert isinstance(got, MatchRef), got
    # 🔴 열쇠로 다닌다(이름은 렌더용 칸에만)
    assert got.home == "team:000103" and got.home_name == "Honduras"
    # 🔴 짧은 대회명이 들어간다(§2-2 한 함수)
    assert got.competition_short == "CONCACAF Nations League", got.competition_short
    assert st.match_key == "fotmob:1"
    assert any("찾았다" in n for n in st.notes), st.notes


def test_s1_못_고르면_Ambiguous_다(monkeypatch):
    """🔴 하나를 골라 주면 **남의 경기**를 분석한다(§17-g-3 · M14)."""
    from app import resolve
    from app.matchref import Reason

    async def _fake(pool, **kw):
        return _Look(False, reason=Reason.MATCH_NOT_FOUND,
                     candidates=[{"home": "A", "away": "B", "league": "L"}])

    monkeypatch.setattr(resolve, "match_of", _fake)
    got = asyncio.run(S1.run(_q(), pool=None, state=RunState()))
    assert isinstance(got, Ambiguous), got
    assert got.candidates, got


def test_s1_터져도_예외를_안_던진다(monkeypatch):
    """🔴 §5 — 단계는 예외를 위로 던지지 않는다. 카드는 **항상** 나온다."""
    from app import resolve

    async def _boom(pool, **kw):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(resolve, "match_of", _boom)
    st = RunState()
    got = asyncio.run(S1.run(_q(), pool=None, state=st))
    assert isinstance(got, Ambiguous) and "터졌다" in got.why, got
    assert st.drops, st.drops


def test_s1_시간대_없는_킥오프는_안_받는다(monkeypatch):
    """🔴 절대규칙 2 — 그 값으로 창을 자르면 경기를 잃는다(실측 2026-10-03)."""
    from app import resolve

    async def _fake(pool, **kw):
        return _Look(True, ref=_OldRef(kickoff_utc=dt.datetime(2026, 10, 7, 2)))

    monkeypatch.setattr(resolve, "match_of", _fake)
    got = asyncio.run(S1.run(_q(), pool=None, state=RunState()))
    assert isinstance(got, Ambiguous), got
    assert "킥오프" in got.why, got.why


def test_s2_어댑터_모양_차이를_흡수한다():
    """🔴 `players` 가 dict 든 list 든 같은 꼴로 나온다(결함 ①의 사례)."""
    a = adapt.xi_of("team:000103", {"players": {"1": "Kim", "2": {"name": "Lee"}},
                                    "formation": "4-4-2", "confirmed": True})
    b = adapt.xi_of("team:000103", {"players": ["Kim", {"name": "Lee"}]})
    assert a.players == b.players == ["Kim", "Lee"], (a.players, b.players)
    assert a.state == "confirmed" and b.state == "predicted"
    # 🔴 아무것도 없으면 `none` — 지어내지 않는다
    assert adapt.xi_of("team:000103", None).state == "none"


def test_s2_빈_Facts_도_돌아온다(monkeypatch):
    """🔴 깊이 소스가 터져도 **빈 `Facts`** 다(§5)."""
    ref = MatchRef(id="fotmob:1", sport="soccer", competition="X Grp. 2",
                   competition_short="X", home="team:000103",
                   away="team:000119", home_name="A", away_name="B",
                   kickoff_utc=dt.datetime(2026, 10, 7, 2, tzinfo=UTC))

    async def _boom(ref_, *, net, search):
        raise RuntimeError("깊이 실패")

    monkeypatch.setattr(S2, "_depth", _boom)
    st = RunState()
    got = asyncio.run(S2.run(ref, state=st, net=None))
    assert got.standings == {} and got.xi == {}
    assert got.match_format in set(
        MatchRef.model_fields["sport"].annotation.__args__) | {
            "league", "group", "knockout_single", "two_leg_1st", "two_leg_2nd",
            "final_single", "friendly", "unknown"}
    assert st.drops, st.drops


def test_s2_형식을_모르면_unknown_이다():
    """🔴 지어내지 않는다 — 표가 못 맞추면 `unknown`."""
    ref = MatchRef(id="x", sport="soccer", competition="알 수 없는 대회",
                   competition_short="알 수 없는 대회", home="team:000103",
                   away="team:000119", home_name="A", away_name="B",
                   kickoff_utc=dt.datetime(2026, 10, 7, 2, tzinfo=UTC))
    fmt, why = S2._format_of(ref)
    assert fmt == "unknown", (fmt, why)
    assert "모른다" in why, why
