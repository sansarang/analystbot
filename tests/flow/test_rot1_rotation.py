"""[ROT-1] `rotation_risk` 를 **일정에서 계산한다.** 기사에 묻지 않는다.

사용자 2026-09-23: "1,2,3,4 전부다 승인" (② rotation_risk — 일정으로 계산)

🔴 실측 — 최근 3일 축구 `rotation_risk` **305건 전건 미상**이었다.
   소스가 위성 추출 상자(`midweek`)뿐인데 LLM 을 0 으로 만든 뒤로 그 상자가
   비어 있다. 그런데 "직전 며칠 안에 경기를 했는가"는 **`games` 표에 있다** —
   외부 요청도 LLM 도 필요 없다.

🔴 **휴식이 호재라고 적지 않는다.** 확인되는 것은 "직전 경기가 있었다"(피로)
   뿐이다. "푹 쉬어서 유리하다"는 미검증이고, 그것까지 조정에 넣으면 근거
   없는 방향이 붙는다.
     · 창 안에 경기 있음  → `confirmed` · 방향 −1(피로)
     · 없음               → 빈 목록 = ⑥ 규약상 `refuted`("봤는데 없다") ·
                            ⑦은 `confirmed` 에만 움직이므로 **조정 0**
   조용한 0 을 만들지 않으려고 "없음"도 원문 한 줄을 남긴다.

⚠️ 창(시간)의 원본은 `config/rules.yaml` 하나다 — 코드에 숫자를 박지 않는다.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.flow.nodes import n05_evidence as N5

KICK = datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)


def _pool(rows):
    class _P:
        def __init__(self):
            self.sql = []

        async def fetch(self, sql, *a):
            self.sql.append((sql, a))
            if "starts_at <" in sql and "lineups" not in sql:
                return rows
            return []
    return _P()


async def _run(rows, *, sport="soccer", league="EPL", side="home"):
    from app.flow.ctx import Ctx
    from app.flow.state import State

    st = State.new({"id": "1", "sport": sport, "league": league,
                    "home": "A", "away": "B", "starts_at": KICK.isoformat()})
    st.sport = sport
    st.hyp_side = st.pick_side = side   # [SIDE-2] ⑤는 조사 방향을 본다
    st.n04_hyp = [{"id": "H", "vars": [{"var": "rotation_risk"}]}]
    out = await N5.run(st, Ctx(pool=_pool(rows)))
    return [e for e in (out.n05_evidence or []) if e["var"] == "rotation_risk"]


@pytest.mark.asyncio
async def test_창_안에_경기가_있으면_확인이다():
    rows = [{"home": "A", "away": "C", "starts_at": KICK - timedelta(hours=70),
             "league": "EPL"}]
    got = await _run(rows)
    assert got, "직전 경기가 있는데 증거가 비었다"
    assert got[0]["value"], got[0]
    assert got[0]["direction"] == -1, "피로는 악재다"
    assert "db:games" in got[0]["source"]


@pytest.mark.asyncio
async def test_없으면_반증이되_원문을_남긴다():
    """🔴 조용한 0 금지 — "안 봤다"와 "봤는데 없다"를 가른다."""
    got = await _run([])
    assert got, "없음을 조용히 버렸다"
    assert got[0]["value"] == [], got[0]
    assert got[0]["raw_excerpt"], "원문이 비면 ⑤가 그 행을 버린다"


@pytest.mark.asyncio
async def test_없음이_호재로_바뀌지_않는다():
    """🔴 "푹 쉬어서 유리하다"는 미검증이다 — 방향을 붙이지 않는다."""
    got = await _run([])
    # ⚠️ `_row` 의 기본 방향은 `{}` 다(팀별 dict). 빈 것이면 방향 없음이다.
    assert not got[0].get("direction"), got[0]


@pytest.mark.asyncio
async def test_우리쪽만_본다():
    """⚠️ 상대의 피로는 우리에게 호재다 — 우리 칸에 실으면 방향이 뒤집힌다."""
    rows = [{"home": "A", "away": "C", "starts_at": KICK - timedelta(hours=70),
             "league": "EPL"}]
    seen = _pool(rows)

    from app.flow.ctx import Ctx
    from app.flow.state import State

    st = State.new({"id": "1", "sport": "soccer", "league": "EPL",
                    "home": "A", "away": "B", "starts_at": KICK.isoformat()})
    st.sport, st.hyp_side, st.pick_side = "soccer", "away", "away"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "rotation_risk"}]}]
    await N5.run(st, Ctx(pool=seen))
    args = [a for sql, a in seen.sql if "starts_at <" in sql and "lineups" not in sql]
    assert args and "B" in args[0], f"픽이 원정인데 홈 팀을 물었다: {args}"


@pytest.mark.asyncio
async def test_그_경기_자신은_세지_않는다():
    """⚠️ 킥오프 **이전**만 센다. 자기 자신을 세면 전건이 confirmed 가 된다."""
    from app.flow.ctx import Ctx
    from app.flow.state import State

    seen = _pool([])
    st = State.new({"id": "1", "sport": "soccer", "league": "EPL",
                    "home": "A", "away": "B", "starts_at": KICK.isoformat()})
    st.sport, st.hyp_side, st.pick_side = "soccer", "home", "home"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "rotation_risk"}]}]
    await N5.run(st, Ctx(pool=seen))
    sql = [s for s, _ in seen.sql if "starts_at <" in s and "lineups" not in s]
    assert sql and "starts_at <" in sql[0]
    assert "status" in sql[0], "취소된 경기까지 세면 안 된다"


def test_창의_원본이_설정이다():
    """🔴 사본 금지 — 설정을 바꾸면 **질의가 실제로 바뀐다.**

    ⚠️ 원문에서 숫자를 찾는 대리검사는 쓰지 않았다. 폴백 상수는 이 저장소의
       관례이고(`R.get(..., 5) or 5`), 그걸 금지하면 거짓 실패가 된다.
       중요한 것은 **config 가 동작을 지배하는가**다 — 그래서 불러서 본다.
    """
    from app.flow import rules as R

    assert R.get("rotation_window_h") is not None
    src = inspect.getsource(N5._recent_match)
    assert "rotation_window_h" in src


@pytest.mark.asyncio
async def test_설정을_바꾸면_질의가_바뀐다(monkeypatch):
    from app.flow import rules as R
    from app.flow.ctx import Ctx
    from app.flow.state import State

    monkeypatch.setattr(
        R, "get", lambda k, d=None: 12 if k == "rotation_window_h" else d)
    seen = _pool([])
    st = State.new({"id": "1", "sport": "soccer", "league": "EPL",
                    "home": "A", "away": "B", "starts_at": KICK.isoformat()})
    st.sport, st.hyp_side, st.pick_side = "soccer", "home", "home"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "rotation_risk"}]}]
    await N5.run(st, Ctx(pool=seen))
    args = [a for sql, a in seen.sql
            if "starts_at <" in sql and "lineups" not in sql]
    assert args and args[0][3] == 12.0, args


@pytest.mark.asyncio
async def test_킥오프를_모르면_묻지_않는다():
    """⚠️ 기준 시각이 없으면 창을 만들 수 없다 — 미상이다."""
    from app.flow.ctx import Ctx
    from app.flow.state import State

    seen = _pool([])
    st = State.new({"id": "1", "sport": "soccer", "league": "EPL",
                    "home": "A", "away": "B", "starts_at": None})
    st.sport, st.hyp_side, st.pick_side = "soccer", "home", "home"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "rotation_risk"}]}]
    out = await N5.run(st, Ctx(pool=seen))
    assert [e for e in (out.n05_evidence or [])
            if e["var"] == "rotation_risk"] == []
