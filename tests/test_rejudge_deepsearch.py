"""[RJG-2] 판정 생략이 **딥서치 T5·T6 까지 껐다** — RJG-1 이 낸 회귀.

🔴 **내가 커밋에 거짓을 적었다.** RJG-1(`648849b`)은 이렇게 주장했다:
     "승격·research 병합·결장자·배당·의도·**딥서치**·수정 카드 발송은 전부 그대로다"
   그런데 `rejudge_after_lineup` 에서 `run_for_rejudge` 호출은
   `_run_baseball_matchups` 와 **같은 블록 안**에 있었다. `if` 를 `elif` 로
   바꾸면서 딥서치도 함께 생략된다.

⚠️ **하필 가장 나쁜 조합이다.** 그 딥서치가 반응하는 트리거는
     T4 선발 변경 · **T5 라인업 이상** · T6 첫 라인업
   이고, 우리가 생략하는 경우가 정확히 **선발은 그대로이고 타순만 바뀐** 때다 —
   T4 는 어차피 안 걸리고 **T5·T6 만 걸릴 수 있는 상황**인데 그것을 껐다.
   `deepsearch.run_for_rejudge` 자신이 적어 두었다: "라인업이 바뀌었을 때
   조사하라고 만든 트리거인데 정작 라인업 재판정에 연결이 없었다."

🔴 **이 파일은 소스 텍스트를 읽지 않는다.** `rejudge_after_lineup` 의 기존
   테스트 넷이 전부 `src.index(...)` 형태였고(FINDINGS TST-2 가 지적한 바로 그
   형태), 그래서 들여쓰기 한 칸이 바꾼 **동작**을 아무도 못 봤다. 여기서는
   함수를 실제로 돌리고 **무엇이 불렸는지**로 단언한다.
"""
from __future__ import annotations

import json

import pytest


class _Redis:
    def __init__(self, store):
        self.store = store

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, *a, **kw):
        self.store[k] = v

    async def setex(self, k, t, v):
        self.store[k] = v

    async def aclose(self):
        pass

    async def exists(self, k):
        return int(k in self.store)

    async def lrange(self, *a, **kw):
        return []


class _Pool:
    def acquire(self):
        return _Conn()

    async def fetch(self, *a, **kw):
        return []

    async def fetchrow(self, *a, **kw):
        return None

    async def fetchval(self, *a, **kw):
        return None

    async def execute(self, *a, **kw):
        return None


class _Conn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def fetch(self, *a, **kw):
        return []

    async def fetchrow(self, *a, **kw):
        return None

    async def fetchval(self, *a, **kw):
        return None

    async def execute(self, *a, **kw):
        return None


def _analysis(*, p_claude=0.55, starter="손주영"):
    return {"sport": "kbo", "date": "2026-09-09", "games": [{
        "game_id": 1, "sport": "kbo", "status": "scheduled",
        "home": "LG Twins", "away": "Doosan Bears",
        "p_claude": p_claude, "p_model": 0.5, "p_market": None,
        "lineup_status": "confirmed",
        "pick_summary": {"desc": "보드만"},
        "research": {
            "home_pitcher": {"name": starter},
            "away_pitcher": {"name": "곽빈"},
            "home_lineup": {"order": "가(중)-나(유)"},
            "away_lineup": {"order": "다(중)-라(유)"},
        },
    }], "picks": [], "parlays": [], "combos": []}


