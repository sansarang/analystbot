"""SOC-6 — 축구가 v3 판정 경로에 **연결돼 있지 않았다.**

🔴 **실측 2026-09-12 22:11 (운영 수동 실행, ORDER_V3=1).** 12경기 전부:

     [2단] 12경기 판정 0건 — 재시도 큐 적재
     [judge] 구 Judge 꺼짐(SOCCER_JUDGE_ENABLED=false) — soccer 12경기 판정 없이 반환
     [pipeline] 판정 부착 0건 — 분석 대상 12경기 중 매칭 실패

   원인은 둘이다:
     ① `matchup.judge_matchup` 첫머리 `if sport not in BASEBALL_SPORTS: return None`
     ② 파이프라인이 `sport in BASEBALL_SPORTS` 일 때만 매치업 러너를 부른다
        (`_run_baseball_matchups` — 이름 그대로 야구 전용)

   SOC-1(수집 채널 표)·SOC-2(3-way)로 v3 **안쪽**은 축구를 받을 준비가 됐는데,
   그 문 앞까지 오는 길이 없었다.

⚠️ ORDER_V3 가 꺼져 있으면 축구는 **종전 그대로** 구 Judge 경로다.
   v3 아래쪽 경로(`render_matchup_prompt` 등)는 야구 모양이라 축구가 들어가면 안 된다.
"""

import inspect

import pytest


def _jg(sport="soccer"):
    return {"sport": sport, "game_id": 1, "league": "세리에A",
            "home": "SS Lazio", "away": "AC Milan", "status": "scheduled"}


class _S:
    order_v3 = True
    order_v2 = False
    mock_judge = False
    matchup_model = "x"


@pytest.mark.asyncio
async def test_v3가_켜지면_축구가_v3로_간다(monkeypatch):
    from app.engine import matchup as M

    seen = {}

    async def _v3(jg, redis, date, *, final, pool=None):
        seen["sport"] = jg.get("sport")
        return {"ok": True}

    monkeypatch.setattr(M, "_judge_v3", _v3)
    monkeypatch.setattr(M, "get_settings", lambda: _S())
    out = await M.judge_matchup(_jg(), None, "2026-09-13")
    assert out == {"ok": True}, out
    assert seen["sport"] == "soccer"


@pytest.mark.asyncio
async def test_v3가_꺼지면_축구는_종전대로_거절된다(monkeypatch):
    """🔴 반대 위험 — v3 아래 경로는 야구 모양이다. 축구가 새면 안 된다."""
    from app.engine import matchup as M

    class _Off(_S):
        order_v3 = False

    monkeypatch.setattr(M, "get_settings", lambda: _Off())
    assert await M.judge_matchup(_jg(), None, "2026-09-13") is None


@pytest.mark.asyncio
async def test_축구_말고_다른_종목은_여전히_거절된다(monkeypatch):
    from app.engine import matchup as M

    monkeypatch.setattr(M, "get_settings", lambda: _S())
    for sport in ("tennis", "nba", ""):
        assert await M.judge_matchup(_jg(sport), None, "2026-09-13") is None, sport


@pytest.mark.asyncio
async def test_야구는_v3든_아니든_들어간다(monkeypatch):
    from app.engine import matchup as M

    seen = []

    async def _v3(jg, redis, date, *, final, pool=None):
        seen.append(jg.get("sport"))
        return {"ok": True}

    monkeypatch.setattr(M, "_judge_v3", _v3)
    monkeypatch.setattr(M, "get_settings", lambda: _S())
    for sport in ("kbo", "npb", "mlb"):
        await M.judge_matchup(_jg(sport), None, "2026-09-13")
    assert seen == ["kbo", "npb", "mlb"], seen


# ── 파이프라인 쪽 배선

@pytest.mark.asyncio
async def test_축구_러너가_경기마다_판정을_부른다(monkeypatch):
    from app import pipeline as P

    called = []

    async def _jm(jg, redis, date, **kw):
        called.append(jg["game_id"])
        return {"승자": jg["home"]}

    monkeypatch.setattr("app.engine.matchup.judge_matchup", _jm)
    games = [{"sport": "soccer", "game_id": i, "home": "H", "away": "A"}
             for i in (1, 2, 3)]
    n = await P._run_soccer_matchups(None, "2026-09-13", games)
    assert n == 3 and called == [1, 2, 3], (n, called)


@pytest.mark.asyncio
async def test_한_경기가_터져도_나머지가_산다(monkeypatch, caplog):
    import logging

    from app import pipeline as P

    async def _jm(jg, redis, date, **kw):
        if jg["game_id"] == 2:
            raise RuntimeError("boom")
        return {"승자": "H"}

    monkeypatch.setattr("app.engine.matchup.judge_matchup", _jm)
    games = [{"sport": "soccer", "game_id": i, "home": "H", "away": "A"}
             for i in (1, 2, 3)]
    with caplog.at_level(logging.WARNING):
        n = await P._run_soccer_matchups(None, "2026-09-13", games)
    assert n == 2, n
    assert "game=2" in caplog.text, caplog.text


def test_축구_러너가_야구_부착을_부르지_않는다():
    """🔴 축구에는 선발도 타자도 불펜도 없다. 부르면 시간만 쓴다."""
    src = inspect.getsource(__import__("app.pipeline", fromlist=["x"])
                            ._run_soccer_matchups)
    for bad in ("attach_starter_recent", "attach_batter_recent",
                "bullpen_recent", "team_elo", "attach_material10"):
        assert bad not in src, bad


def test_파이프라인이_축구를_축구_러너로_보낸다():
    """🔴 배선이 없으면 위 계약이 다 통과해도 운영에서는 0건이다."""
    src = inspect.getsource(__import__("app.pipeline", fromlist=["x"])
                            .build_analysis)
    assert "_run_soccer_matchups" in src
