"""[WIR-2] ⑤가 빈손으로 돌아오던 이유 — 주입에만 의존했다.

🔴 실측 2026-09-19: 게이트를 통과한 7경기 전부 `n05_evidence = []` 이고
   ⑥은 여섯 변수 전건 `unknown`, `verdict=모름과반`, `unknown_ratio=1.0`.
   자료가 DB 에 **없어서가 아니다** — 같은 DB 로 만든 내보내기는 적었다:
     선발 Paul Skenes ERA 3.06 · 불펜 3일 홈 18.0이닝 · 결장 홈 4명
🔴 원인은 한 줄이다:
     n05_evidence.py:153  absences = (ctx.inject or {}).get("absences") or []
   그리고 `bridge.py:117` 은 `model_probs` 하나만 주입한다.
   운영에서 `absences`·`starter_notes` 는 **영원히 빈 목록**이었다.
⚠️ 새 수집기를 만들지 않는다. 파이프라인이 이미 만들어 둔 판정 캐시
   (`analysis:{sport}:{date}`)를 읽는다 — 내보내기가 읽는 바로 그 자리다.
"""
from __future__ import annotations

import inspect

import pytest


def test_absences_가_주입에만_매달리지_않는다():
    from app.flow.nodes import n05_evidence as N

    src = inspect.getsource(N)
    assert "_cache_absences" in src, "캐시에서 결장을 읽지 않는다"


def test_MLB_캐시는_미동부_날짜도_본다():
    """🔴 `analysis:mlb:2026-09-19` 는 없고 `…:2026-09-18` 이 있다(실측).
       KST 날짜로만 찾으면 MLB 는 언제나 빈손이다."""
    from app.flow.nodes import n05_evidence as N

    src = inspect.getsource(N._cache_doc)
    assert "days=1" in src or "timedelta" in src, src[:400]


@pytest.mark.asyncio
async def test_캐시에서_결장을_읽어_증거로_만든다():
    import json

    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N
    from app.flow.state import State

    doc = {"games": [{"game_id": "10098", "research": {"absences": [
        "New York Yankees의 Aaron Judge 중심 타선 결장 — 평소 3번, 오늘 라인업에서 빠짐",
    ]}}]}

    class _R:
        async def get(self, k):
            return json.dumps(doc) if k.startswith("analysis:mlb:") else None

    st = State(run_id="r", game_id="10098", sport="baseball", league="MLB",
               home="Arizona Diamondbacks", away="New York Yankees",
               kickoff_utc="2026-09-19T01:40:00Z")
    st.n04_hyp = [{"id": "H", "vars": [{"var": "lineup_out", "is_core": True}]}]
    out = await N.run(st, Ctx(redis=_R()))
    got = out.n05_evidence
    assert got, "캐시에 결장이 있는데 증거가 비었다"
    assert got[0]["var"] == "lineup_out"
    assert "Aaron Judge" in got[0]["raw_excerpt"], got


@pytest.mark.asyncio
async def test_주입이_있으면_캐시를_읽지_않는다():
    """⚠️ 픽스처·드라이런이 먼저다 — 캐시가 그것을 덮으면 테스트가 못 믿을 게 된다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N
    from app.flow.state import State

    hits = []

    class _R:
        async def get(self, k):
            hits.append(k)
            return None

    st = State(run_id="r", game_id="1", sport="baseball", league="MLB",
               home="A", away="B", kickoff_utc="2026-09-19T01:40:00Z")
    st.n04_hyp = [{"id": "H", "vars": [{"var": "lineup_out", "is_core": True}]}]
    await N.run(st, Ctx(redis=_R(), inject={"absences": [], "extract": {}}))
    assert not [k for k in hits if k.startswith("analysis:")], hits


def test_기사는_증거가_되지_않는다():
    """🔴 가설 변수 목록에 없는 것은 증거로 안 들어간다 — 트랜잭션 기사가
       채점 분모에 섞이면 `모름과반` 이 아니라 **틀린 확인**이 된다."""
    from app.flow.nodes import n05_evidence as N

    src = inspect.getsource(N.run)
    assert "wanted" in src
    assert "for var in wanted" in src, "화이트리스트를 돌지 않는다"
