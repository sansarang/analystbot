"""[LGA-1b / STEP 1-i-1b] 기능 플래그의 **역방향 잠금.**

🔴 `features` 는 "덜 켜는" 장치다. 그런데 반대 방향이 비어 있었다 —
   **판정·라우터가 켜져 있는데 결과 적재가 없는 리그**를 아무도 막지 않는다.
   그런 리그는 판정을 하고 카드를 낼 수 있지만 **영원히 채점되지 않는다.**
   실측 2026-09-20: ACL 8건이 정확히 그 상태였다(판정 8 · 채점 0 · 결과 0).

🔴 "작동"의 정의는 **설정**이다 — `fd_names` 가 비어 있지 않거나 `fotmob_id`
   가 있으면 적재 경로가 있는 것이다.
   ⚠️ DB 행 수를 보지 않는다. 테스트가 DB 상태에 의존하면 그날그날 달라진다.
"""
from __future__ import annotations

import pytest

from app.leagues import LEAGUES, features_of

#: 결과 적재가 **없는** 채로 판정·라우터가 켜진 리그.
#  🔴 [W3-8 2026-09-21] **비었다 — 1-i-2 가 닫혔다.**
#     j1·denmark·kleague1·acl 넷은 W3-1(`b61d847`)이 `result_source: fotmob`
#     으로 적재 경로를 만들면서 해소됐다. 운영 실측: K리그1 final 53·점수 53 ·
#     덴마크 final 42·점수 42.
#     ⚠️ 그런데 이 파일의 `_has_result_source` 가 **없는 칸**(`fotmob_id`)을
#        보고 있어서 **해소된 줄 몰랐다.** 계약이 W3-1 을 따라가지 못했다.
_PENDING: set = set()


def _has_result_source(key: str) -> bool:
    """그 리그에 결과를 넣을 **경로가 설정돼 있나.**

    🔴 설정만 본다(지시 1-i-1b). `fd_names` → football-data ·
       **`result_source`** → 적재 경로 이름(`fd` · `fotmob`).
    ⚠️ [W3-8 2026-09-21] 종전에는 `fotmob_id` 를 봤는데 **그런 칸은 없다.**
       W3-1(`b61d847`)이 적재 경로를 `result_source` 로 만들었고 이 함수가
       따라가지 못했다 — 그래서 넷이 해소됐는데도 xfail 로 남아 있었다.
    ⚠️ **DB 행 수를 보지 않는다**(파일 머리 규약). 테스트가 DB 상태에
       의존하면 그날그날 달라진다.
    """
    cfg = LEAGUES.get(key) or {}
    return bool(cfg.get("fd_names")) or bool(cfg.get("result_source"))


@pytest.mark.parametrize("key", sorted(LEAGUES))
def test_judge_requires_results(key, request):
    """🔴 판정·라우터를 켰으면 **결과 적재도 켜져 있어야** 한다.

    안 그러면 그 리그는 판정만 쌓이고 **영원히 채점되지 않는다.**
    """
    if key in _PENDING:
        request.node.add_marker(pytest.mark.xfail(
            reason="1-i-2 에서 fotmob_id 로 해소", strict=True))
    feats = set(features_of(key))
    if not (feats & {"judge", "router"}):
        return                      # 결과만 켠 리그는 대상이 아니다
    assert "results" in feats, f"{key}: 판정/라우터가 켜졌는데 results 가 없다"
    assert _has_result_source(key), \
        f"{key}: results 가 켜졌는데 적재 경로(fd_names·fotmob_id)가 없다"


def test_pending_이_비었다():
    """🔴 [W3-8 2026-09-21] **1-i-2 가 닫혔다.**

    ⚠️ 종전 `test_pending_목록이_비면_1i2가_닫힌다` 를 대체한다 — 그 시험은
       "비었으면 지우라는 신호"라고 스스로 적고 있었다.
    """
    assert _PENDING == set(), _PENDING


def test_경로가_없으면_여전히_걸린다():
    """🔴 **느슨하게 고친 것이 아님을 확인한다.**

    이 계약의 목적은 "판정·라우터가 켜졌는데 결과 적재가 없는 리그"를 막는
    것이다(실측 2026-09-20: ACL 8건이 판정 8 · 채점 0 · 결과 0).
    칸 이름만 고쳤지 **구멍을 열지 않았다.**
    """
    import app.leagues as L

    key = "__시험용__"
    L.LEAGUES[key] = {"features": ("judge", "router", "results")}
    try:
        assert _has_result_source(key) is False
        with pytest.raises(AssertionError):
            test_judge_requires_results(key, _NoMark())
    finally:
        L.LEAGUES.pop(key, None)


class _NoMark:
    """`request` 대역 — xfail 표시를 받지 않는다."""

    class node:
        @staticmethod
        def add_marker(_m):
            raise AssertionError("빈 _PENDING 인데 xfail 을 붙이려 했다")
