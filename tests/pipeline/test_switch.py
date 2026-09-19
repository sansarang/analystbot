"""[v1.4 STEP 13] 운영 경로 전환 계약 — **두 경로가 동시에 카드를 내지 않는다.**

🔴 지시문 STEP 13: 스위치가 true 면 기존 발송은 **반드시 skip** 한다.
   동시에 나가면 실패다 — 사용자는 같은 경기 카드를 두 장 받는다.
🔴 **기본은 꺼짐**이다. 켜기 전 24h 기존 동작을 관측한다(지시문 §7).
🔴 되돌림은 스위치 하나다 — 코드를 되돌릴 필요가 없다.
"""
from __future__ import annotations

import pytest

from app.engine import pregame_push as PP


class _Redis:
    def __init__(self):
        self.store: dict = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, **kw):
        self.store[k] = v

    async def incr(self, k):
        self.store[k] = int(self.store.get(k, 0)) + 1
        return self.store[k]

    async def expire(self, k, s):
        return True

    async def hincrby(self, k, f, n=1):
        self.store.setdefault(k, {})
        self.store[k][f] = int(self.store[k].get(f, 0)) + n
        return self.store[k][f]


def _row(**kw):
    from datetime import UTC, datetime, timedelta

    return dict({"id": 1, "sport": "kbo",
                 "starts_at": datetime.now(UTC) + timedelta(minutes=40)}, **kw)


def test_스위치는_기본_꺼짐이다():
    """🔴 배포해도 무해해야 한다 — 켜는 것은 사람이 한다."""
    from app.config import get_settings

    assert get_settings().pipeline_v14 is False


@pytest.mark.asyncio
async def test_스위치가_켜지면_기존_발송이_비킨다(monkeypatch):
    from app import config as C

    class _S:
        pipeline_v14 = True

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    got = await PP.send_game_prediction(_Redis(), _row(), "2026-09-18")
    assert got == "skipped"


@pytest.mark.asyncio
async def test_사유를_남기고_비킨다(monkeypatch):
    """🔴 조용한 0 금지 — "왜 안 나갔나"가 집계에 남아야 한다."""
    from app import config as C
    from app.engine import dispatch_stats as ds

    reasons: list = []

    class _S:
        pipeline_v14 = True

    async def _rec(redis, sport, date, reason):
        reasons.append(reason)

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    monkeypatch.setattr(ds, "record", _rec)
    await PP.send_game_prediction(_Redis(), _row(), "2026-09-18")
    assert reasons == ["pipeline_v14"], reasons


@pytest.mark.asyncio
async def test_스위치가_꺼지면_종전대로_간다(monkeypatch):
    """🔴 반대 위험 — 꺼진 상태에서 동작이 바뀌면 되돌림이 불가능해진다.

    ⚠️ 종전 경로의 **첫 관문**은 `SPORTS` 다. 스위치가 꺼져 있으면 그 관문까지
       가야 한다 — `pipeline_v14` 사유로 빠지면 안 된다.
    """
    from app import config as C
    from app.engine import dispatch_stats as ds

    reasons: list = []

    class _S:
        pipeline_v14 = False

    async def _rec(redis, sport, date, reason):
        reasons.append(reason)

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    monkeypatch.setattr(ds, "record", _rec)
    await PP.send_game_prediction(_Redis(), _row(sport="없는종목"), "2026-09-18")
    assert reasons == ["not_supported"], reasons


