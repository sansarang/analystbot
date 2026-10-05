"""킥오프 **전** 녹음 계약 (사용자 지시 2026-10-02).

🔴 **정답지와 무관하다** — 이것은 *"시작한 경기를 녹음하지 않는다"* 는 기계 규율이고,
   무엇이 정답인지와 아무 관계가 없다. 그래서 정답지를 지울 때 함께 지우지 않고
   여기로 옮겼다.
"""
from __future__ import annotations

import pytest


# ══════════════════════════════════════════════════════════════════
# 🔴 킥오프 **전** 녹음 (사용자 지시 2026-10-02 — 게이트)
# ══════════════════════════════════════════════════════════════════


def test_킥오프_지난_경기는_녹음하지_않는다():
    """🔴🔴 **이것이 이 기능의 전부다.**

    §9 단계 4 는 *"**경기 전 시점** 웹에서 재현"* 을 요구한다. 시작한 경기를 녹음하면
    순위·폼이 결과를 담고 있어 **경기 후 자료**가 되고, 그 카세트로 잰 재현율은 거짓이다.
    ⚠️ 건너뛴 경기도 **사유와 함께** 보고에 들어가야 한다(조용한 0 금지).
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    from app import scheduler as S

    KST = timezone(timedelta(hours=9))
    now = datetime.now(timezone.utc)

    class _Pool:
        async def fetch(self, *a, **k):
            return [
                # 🔴 이미 시작했다 — 건너뛰어야 한다
                {"id": 1, "sport": "soccer", "league": "L", "home": "H1",
                 "away": "A1", "venue": None, "ext_id": "x1", "status": "x",
                 "starts_kst": now - timedelta(minutes=30),
                 "home_score": None, "away_score": None, "round_note": None},
                # ⚠️ 너무 멀다 — 창 밖이다
                {"id": 2, "sport": "soccer", "league": "L", "home": "H2",
                 "away": "A2", "venue": None, "ext_id": "x2", "status": "x",
                 "starts_kst": now + timedelta(hours=20),
                 "home_score": None, "away_score": None, "round_note": None},
            ]

    got = asyncio.run(S.record_prekickoff_once(_Pool(), within_min=180))
    assert got["recorded"] == 0 and got["skipped"] == 2, got
    whys = [v["why"] for v in got["games"].values()]
    assert any("이미 시작했다" in w for w in whys), whys
    assert any("아직 멀다" in w for w in whys), whys
    # 🔴 창을 코드에 박지 않았나 — 기본값이 §19-d 라인업 창보다 넓다
    from app.cells import WAKE, Q_LINEUP
    assert S.PREKICK_WINDOW_MIN > WAKE[Q_LINEUP][0]


def test_녹음_모드가_새지_않는다():
    """🔴 운영이 녹음 모드로 남으면 디스크가 찬다 — 실측: 라이브 4회에 59MB.

    ⚠️ `finally` 로 되돌려야 한다. 터져도 되돌아와야 한다.
    """
    import asyncio
    import inspect
    import os

    from app import cassette
    from app import scheduler as S

    src = inspect.getsource(S.record_prekickoff_once)
    assert "finally:" in src, "녹음 모드를 되돌리는 자리가 없다"

    class _Boom:
        async def fetch(self, *a, **k):
            raise RuntimeError("DB 터짐")

    before = os.environ.get(cassette.MODE_ENV)
    with pytest.raises(RuntimeError):
        asyncio.run(S.record_prekickoff_once(_Boom()))
    assert os.environ.get(cassette.MODE_ENV) == before, "녹음 모드가 남았다"


def test_녹음이_카드를_저장한다():
    """🔴🔴 **라이브 테스트가 이 구멍을 찾았다**(사용자 지시 2026-10-02 — 아시안게임).

    전 판 `record_prekickoff_once` 는 **사실만 모으고 끝났다.** 그러면 경기가 끝난 뒤
    채점이 *"카드를 저장한 적이 없다"* 로 건너뛰고 **원장이 영원히 빈다** —
    *"뭘 쌓는데"* 의 답이 "아무것도"가 된다.
    """
    import inspect

    from app import scheduler as S

    src = inspect.getsource(S.record_prekickoff_once)
    # 🔴 카드를 만들고 **적는다**
    assert "analyze.build(" in src and "analyze.persist(" in src
    # 🔴 적재가 실패해도 녹음은 남는다 — 사유를 적는다
    assert "카드 적재 실패" in src
    # 🔴 보고에 **무엇이 저장됐나**가 들어간다(조용한 0 금지)
    for key in ("insufficient", "scenarios", "saved"):
        assert f'"{key}"' in src, key
