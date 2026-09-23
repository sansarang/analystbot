"""[OUT-S] 축구 결장자가 **쌓이기만 하고 아무도 안 읽는다.**

사용자 2026-09-23: (① 축구 결장자 읽기 … ④ NPB 라인업) "1,2,3,4 전부다 승인"

🔴 실측 2026-09-23 운영 — `lineups` 표:
```
라리가    transfermarkt injury  20행      EPL   transfermarkt injury  24행
세리에A   transfermarkt injury  22행      분데스  transfermarkt injury  16행
J1 리그   transfermarkt injury  17행      K리그1 transfermarkt injury   7행
덴마크    transfermarkt injury   4행      ─ 합계 110행
  scratches 예: ['César Tárrega — Muscle injury (복귀 예정 05/10/2026)',
                 'Mouctar Diakhaby — …', … 7명]
```
`satellite_soccer` 가 **SOC-10 에서 일부러 남긴 자리**인데(주석: "결장자를 DB에
남긴다 — 제미나이가 DB에서 고른다"), ⑤에는 읽는 코드가 없었다.

🔴 그리고 축구 변수표에 **결장 칸 자체가 없었다**
   (`xi_confirmed`·`form_recent5`·`rotation_risk`·`travel`·`motivation`).
   CLAUDE.md 규약대로 **`config/rules.yaml` 에 변수를 넣고 노드가 읽게** 한다 —
   노드에 이름을 손으로 적지 않는다.

⚠️ `max_abs` 는 **미검증 사전값**이다. 야구 `lineup_out` 2.5 를 그대로 놓았고,
   채점이 쌓이기 전에는 고치지 않는다(고치면 측정이 아니라 취향이다).
"""
from __future__ import annotations

import inspect

import pytest

from app.flow.nodes import n05_evidence as N5

SCRATCH = ["César Tárrega — Muscle injury (복귀 예정 05/10/2026)",
           "Mouctar Diakhaby — Cruciate ligament injury",
           "Pablo Marín — Muscle injury"]


def test_축구_변수표에_결장이_있다():
    """🔴 원본은 `config/rules.yaml` 하나다 — 노드에 이름을 적지 않는다."""
    from app.flow import rules as FR

    v = FR.vars_for("soccer")
    assert "lineup_out" in v, f"축구 변수표: {sorted(v)}"
    assert float(v["lineup_out"]["max_abs"]) > 0


def test_야구_변수표는_안_바뀌었다():
    """⚠️ 반대 위험."""
    from app.flow import rules as FR

    b = FR.vars_for("baseball")
    # 🔴 [NWS-D 2026-09-23 사용자 지시] `news_injury` 를 **더했다** —
    #    "부상이나 다른 문제가 있으면 예측에 무조건 좌우되어야 한다".
    #    ⚠️ 집합을 느슨하게 하지 않았다 — 여전히 **정확한 목록**을 요구한다.
    #       변수를 몰래 늘리면 이 계약이 깨져야 한다.
    # 🔴 [LOAD-1 2026-09-23 사용자 지시] `play_load`(출전 부하)를 더했다 —
    #    "출전부하도 배선에 넣어라". ⚠️ 축구는 안 더했다(자료 없음).
    assert set(b) == {"starter_recent3", "bullpen_3d", "lineup_out",
                      "travel_backtoback", "park_factor", "weather",
                      "news_injury", "play_load"}, sorted(b)


def _pool(rows):
    class _P:
        async def fetch(self, sql, *a):
            return rows if "lineups" in sql else []
    return _P()


async def _run(rows, *, side="home", league="EPL", sport="soccer"):
    from app.flow.ctx import Ctx
    from app.flow.state import State

    st = State.new({"id": "1", "sport": sport, "league": league,
                    "home": "A", "away": "B",
                    "starts_at": "2026-09-20T18:00:00+00:00"})
    st.sport = sport
    st.pick_side = side
    st.n04_hyp = [{"id": "H", "vars": [{"var": "lineup_out", "is_core": False}]}]
    out = await N5.run(st, Ctx(pool=_pool(rows)))
    return [e for e in (out.n05_evidence or []) if e["var"] == "lineup_out"]


