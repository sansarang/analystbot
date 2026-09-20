"""[STOP-1 / STEP 1-b] 멈춤 사유가 ⑬ 에 안 남는다.

🔴 실측 2026-09-20: 오늘 슬레이트 32경기 중 `n13_send.why` 가 **전건 null**.
   ⑬ 까지 간 경기가 없어 `n13_send` **행 자체가 없기** 때문이다.
   `stop_reason` 은 `finish` 스냅샷의 JSON 안에만 있고 `analysis_runs` 에
   **칸이 없어** 집계하려면 전 행을 파싱해야 했다.

🔴 STEP 1-b 요구:
     · `analysis_runs` 에 `stopped_at`(노드)·`stop_reason`(코드) **칸**을 둔다.
     · ⑬ 에 도달하지 못한 경기는 `n13.why = "미도달:<stopped_at>"`.
"""
from __future__ import annotations

import pathlib

import pytest

SCHEMA = pathlib.Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def test_analysis_runs에_멈춤_칸이_있다():
    s = SCHEMA.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS stopped_at" in s, "stopped_at 칸이 없다"
    assert "ADD COLUMN IF NOT EXISTS stop_reason" in s, "stop_reason 칸이 없다"


@pytest.mark.asyncio
async def test_13에_못_가면_미도달로_남는다():
    """🔴 조용한 null 금지 — "안 보냈다"와 "거기까지 못 갔다"는 다르다."""
    from app.flow import run as R
    from app.flow.state import State

    st = State.new({"game_id": "g", "sport": "baseball", "league": "KBO",
                    "home": "한화", "away": "삼성"})
    st.trace = ["n01_prior", "n02_market", "n03_gate"]
    st = await R.finish(st, "n03_freeze", None)
    assert st.n13_send is not None, "⑬ 칸이 비어 있다"
    assert st.n13_send.get("why") == "미도달:n03_gate", st.n13_send
    assert st.n13_send.get("sent") is False
    assert st.stopped_at == "n03_gate", st.stopped_at


@pytest.mark.asyncio
async def test_13까지_간_경기는_why를_덮지_않는다():
    """⚠️ 반대 위험 — ⑬ 가 적은 사유를 '미도달'로 지우면 안 된다."""
    from app.flow import run as R
    from app.flow.state import State

    st = State.new({"game_id": "g", "sport": "baseball", "league": "KBO",
                    "home": "한화", "away": "삼성"})
    st.trace = ["n01_prior", "n13_send"]
    st.n13_send = {"sent": False, "message_id": None, "why": "섀도"}
    st = await R.finish(st, None, None)
    assert st.n13_send["why"] == "섀도", st.n13_send


@pytest.mark.asyncio
async def test_멈춤_칸이_행에_쓰인다():
    """🔴 칸만 만들고 안 채우면 그대로다 — `finish` 가 그 run 전체를 갱신한다."""
    import inspect

    from app.flow import run as R

    src = "\n".join(ln for ln in inspect.getsource(R.finish).splitlines()
                    if ln.strip() and not ln.strip().startswith("#"))
    assert "UPDATE analysis_runs" in src, "finish 가 멈춤 칸을 쓰지 않는다"
