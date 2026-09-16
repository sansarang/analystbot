"""MOV-2 — 배당 이동 분류 배선.

🔴 실측 결함 2026-09-14: `MOV-1` 이 분류 규칙을 만들었는데 **부르는 곳이
   0** 이었다. `pick_ledger.move_class`·`odds_open` 은 영원히 NULL 이었고,
   Part 1-B-4(확증·취소)가 읽을 값이 없었다.

⚠️ 소스 문자열 grep 으로 배선을 단언하지 않는다 — 주석 한 줄이 테스트를
   통과시킨다. 호출은 **AST** 로, 동작은 **실제 실행**으로 확인한다.
"""
import ast
import inspect
from datetime import UTC, datetime

import pytest

from app.engine import odds_move as M
from app.engine import pick_ledger as PL


class _Conn:
    """fetch/fetchrow/execute 를 받아 적는 가짜 커넥션."""

    def __init__(self, snaps, pick=None):
        self.snaps = snaps
        self.pick = pick or {"favored": "home", "p_home": 0.55,
                             "predicted_side": None}
        self.executed: list[tuple] = []

    async def fetch(self, sql, *args):
        return self.snaps

    async def fetchrow(self, sql, *args):
        return self.pick

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"


def _snap(tag, side, odds, home="H", away="A", provider="oddsportal"):
    return {"provider": provider, "snap_tag": tag, "side": side,
            "odds": odds, "home": home, "away": away}


@pytest.mark.asyncio
async def test_기준선과_최신_시점_사이_이동을_원장에_남긴다():
    # open 2.00/2.00(50%) → lineup 1.60/2.60(약 62%) = 홈 쪽 +12%p
    conn = _Conn([_snap("open", "H", 2.00), _snap("open", "A", 2.00),
                  _snap("lineup", "H", 1.60), _snap("lineup", "A", 2.60)])

    out = await PL.record_move(conn, game_id=7432)

    assert out["from"] == "open" and out["to"] == "lineup"
    assert out["move_pp"] > M.MOVE_MIN_PP
    # 뉴스를 안 넘겼으므로 news 로 분류하면 안 된다(근거 없는 확증 금지).
    assert out["move_class"] == M.MONEY
    saved = [(s, a) for s, a in conn.executed if "SET odds_open" in s]
    assert len(saved) == 1
    _, args = saved[0]
    assert args[0] == 7432
    assert args[1] == 2.00, "odds_open 은 기준선의 **고른 쪽** 배당이다"
    assert args[2] == M.MONEY


@pytest.mark.asyncio
async def test_이름표가_없으면_아무것도_쓰지_않는다():
    """🔴 "모른다"를 `none`(안 움직였다)으로 바꾸지 않는다."""
    conn = _Conn([])

    assert await PL.record_move(conn, game_id=1) is None
    assert not conn.executed


@pytest.mark.asyncio
async def test_기준선_뒤_시점이_없으면_쓰지_않는다():
    conn = _Conn([_snap("open", "H", 2.00), _snap("open", "A", 2.00)])

    assert await PL.record_move(conn, game_id=1) is None
    assert not conn.executed


@pytest.mark.asyncio
async def test_소스를_섞지_않는다():
    """다른 북의 값과 비교하면 이동이 아니라 마진 차를 잰다."""
    conn = _Conn([_snap("open", "H", 2.00, provider="a"),
                  _snap("open", "A", 2.00, provider="a"),
                  _snap("lineup", "H", 1.60, provider="b"),
                  _snap("lineup", "A", 2.60, provider="b")])

    # 소스 a 에는 기준선만, b 에는 lineup 만 있다 → 둘 다 잴 수 없다.
    assert await PL.record_move(conn, game_id=1) is None


def test_판정_기록이_이동_분류를_부른다():
    """AST 로 **실제 호출**을 확인한다 — 주석·문자열은 세지 않는다."""
    tree = ast.parse(inspect.getsource(PL))
    # 🔴 [PA-19 2026-09-16] 호출이 `_record_side_effects` 안으로 한 단계
    #    들어갔다 — `unchanged` 분기와 삽입 분기가 **같은 함수**를 부르게
    #    모았기 때문이다(사본 금지). 뜻은 그대로다: 판정 기록이 이것을 부른다.
    #    그래서 `record_analysis` 본문이 아니라 **호출 사슬**을 본다.
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "record_analysis")
    assert [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "_record_side_effects"], \
        "record_analysis 가 부수 기록을 안 부른다"
    helper = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "_record_side_effects")
    calls = [n for n in ast.walk(helper)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "record_move"]
    assert len(calls) == 1, "record_analysis 가 record_move 를 정확히 한 번 부른다"
    kw = {k.arg for k in calls[0].keywords}
    assert "game_id" in kw
