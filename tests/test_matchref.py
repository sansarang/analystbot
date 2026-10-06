"""🔴🔴 **입구는 하나다** — 2단계(사용자 설계 2026-10-03).

> 입구에서 **단 한 번** 이름을 ID 로 바꾸고, 그 뒤로는 ID 만 쓴다.

⚠️ 종전 `analyze.answer` 는 별칭을 풀고, 리그를 묻고, 표를 뒤지고, 못 찾으면 다시
   찾고 — **네 군데에서 이름을 다시 비교했다.** 그 사이에서 언어가 갈리면 자기가
   찾은 것을 버렸다(실측 2026-10-03: 네 번).
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import datetime, timezone

import pytest

from app import matchref, resolve
from app.matchref import MatchRef, Reason


def _code(fn) -> str:
    """🔴 D46 — **독스트링·주석을 뺀 코드만** 본다."""
    return ast.unparse(ast.parse(textwrap.dedent(inspect.getsource(fn))))


def test_열쇠를_새로_만들지_않는다():
    """🔴 `games.ext_id` 가 **이미** 그 열쇠다(`UNIQUE(sport, ext_id)`).

    ⚠️ 비슷한 열쇠를 하나 더 만들면 **둘을 맞추는 코드**가 또 생기고, 그것이 지금
       고치려는 병의 모양이다(사본 금지).
    """
    row = {"id": 7, "ext_id": "fotmob-5181853", "home": "Croatia",
           "away": "England", "sport": "soccer", "league": "UEFA NL",
           "starts_kst": datetime(2026, 10, 3, 16, tzinfo=timezone.utc)}
    ref = matchref.ref_from_row(row)
    assert ref.key == "fotmob-5181853"
    assert ref.game_id == 7


def test_팀은_ID_로_들고_다닌다():
    """🔴 1단계 이름표가 준 열쇠가 `MatchRef` 에 박힌다 — 이름이 아니라 **이것**이 신원."""
    row = {"id": 1, "ext_id": "x-1", "home": "Croatia", "away": "England",
           "sport": "soccer", "league": "UEFA NL",
           "starts_kst": datetime(2026, 10, 3, 16, tzinfo=timezone.utc)}
    # 🔴 **열쇠는 봇이 발급한 번호다** — 글자로 박지 않는다(사용자 지적 2026-10-04).
    #    ⚠️ 이름이 든 열쇠는 표기가 하나만 바뀌어도 ID 가 죽는다.
    from app import teamref
    ref = matchref.ref_from_row(row)
    assert ref.home_id == teamref.key_of("Croatia")[0]
    assert ref.away_id == teamref.key_of("England")[0]
    assert ref.home_id.startswith(teamref.TEAM_KEY_PREFIX)
    assert ref.home_id != ref.away_id


def test_시간대_없는_값은_안_받는다():
    """🔴 사용자 설계: *"내부는 UTC 만, KST 는 출력할 때만."*

    ⚠️ 실측 2026-10-03: `16:00Z` 와 `01:00 KST` 를 섞어 비교해 **경기를 잃었다**.
    🔴 시간대 없는 값은 **안 받는다** — 조용히 UTC 로 가정하면 그 거짓이 안 보인다.
    """
    naive = {"id": 1, "ext_id": "x-1", "home": "A", "away": "B",
             "starts_kst": datetime(2026, 10, 3, 16)}
    assert matchref.ref_from_row(naive).kickoff_utc is None
    aware = dict(naive, starts_kst=datetime(2026, 10, 3, 16,
                                            tzinfo=timezone.utc))
    got = matchref.ref_from_row(aware).kickoff_utc
    assert got is not None and got.tzinfo is not None


def test_MatchRef_는_중간에_안_바뀐다():
    """🔴 `frozen` — 중간 단계가 슬그머니 고치면 그 자체가 이 병의 재발이다."""
    ref = MatchRef(key="x-1")
    with pytest.raises(Exception):
        ref.key = "x-2"             # type: ignore[misc]


def test_실패한_조건이_사유를_정한다():
    """🔴🔴 실측 2026-10-03 — **거짓 사유가 사용자를 두 번 헛돌게 했다.**

    봇이 `Croatia` 로 적어 놓고 `크로아티아` 로 되찾아 실패한 뒤
    *"질문 창 밖이다 — 날짜를 지정해 다시 물어라"* 라고 적었다. 🔴 날짜는 맞았고
    **이름이 달랐다.** 그래서 날짜를 지정해 다시 물어도 같은 자리에서 또 막혔다.
    """
    assert Reason.OUT_OF_WINDOW.fixable_by_asking_again
    assert Reason.AMBIGUOUS.fixable_by_asking_again
    # 🔴 **이름 문제는 다시 물어도 안 풀린다** — 그렇게 적으면 거짓말이다
    assert not Reason.NAME_UNRESOLVED.fixable_by_asking_again
    assert not Reason.MATCH_NOT_FOUND.fixable_by_asking_again
    # 🔴 사유는 **enum 이 정한다** — 입구가 문장을 짓지 않는다
    code = _code(resolve.match_of)
    for r in ("NAME_UNRESOLVED", "MATCH_NOT_FOUND", "OUT_OF_WINDOW",
              "AMBIGUOUS"):
        assert f"Reason.{r}" in code, r






@pytest.mark.asyncio
async def test_이름을_못_풀면_그렇게_말한다():
    """🔴 *"이름 문제"* 와 *"자료 문제"* 는 처방이 완전히 다르다.

    ⚠️ 하나는 이름표 한 줄을 적는 것, 하나는 자료를 더 찾는 것이다.
    """
    class _Pool:
        async def fetchrow(self, *a):
            return None

        async def fetch(self, *a, **k):
            return []

        async def fetchval(self, *a, **k):
            return None

    got = await resolve.match_of(_Pool(), team="없는팀 FC", opponent="",
                                 look_up=False)
    assert got.reason is Reason.NAME_UNRESOLVED, got.steps
    assert not got.ok
