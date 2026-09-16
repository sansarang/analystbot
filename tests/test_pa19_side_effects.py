"""PA-19 계약 — 판정이 같아도 부수 기록은 돈다.

🔴 실측 2026-09-16: ACLE 2경기가 `[v3]` 판정을 두 번 냈는데 원장은
   `judged_at 06:16UTC` 그대로 · 사전값 None · 게이트 None · need 0.
   축구는 같은 승자가 반복돼 **영원히 unchanged** 라, 티어를 채우고(PA-7)
   길을 열어도(PA-6·PA-13) 값이 안 찼다.
🔴 이 값들은 **판정이 같아도 시간이 지나면 달라진다** — 배당은 나중에 오고,
   라인업은 T-60 에 뜨고, 위성 추출은 다음 사이클에 붙는다.
"""
import inspect
import pathlib

import pytest

from app.engine import pick_ledger as PL

SIDE = ("record_move", "record_book_gap", "record_prior",
        "record_confirm_and_analysis")


@pytest.fixture
def spy(monkeypatch):
    called: list[str] = []

    for fn in SIDE + ("record_clv",):
        async def _f(*a, _n=fn, **k):
            called.append(_n)
            return None
        monkeypatch.setattr(PL, fn, _f)
    return called


class _Conn:
    async def fetchrow(self, sql, *a):
        if "FOR UPDATE" in sql:
            return {"id": 1, "rejudge_count": 0, "p_home": 0.55,
                    "favored": "home", "predicted_side": "home",
                    "confidence": "중", "p_market": None,
                    "p_market_spine": None, "sport": "soccer"}
        return None

    async def fetch(self, sql, *a):
        return []

    async def execute(self, sql, *a):
        return None

    def transaction(self):
        class _T:
            async def __aenter__(s):
                return None

            async def __aexit__(s, *a):
                return False
        return _T()


class _Pool:
    def acquire(self):
        class _A:
            async def __aenter__(s):
                return _Conn()

            async def __aexit__(s, *a):
                return False
        return _A()


ANALYSIS = {
    "sport": "soccer", "date": "2026-09-16",
    "games": [{"game_id": 8360, "sport": "soccer", "league": "ACL엘리트",
               "home": "Jeonbuk Hyundai Motors FC", "away": "Kashiwa Reysol",
               "matchup": {"승자": "Jeonbuk Hyundai Motors FC", "확신": "하"},
               "winner": "Jeonbuk Hyundai Motors FC", "p_claude": 0.55}],
}


@pytest.mark.asyncio
async def test_판정이_같아도_부수_기록은_돈다(spy, monkeypatch):
    monkeypatch.setattr(PL, "_same_judgement", lambda row, ex: True)
    out = await PL.record_analysis(_Pool(), ANALYSIS, trial=True)
    assert out["unchanged"] == 1, "이력 행이 늘었다"
    for fn in SIDE:
        assert fn in spy, f"{fn} 이 안 불렸다"


@pytest.mark.asyncio
async def test_판정이_같으면_CLV는_다시_안_찍는다(spy, monkeypatch):
    """⚠️ 판정 시각 배당은 그 시각이 이미 지났다 — 덮어쓰면 거짓이 된다."""
    monkeypatch.setattr(PL, "_same_judgement", lambda row, ex: True)
    await PL.record_analysis(_Pool(), ANALYSIS, trial=True)
    assert "record_clv" not in spy


@pytest.mark.asyncio
async def test_판정이_바뀌면_CLV도_찍는다(spy, monkeypatch):
    monkeypatch.setattr(PL, "_same_judgement", lambda row, ex: False)
    await PL.record_analysis(_Pool(), ANALYSIS, trial=True)
    assert "record_clv" in spy
    for fn in SIDE:
        assert fn in spy


def test_부수_기록은_한_곳이다():
    """🔴 사본 금지 — 두 분기가 같은 함수를 부른다."""
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert src.count("await _record_side_effects(") == 2
    body = inspect.getsource(PL._record_side_effects)
    for fn in SIDE:
        assert f"await {fn}(" in body


def test_하나가_터져도_나머지는_돈다():
    """🔴 각각을 따로 감싼다 — 한 실패가 나머지를 못 막는다."""
    body = inspect.getsource(PL._record_side_effects)
    assert body.count("except Exception") >= len(SIDE)


def test_판정을_건드리지_않는다():
    """🔴 전부 저장 전용이다."""
    body = inspect.getsource(PL._record_side_effects)
    for banned in ("INSERT", "is_final = ", "predicted_side =", "p_home ="):
        assert banned not in body, f"부수 기록이 {banned} 를 건드린다"
