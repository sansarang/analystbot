"""[MOV-T7] 가격이 움직이면 조사한다.

사용자 2026-09-22: "종가 시작가는 이상 흐름이어서 가격 변동이 있다.
**이유를 찾으면 된다**."

🔴 실측 2026-09-22 — 이 트리거가 없어서 생긴 결과:
```
3%p 이상 움직인 20경기  →  **20/20 전부 "뉴스 근거 없음"**
  g1752 KT@한화 16.62%p · g1750 SSG@롯데 7.66%p · g9479 소뱅@오릭스 6.29%p
딥서치 로그: 발동=True · **검색=0** · status=capped/failed
```
`odds_move.classify` 가 스스로 적고 있었다 —
`"{pp}%p 이동 — 뉴스 근거 없음(**딥서치 미실행** 또는 무소득)"`.

원인: `T2_시장괴리` 는 **우리 확률 vs 시장**의 차이지 시간에 따른 이동이 아니다.
가격 이동을 방아쇠로 쓰는 트리거가 **하나도 없었다.**
"""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.engine import deepsearch as D


def _jg(**kw):
    base = {"matchup": {}, "sport": "kbo", "game_id": 1}
    base.update(kw)
    return base


def test_이동이_크면_T7_이_걸린다():
    """🔴 이것이 없어서 16.62%p 가 조사 없이 지나갔다."""
    t = D.triggers(_jg(move_pp=3.1), get_settings())
    assert D.T7_PRICE_MOVE in t
    t = D.triggers(_jg(move_pp=-16.62), get_settings())
    assert D.T7_PRICE_MOVE in t, "음수 이동(원정 쪽)도 이동이다"


def test_문턱_미만이면_안_걸린다():
    """⚠️ 반대 위험 — 잡음까지 조사하면 상한이 즉시 터진다."""
    assert D.T7_PRICE_MOVE not in D.triggers(_jg(move_pp=1.0), get_settings())
    assert D.T7_PRICE_MOVE not in D.triggers(_jg(move_pp=0.0), get_settings())


def test_못_재면_안_걸린다():
    """🔴 0 으로 채우지 않는다 — "안 움직였다"와 "모른다"는 다른 말이다."""
    assert D.T7_PRICE_MOVE not in D.triggers(_jg(), get_settings())
    assert D.T7_PRICE_MOVE not in D.triggers(_jg(move_pp=None), get_settings())


def test_문턱을_여기서_정하지_않는다():
    """🔴 원본은 `odds_move.moved()`(MOVE_MIN_PP) 하나다(사본 금지)."""
    import inspect

    from app.engine.odds_move import MOVE_MIN_PP

    src = inspect.getsource(D.triggers)
    assert "moved" in src, "odds_move.moved 를 안 쓴다"
    assert str(MOVE_MIN_PP) not in src, "문턱 숫자를 여기 적었다"
    # 문턱 바로 위/아래가 규칙대로 갈린다
    assert D.T7_PRICE_MOVE in D.triggers(_jg(move_pp=MOVE_MIN_PP),
                                         get_settings())
    assert D.T7_PRICE_MOVE not in D.triggers(_jg(move_pp=MOVE_MIN_PP - 0.01),
                                             get_settings())


@pytest.mark.asyncio
async def test_이동을_트리거_앞에서_잰다():
    """🔴 **순서가 핵심이다.** 종전에는 이동이 `pick_ledger` 기록 시점에
    계산돼 **조사보다 나중**이었다. 그래서 조사가 이동을 못 봤다."""
    import inspect

    src = inspect.getsource(D.run_for_rejudge)
    i_move = src.index("attach_move")
    i_trig = min(src.index("t4_evidence"), src.index("T7_PRICE_MOVE"))
    assert i_move < i_trig, "이동 측정이 트리거 판별보다 뒤에 있다"

    src2 = inspect.getsource(D.run_for_slate)
    assert src2.index("attach_move") < src2.index("triggers(jg")


@pytest.mark.asyncio
async def test_못_재도_조사를_막지_않는다():
    """⚠️ 측정 실패가 파이프라인을 죽이면 안 된다."""
    jg = _jg(game_id=None)
    assert await D.attach_move(jg) is None
    assert "move_pp" not in jg

    class _Boom:
        async def fetch(self, *a, **k):
            raise RuntimeError("DB 없음")

    jg2 = _jg(game_id=7)
    assert await D.attach_move(jg2, pool=_Boom()) is None
    assert "move_pp" not in jg2, "못 쟀는데 값을 넣었다"


def test_규칙을_다시_짓지_않았다():
    """🔴 스냅샷 선택·기준선·환산의 원본은 `pick_ledger`·`odds_move` 다."""
    import inspect

    src = inspect.getsource(D.attach_move)
    assert "_MOVE_SNAP_SQL" in src and "_best_provider" in src
    assert "SELECT" not in src.upper().replace("_MOVE_SNAP_SQL", ""), (
        "SQL 을 여기서 새로 썼다")