@pytest.fixture
def wired(monkeypatch):
    """`rejudge_after_lineup` 을 실제로 돌리되 바깥 세계만 막는다."""
    import app.pipeline as P

    calls = {"judge": 0, "deepsearch": 0}
    store = {"analysis:kbo:2026-09-09": json.dumps(_analysis(), ensure_ascii=False)}

    monkeypatch.setattr(P, "default_date", lambda sport: "2026-09-09")
    monkeypatch.setattr(P.aioredis, "from_url", lambda *a, **kw: _Redis(store))

    async def _pool():
        return _Pool()
    monkeypatch.setattr("app.db.get_pool", _pool)

    async def _research(redis, jg, sport, force=False):
        return (jg.get("research"), "cached")
    monkeypatch.setattr("app.research.deep.get_game_research", _research)

    async def _judge(redis, date, games, allow_final=False):
        calls["judge"] += 1
        return 1
    monkeypatch.setattr(P, "_run_baseball_matchups", _judge)

    async def _ds(jg, redis, date, **kw):
        calls["deepsearch"] += 1
        return {"triggered": False, "triggers": [], "status": None,
                "searches": 0, "moved_pp": 0.0, "source": None}
    monkeypatch.setattr("app.engine.deepsearch.run_for_rejudge", _ds)

    monkeypatch.setattr(P, "_prepare_games_for_judge", lambda games, sport: None)
    monkeypatch.setattr(P, "_enforce_data_rules", lambda games: None)
    monkeypatch.setattr(P, "_compute_picks",
                        lambda *a, **kw: ([], [], None))
    monkeypatch.setattr("app.engine.parlay.build_tiered_parlays",
                        lambda *a, **kw: [])
    monkeypatch.setattr(P, "_spawn_fact_audit", lambda jg: None)

    async def _renarrate(games, sport):
        return None
    monkeypatch.setattr(P, "_renarrate", _renarrate)
    return calls, store


async def test_타순만_바뀌면_판정은_생략하되_딥서치는_돈다(wired):
    """🔴 RJG-2 의 핵심. 생략하는 그 경우가 T5·T6 만 걸릴 수 있는 경우다."""
    from app.pipeline import rejudge_after_lineup

    calls, _ = wired
    ok = await rejudge_after_lineup(
        {"id": 1, "sport": "kbo"},
        {"status": "confirmed", "notes": [], "home": ["가", "나"], "away": ["다", "라"]})
    assert ok is True
    assert calls["judge"] == 0, "선발이 그대로인데 LLM 판정을 다시 돌렸다"
    assert calls["deepsearch"] == 1, "판정을 생략하면서 딥서치 T5·T6 까지 껐다"


async def test_선발_변경_통지가_오면_판정도_딥서치도_돈다(wired):
    """반대 위험 — 선발이 바뀌었는데 생략하면 틀린 투수로 낸 카드가 최종이 된다.

    ⚠️ 여기서는 **배선**만 본다. 판별 규칙 자체(선발 변경·새로 확인·판정 없음·
       통지)는 `needs_rejudge` 단위 테스트가 잠근다 — 두 곳에 적지 않는다.
    """
    from app.pipeline import rejudge_after_lineup

    calls, _ = wired
    await rejudge_after_lineup(
        {"id": 1, "sport": "kbo"},
        {"status": "confirmed", "notes": ["홈 선발 변경: 임찬규 → 손주영"],
         "home": ["가"], "away": ["다"]})
    assert calls["judge"] == 1, "선발 변경 통지가 왔는데 판정을 생략했다"
    assert calls["deepsearch"] == 1


async def test_판정이_없으면_돌린다(wired, monkeypatch):
    from app.pipeline import rejudge_after_lineup

    calls, store = wired
    store["analysis:kbo:2026-09-09"] = json.dumps(
        _analysis(p_claude=None), ensure_ascii=False)
    await rejudge_after_lineup(
        {"id": 1, "sport": "kbo"},
        {"status": "confirmed", "notes": [], "home": ["가"], "away": ["다"]})
    assert calls["judge"] == 1, "판정이 없는데 생략했다"


async def test_생략이_재료_부족으로_기록되지_않는다(wired, caplog):
    """⚠️ 원장에는 생략 사유를 남기면서 로그만 다른 말을 하면 안 된다."""
    import logging

    from app.pipeline import rejudge_after_lineup

    caplog.set_level(logging.DEBUG, logger="app.pipeline")
    await rejudge_after_lineup(
        {"id": 1, "sport": "kbo"},
        {"status": "confirmed", "notes": [], "home": ["가"], "away": ["다"]})
    txt = "\n".join(r.getMessage() for r in caplog.records)
    assert "재료 부족" not in txt, txt[-400:]
    assert "판정 생략" in txt