def test_배타_가드가_SPORTS_관문보다_앞에_있다():
    """🔴 뒤에 두면 `SPORTS` 에 없는 종목이 먼저 걸러져 스위치가 안 듣는다."""
    import inspect

    src = inspect.getsource(PP.send_game_prediction)
    code = "\n".join(ln for ln in src.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    assert code.index("pipeline_v14") < code.index("sport not in SPORTS")


# ── [2026-09-18 페이블 검토] ⑤ 섀도 스위치 · 스케줄러 다리

def test_SEND_스위치도_기본_꺼짐이다():
    from app.config import get_settings

    assert get_settings().pipeline_v14_send is False


@pytest.mark.asyncio
async def test_섀도면_끝까지_가도_보내지_않는다(monkeypatch):
    """🔴 24h 관측이 §7 의 전제인데 그때 카드가 나가면 관측이 아니다."""
    from app import config as C
    from app.flow.ctx import Ctx
    from app.flow.nodes import n13_send
    from app.flow.state import State

    class _S:
        pipeline_v14 = True
        pipeline_v14_send = False

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    sent: list = []
    st = State.new({"game_id": "1", "sport": "baseball", "league": "KBO",
                    "home": "한화", "away": "삼성"})
    st.pick_side = "away"
    st.n11_value = {"pick_type": "승패", "structure": None}
    st.n02_market = {"odds": {"away": 1.35}}
    st.n08_pcode = {"p_code_pick": 0.71}
    st.n09_conf = {"grade": "B"}
    st.n12_text = {"sentences": ["1", "2", "3", "4"]}
    st.n05_evidence = []
    st = await n13_send.run(st, Ctx(inject={"send": lambda t: sent.append(t) or True}))
    assert sent == [], sent
    assert st.n13_send == {"sent": False, "message_id": None, "why": "섀도"}


@pytest.mark.asyncio
async def test_SEND가_켜지면_보낸다(monkeypatch):
    from app import config as C
    from app.flow.ctx import Ctx
    from app.flow.nodes import n13_send
    from app.flow.state import State

    class _S:
        pipeline_v14 = True
        pipeline_v14_send = True

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    sent: list = []
    st = State.new({"game_id": "1", "sport": "baseball", "league": "KBO",
                    "home": "한화", "away": "삼성"})
    st.pick_side = "away"
    st.n11_value = {"pick_type": "승패", "structure": None}
    st.n02_market = {"odds": {"away": 1.35}}
    st.n08_pcode = {"p_code_pick": 0.71}
    # ⚠️ [FIX-5 2026-09-20] 승패 픽 발송 조건 grade==A. 이 테스트가 재는 것은
    #    **스위치**이므로 등급만 올린다.
    st.n09_conf = {"grade": "A"}
    st.n12_text = {"sentences": ["1", "2", "3", "4"]}
    st.n05_evidence = []
    st = await n13_send.run(st, Ctx(inject={"send": lambda t: sent.append(t) or True}))
    assert len(sent) == 1 and st.n13_send["sent"] is True


@pytest.mark.asyncio
async def test_스위치가_꺼지면_다리가_즉시_돌아온다(monkeypatch):
    """🔴 배포해도 무해해야 한다 — 꺼진 상태에서 경기를 한 건도 돌리지 않는다."""
    from app import config as C
    from app.flow.bridge import run_slate

    class _S:
        pipeline_v14 = False

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    got = await run_slate(None, None, [{"id": 1, "sport": "kbo"}])
    assert got["games"] == 0 and got["why"] == "스위치 꺼짐"


@pytest.mark.asyncio
async def test_다리가_멈춤_사유를_사유별로_센다(monkeypatch):
    """🔴 조용한 0 금지 — 24h 섀도 보고의 대상이 이 분포다."""
    from app import config as C
    from app.flow import bridge as B

    class _S:
        pipeline_v14 = True
        pipeline_v14_send = False

    class _St:
        def __init__(self, reason):
            self.stop_reason = reason
            self.n13_send = None

    calls = []

    async def _run_game(game, ctx):
        calls.append(game["game_id"])
        return _St("n03_freeze" if game["game_id"] == 1 else None)

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    monkeypatch.setattr("app.flow.run.run_game", _run_game)
    got = await B.run_slate(None, None,
                            [{"id": 1, "sport": "kbo", "starts_at": None},
                             {"id": 2, "sport": "kbo", "starts_at": None}])
    assert got["games"] == 2 and calls == [1, 2]
    assert got["stopped"] == {"n03_freeze": 1, "완주": 1}, got


def test_스케줄러가_다리를_부른다():
    """🔴 STEP 13 을 처음 붙일 때 가드만 걸고 호출을 안 이었다 — 그러면
    스위치가 "새 경로를 켠다"가 아니라 "카드를 끈다"가 된다.

    🔴 [2026-09-19 실사고] 그다음엔 호출을 **폴링 창 안에** 넣었다. 창이
       닫힌 시간대에는 그 함수가 조기 반환해 **12시간 동안 한 번도 안 돌았다**.
       관측은 창과 무관해야 한다 — 전용 잡으로 옮겼다.
    """
    import pathlib

    src = pathlib.Path("app/scheduler.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    assert "async def flow_shadow_job" in code
    assert "from app.flow.bridge import run_today" in code
    assert "await run_today(" in code
    # 🔴 잡 목록에 등록돼 있어야 실제로 돈다 — 함수만 있으면 죽은 코드다.
    assert '("flow_shadow_15m", flow_shadow_job' in code
    # ⚠️ 창 안 호출은 **없어야** 한다(두 곳에서 돌면 예산이 두 배로 샌다).
    assert "await run_slate(" not in code


@pytest.mark.asyncio
async def test_섀도잡은_스위치가_꺼지면_아무것도_안_한다(monkeypatch):
    """🔴 배포해도 무해해야 한다 — 꺼진 상태에서 Redis 도 열지 않는다."""
    import app.scheduler as S

    opened = []

    class _S:
        pipeline_v14 = False
        redis_url = "redis://x"

    monkeypatch.setattr(S, "get_settings", lambda: _S())
    monkeypatch.setattr(S.aioredis, "from_url",
                        lambda *a, **k: opened.append(1))
    await S.flow_shadow_job()
    assert opened == [], "스위치가 꺼졌는데 Redis 를 열었다"


@pytest.mark.asyncio
async def test_run_today는_창에_매이지_않는다():
    """🔴 실사고의 핵심 — 슬레이트를 **직접** 조회한다."""
    import inspect

    from app.flow import bridge as B

    # ⚠️ **주석이 아니라 실행 줄만 본다.** 머리말에 "창(window)에 매이지
    #    않는다"고 설명해 둔 것을 결함으로 세면 설명을 못 쓰게 된다.
    import ast

    tree = ast.parse(inspect.getsource(B.run_today))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree)
    assert "_SLATE_SQL" in code
    for banned in ("window", "poll", "updated"):
        assert banned not in code, f"창 개념에 매여 있다: {banned}"


# ── [2026-09-19 실사고] 카드의 목구멍에 걸어야 한다

@pytest.mark.asyncio
async def test_V14면_어떤_카드도_나가지_않는다(monkeypatch):
    """🔴 실사고 2026-09-19: 섀도인데 **판정 불가 카드 7장이 나갔다**
    (10085~10091). 가드를 `send_game_prediction` 에만 걸었는데 그 카드는
    `send_unavailable_card` 라는 다른 경로였다.

    관문을 함수 하나에 걸면 **다른 문으로 나간다.** 목구멍에 건다.
    """
    from app import notify as N
    from app.config import get_settings
    from app.engine import pregame_push as P

    sent: list = []

    async def _tg(text, **kw):
        sent.append(text)
        return True

    monkeypatch.setattr(N, "send_telegram", _tg)
    monkeypatch.setattr(P, "_notify_mod", N)

    class _S:
        pipeline_v14 = True

    monkeypatch.setattr("app.config.get_settings", lambda: _S())
    assert await P._send_card("아무 카드") is False
    assert sent == [], sent


@pytest.mark.asyncio
async def test_스위치가_꺼지면_카드는_나간다(monkeypatch):
    """🔴 반대 위험 — 꺼진 상태에서 발송이 막히면 그게 더 큰 사고다."""
    from app import notify as N
    from app.engine import pregame_push as P

    sent: list = []

    async def _tg(text, **kw):
        sent.append(text)
        return True

    monkeypatch.setattr(N, "send_telegram", _tg)
    monkeypatch.setattr(P, "_notify_mod", N)

    class _S:
        pipeline_v14 = False

    monkeypatch.setattr("app.config.get_settings", lambda: _S())
    assert await P._send_card("아무 카드") is True
    assert len(sent) == 1


def test_발송_경로가_전부_목구멍을_지난다():
    """🔴 `_send_card` 를 우회해 `send_telegram` 을 직접 부르는 자리가 없어야 한다."""
    import pathlib
    import re

    src = pathlib.Path("app/engine/pregame_push.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    # `_send_card` 본문 안의 두 호출만 허용한다.
    calls = re.findall(r"_notify_mod\.send_telegram", code)
    assert len(calls) == 2, f"목구멍 밖에서 텔레그램을 부른다: {len(calls)}곳"