@pytest.mark.asyncio
async def test_우리쪽_결장자를_읽는다():
    rows = [{"side": "home", "status": "injury", "source": "transfermarkt",
             "starter": None, "batting_order": [], "scratches": SCRATCH,
             "captured_at": None}]
    got = await _run(rows)
    assert got, "결장자 110행이 쌓여 있는데 증거가 비었다"
    assert len(got[0]["value"]) == 3, got[0]["value"]
    assert "db:lineups" in got[0]["source"]
    assert "Tárrega" in got[0]["raw_excerpt"]


@pytest.mark.asyncio
async def test_상대쪽_결장자를_우리것으로_쓰지_않는다():
    """🔴 방향이 뒤집힌다 — 상대 결장은 **우리에게 호재**다."""
    rows = [{"side": "away", "status": "injury", "source": "transfermarkt",
             "starter": None, "batting_order": [], "scratches": SCRATCH,
             "captured_at": None}]
    got = await _run(rows, side="home")
    assert not got, f"상대 결장을 우리 칸에 실었다: {got}"


@pytest.mark.asyncio
async def test_결장_0명은_증거가_아니다():
    """⚠️ 빈 목록은 ⑥ 규약상 `refuted`("봤는데 없다")다. transfermarkt 가
    빈손인 것과 "결장자가 정말 0명"인 것을 우리는 **구분할 수 없다** —
    그러면 싣지 않는다(미상)."""
    rows = [{"side": "home", "status": "injury", "source": "transfermarkt",
             "starter": None, "batting_order": [], "scratches": [],
             "captured_at": None}]
    assert await _run(rows) == []


@pytest.mark.asyncio
async def test_문자열_JSON_도_읽는다():
    """⚠️ asyncpg 가 jsonb 를 문자열로 줄 때가 있다."""
    import json

    rows = [{"side": "home", "status": "injury", "source": "transfermarkt",
             "starter": None, "batting_order": "[]",
             "scratches": json.dumps(SCRATCH, ensure_ascii=False),
             "captured_at": None}]
    assert len(((await _run(rows)) or [{}])[0].get("value") or []) == 3


@pytest.mark.asyncio
async def test_야구는_이_경로로_가지_않는다():
    """🔴 야구 `lineup_out` 은 종전 경로(위성+공식)가 낸다 — 건드리지 않는다."""
    rows = [{"side": "home", "status": "injury", "source": "transfermarkt",
             "starter": None, "batting_order": [], "scratches": SCRATCH,
             "captured_at": None}]
    assert await _run(rows, league="KBO", sport="baseball") == []


def test_읽기가_한_함수다():
    """🔴 사본 금지 — XI 와 결장자가 **같은 조회**를 쓴다(경기당 1질의)."""
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(N5).splitlines())
    # 질의문은 한 벌이다(정의 1곳) — 두 벌이면 한쪽이 뒤처진다.
    assert src.count("SELECT l.side") == 1, "라인업 질의가 두 벌이다"
    # XI 와 결장자가 **같은 조회**를 쓴다 — 두 분기가 같은 함수를 부른다.
    # ⚠️ `await` 를 붙여 **호출만** 센다 — 안 붙이면 `async def _xi_rows(...)`
    #    정의 줄까지 세어 3이 나온다(처음에 그래서 거짓 실패했다).
    # ⚠️ **주석과 독스트링을 뗀다.** `_XI_SQL` 을 설명하는 독스트링이 원문
    #    grep 에 걸린다 — `#` 만 떼는 것으로는 부족하다(D46, 15회째).
    #    `ast.unparse` 가 주석을 버리고, 아래가 독스트링을 버린다.
    import ast as _ast

    _tree = _ast.parse(src)
    for _n in _ast.walk(_tree):
        _b = getattr(_n, "body", None)
        if _b and isinstance(_b, list):
            _f = _b[0]
            if (isinstance(_f, _ast.Expr) and isinstance(_f.value, _ast.Constant)
                    and isinstance(_f.value.value, str)):
                _b.pop(0)
    code = _ast.unparse(_tree)
    assert code.count("_XI_SQL") == 2, "라인업 SQL 이 두 곳 이상이다(사본)"
    assert code.count("FROM lineups") == 1, "lineups 를 따로 조회하는 곳이 있다"
    assert "_xi_memo" in code, "조회를 기억하지 않는다 — 경기당 1질의가 깨진다"
    assert code.count("await _xi_rows(state, ctx)") >= 2, "접근자를 안 쓴다"
    assert "_scratches_of" in src
