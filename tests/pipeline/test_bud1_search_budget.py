"""[BUD-1 / STEP 1-a] 검색 예산이 **뒤 경기를 굶겼다.**

🔴 실측 2026-09-20 KBO 5경기(슬레이트 예산 10):
     game=1763 요청 3개 → evidence 2건
     game=1767 요청 3개 → evidence 2건
     game=1765 **슬레이트 예산 소진 — 나머지는 미상** · 요청 6개 → evidence 2건
     game=1766 **슬레이트 예산 소진** · 요청 6개 → evidence 0건
     [flow] 슬레이트 5경기 (예산 10/10)

   두산@KT 는 `캐시 결장 3건` 이 **손에 있었는데** 한 변수도 열지 못했다.
   "여섯 변수 전부 미상" 은 자료가 없어서가 아니라 **예산이 없어서**였다.

🔴 원인: ⑤는 변수마다 `ctx.take_search(1)` 을 부르는데(`n05_evidence.py:354`),
   이 노드에는 **기사 fetch 가 없다** — 바깥 호출이 Redis 읽기(`read_extract`·
   판정 캐시)와 DB(`ctx.pool.fetch`)뿐이고 httpx/aiohttp/requests 가 0건이다.
   예산은 **기사 fetch 용**인데 읽기에 쓰고 있었다.
"""
from __future__ import annotations

import inspect

import pytest


def test_n05는_기사를_긁지_않는다():
    """🔴 이 전제가 깨지면 예산을 다시 걸어야 한다(STEP 7-4)."""
    from app.flow.nodes import n05_evidence

    src = "\n".join(ln for ln in inspect.getsource(n05_evidence).splitlines()
                    if ln.strip() and not ln.strip().startswith("#"))
    for bad in ("httpx", "aiohttp", "requests.get", "urlopen"):
        assert bad not in src, f"⑤에 기사 fetch 가 생겼다: {bad}"


def test_DB변수는_예산을_쓰지_않는다():
    """🔴 [STEP 1-a] 예산 차감은 **기사 fetch 에만.** DB·공식 API 는 0."""
    from app.flow.nodes import n05_evidence

    # ⚠️ **주석을 걷어내고 본다.** 내 설명 주석이 스스로 이 검사에 걸린다.
    src = "\n".join(ln for ln in inspect.getsource(n05_evidence.run).splitlines()
                    if ln.strip() and not ln.strip().startswith("#"))
    assert "take_search" not in src, \
        "⑤ 본문이 아직 예산을 차감한다 — DB 조회에 기사 예산을 쓰면 뒤 경기가 굶는다"


@pytest.mark.asyncio
async def test_예산이_0이어도_DB변수는_전부_본다():
    """🔴 완료 조건 — 예산을 0 으로 묶어도 증거가 나와야 한다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence
    from app.flow.state import State

    st = State.new({"game_id": "g", "sport": "baseball", "league": "KBO",
                    "home": "한화", "away": "삼성"})
    st.pick_side = "away"
    st.n03_gate = {"gate": "시장과대"}
    st.n04_hyp = [{"id": "H_fade", "vars": [{"var": "lineup_out", "is_core": True}]}]
    ctx = Ctx(inject={"extract": {"home": {"out": ["한화 A 오늘 라인업에서 빠짐",
                                                  "한화 B 오늘 라인업에서 빠짐"]}},
                      "absences": []},
              budget={"searches": 999, "slate_cap": 1})   # 이미 소진된 예산
    st = await n05_evidence.run(st, ctx)
    got = [e for e in st.n05_evidence if e["var"] == "lineup_out"]
    assert got, f"예산이 없다고 DB·캐시 변수를 굶겼다: {st.n05_evidence}"
