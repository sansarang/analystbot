"""[HYC-2] **확정 XI 가 아니면 `xi_confirmed` 는 미상이다.**

사용자 2026-09-23: "hyc 전부 다 해라"
계획서(`hyp_conditions_0920`) §1-b:
> `app/engine/scout_config.py` 의 `_XI_STATUS` 옆에 **확정으로 인정하는 값
>  하나**를 두고(`XI_CONFIRMED = ("official",)`), `n05` 가 그것을 읽는다.
> `lastStarting11`·`predicted`·`standard`·`None` 은 전부 미상.

🔴 왜 필요한가 (계획서의 실측):
```
유일하게 confirmed 로 센 xi_confirmed 가 **믿을 수 없는 카드**였다 —
  conflict: true (무고사·하창래가 결장 목록과 XI에 동시 존재)
  source: ""
  xi_status: "lastStarting11"   ← 오늘 확정 XI 가 아니라 지난 경기 선발
```

🔴 `lineups` 표 경로는 XI-1 이 이미 `STATUS_CONFIRMED` 만 인정한다. 여기서
   막는 것은 **위성 추출 상자 경로**다 — 그 상자의 `xi_status` 가
   `predicted` 여도 종전에는 값이 실렸다.

⚠️ CLAUDE.md 발송 규율 "**예상을 확정으로 취급 금지**"와 같은 규약이다.
"""
from __future__ import annotations

import inspect

import pytest

from app.engine import scout_config as SC


def test_확정으로_인정하는_값이_한_곳에_있다():
    """🔴 원본은 `scout_config` 하나다 — 노드에 문자열을 적지 않는다."""
    assert hasattr(SC, "XI_CONFIRMED")
    assert "official" in SC.XI_CONFIRMED


def test_예상은_확정이_아니다():
    """🔴 계획서가 이름을 댄 값들이 전부 빠져 있어야 한다."""
    for bad in ("predicted", "lastStarting11", "standard", "", None):
        assert bad not in SC.XI_CONFIRMED, bad


def test_아는_상태값_목록은_그대로다():
    """⚠️ 반대 위험 — `_XI_STATUS` 는 "아는 값"이고 확정 여부와 다르다."""
    assert set(SC._XI_STATUS) >= {"predicted", "official"}


def _ev(box, status="official"):
    # ⚠️ `_FROM_EXTRACT` 가 `xi_confirmed` 를 `out` 칸에서 읽는다(기존 배선).
    #    이 시험이 보는 것은 **확정 여부 관문**이므로 `out` 에 값을 둔다.
    return {"teams": {"home": {"team": "H", "out": ["결장 A"],
                               "xi": ["a"] * 11, "xi_status": status,
                               "out_src": "official", "conflict": False,
                               "sources_fed": ["http://x"]},
                      "away": {"team": "A", "out": ["결장 B"],
                               "xi": ["b"] * 11, "xi_status": status,
                               "out_src": "official", "conflict": False,
                               "sources_fed": ["http://x"]}},
            # ⚠️ [HYC-1] 신뢰 검사가 먼저다 — 수집 시각이 없으면 카드를
            #    못 믿어 이 시험의 관문(확정 XI)까지 가지도 못한다.
            "gathered_at": "2026-09-23T17:30:00+00:00",
            **box}


async def _run(status):
    from app.flow.ctx import Ctx
    from app.flow.state import State
    from app.flow.nodes import n05_evidence as N5

    st = State.new({"id": "1", "sport": "soccer", "league": "EPL",
                    "home": "H", "away": "A",
                    "starts_at": "2026-09-23T18:00:00+00:00"})
    st.sport = "soccer"
    st.pick_side = "home"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "xi_confirmed"}]}]
    out = await N5.run(st, Ctx(inject={"extract": _ev({}, status),
                                       "absences": []}))
    return [e for e in (out.n05_evidence or []) if e["var"] == "xi_confirmed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["predicted", "lastStarting11", "standard", ""])
async def test_예상_XI_는_증거로_실리지_않는다(status):
    """🔴 이 단위의 전부 — 종전에는 `predicted` 도 값이 실렸다."""
    rows = await _run(status)
    assert all(not r.get("value") for r in rows), (status, rows)


@pytest.mark.asyncio
async def test_공식_XI_는_실린다():
    """⚠️ 반대 위험 — 막느라 진짜 확정까지 버리면 안 된다."""
    rows = await _run("official")
    assert rows and rows[0].get("value"), rows


def test_노드가_문자열을_손으로_적지_않았다():
    """🔴 사본 금지."""
    from app.flow.nodes import n05_evidence as N5

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(N5).splitlines())
    for bad in ('"lastStarting11"', "'lastStarting11'", '"official"'):
        assert bad not in src, f"상태 문자열을 손으로 적었다: {bad}"
    # ⚠️ 상수를 직접 쓰든 판정 함수를 쓰든 **원본을 읽는 것**이면 된다.
    assert ("XI_CONFIRMED" in src or "xi_is_confirmed" in src), \
        "확정 판정의 원본을 안 읽는다"
